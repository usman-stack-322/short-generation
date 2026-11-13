import hashlib
import json
import math
import struct
import subprocess
import sys
import wave
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from app.core.config import settings
from app.tts import kokoro_worker
from app.tts.providers import KokoroTTSProvider
from app.video.renderer import render_video


def _write_pcm(path: Path, seconds: float = 1.5, rate: int = 24000):
    n = int(seconds * rate)
    array_samples = b''.join(
        struct.pack('<h', int(4000 * math.sin(2 * math.pi * 220 * i / rate)))
        for i in range(n)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(array_samples)
    return n / rate


def test_kokoro_resolve_model_prefers_verified_fp32_or_falls_back_to_int8(tmp_path, monkeypatch):
    models = tmp_path / 'models'
    models.mkdir(parents=True)
    int8 = models / 'kokoro-v1.0.int8.onnx'
    int8.write_bytes(b'int8')
    fp32 = models / 'kokoro-v1.0.onnx'
    fp32.write_bytes(b'partial')

    # Partial FP32 falls back to INT8
    path, label, _ = kokoro_worker.resolve_model(tmp_path)
    assert path == int8 and 'INT8' in label

    # Exact size + digest matches FP32 and caches verified-fp32.json
    payload = b'verified-fp32-weights'
    fp32.write_bytes(payload)
    monkeypatch.setattr(kokoro_worker, 'FP32_BYTES', len(payload))
    monkeypatch.setattr(kokoro_worker, 'FP32_SHA256', hashlib.sha256(payload).hexdigest())
    path, label, _ = kokoro_worker.resolve_model(tmp_path)
    assert path == fp32 and 'FP32' in label
    assert (models / 'verified-fp32.json').is_file()


def test_kokoro_load_and_synthesize_uses_fast_threads_no_sliding_and_all_voices(tmp_path, monkeypatch):
    runtime = tmp_path / 'rt'
    (runtime / 'models').mkdir(parents=True)
    (runtime / 'python').mkdir(parents=True)
    (runtime / 'models/kokoro-v1.0.int8.onnx').write_bytes(b'int8')
    (runtime / 'models/voices-v1.0.bin').write_bytes(b'voices')

    seen = {}

    class FakeSessionOptions:
        def __init__(self):
            self.configs = {}
            self.intra_op_num_threads = 0
            self.inter_op_num_threads = 0
            self.execution_mode = None
            self.graph_optimization_level = None

        def add_session_config_entry(self, k, v):
            self.configs[k] = v

    class FakeORT(ModuleType):
        SessionOptions = FakeSessionOptions
        ExecutionMode = SimpleNamespace(ORT_SEQUENTIAL='SEQ')
        GraphOptimizationLevel = SimpleNamespace(ORT_ENABLE_ALL='ALL')

        @staticmethod
        def InferenceSession(path, sess_options=None, providers=None):
            seen['options'] = sess_options
            seen['providers'] = providers
            return SimpleNamespace(model_path=path)

    class FakeTokenizer:
        def phonemize(self, text, lang):
            return ' '.join(w.lower() for w in text.split())

    class FakeKokoroInstance:
        voices = {'am_michael': [0], 'af_heart': [0], 'bm_george': [0]}
        tokenizer = FakeTokenizer()

        def create_timed(self, phonemes, **controls):
            seen['controls'] = controls
            audio = [0.2 * math.sin(i * 0.01) for i in range(24000)]
            timings = [SimpleNamespace(phoneme=c, start=i * 0.02, end=(i + 1) * 0.02) for i, c in enumerate(phonemes)]
            return audio, 24000, timings

    class FakeKokoroMod(ModuleType):
        class Kokoro:
            @staticmethod
            def from_session(sess, voices_path):
                return FakeKokoroInstance()

    class _FakeBoolList(list):
        def all(self):
            return all(self)

    fake_np = ModuleType('numpy')
    fake_np.float32 = float
    fake_np.zeros = lambda n, dtype=None: [0.0] * int(n)
    fake_np.concatenate = lambda seqs: [x for s in seqs for x in s]
    fake_np.isfinite = lambda arr: _FakeBoolList(math.isfinite(x) for x in arr)
    fake_np.abs = lambda arr: [abs(x) for x in arr]
    fake_np.max = max
    monkeypatch.setitem(sys.modules, 'numpy', fake_np)
    monkeypatch.setitem(sys.modules, 'onnxruntime', FakeORT('onnxruntime'))
    monkeypatch.setitem(sys.modules, 'kokoro_onnx', FakeKokoroMod('kokoro_onnx'))
    monkeypatch.setitem(sys.modules, 'soundfile', SimpleNamespace(write=lambda p, a, r, subtype=None: _write_pcm(Path(p), 1.0, r)))

    k, _, label, sha, loaded = kokoro_worker.load_kokoro(runtime)
    assert seen['options'].intra_op_num_threads >= 4
    assert seen['options'].configs['session.intra_op.allow_spinning'] == '1'
    assert seen['options'].graph_optimization_level == 'ALL'

    out = tmp_path / 'out' / 'voice.wav'
    report = kokoro_worker.synthesize_one(
        k, label, sha, loaded,
        {'voice': 'af_heart', 'text': 'hello world', 'output': str(out), 'speed': 1.0, 'alignment_required': True},
    )
    assert seen['controls']['continuous'] is False
    assert seen['controls']['voice'] == 'af_heart'
    assert out.is_file() and out.with_suffix('.words.json').is_file()
    assert report['engine_controls']['voice'] == 'af_heart'

    with pytest.raises(ValueError):
        kokoro_worker.synthesize_one(k, label, sha, loaded, {'voice': 'unknown_voice', 'text': 'hi', 'output': str(out)})


def test_renderer_uses_multithreaded_fast_blur_pipeline_on_video_clips(tmp_path):
    clip = tmp_path / 'clip.mp4'
    subprocess.run(
        [settings.ffmpeg_path, '-y', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=640x360:r=30:d=1.6',
         '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(clip)],
        check=True, capture_output=True, timeout=30,
    )
    wav = tmp_path / 'voice.wav'
    _write_pcm(wav, seconds=1.5, rate=16000)

    out_video, _, _ = render_video(
        'fast-clip-test', 'Fast render headline', 'Topic', 'Short spoken line.',
        wav, 10, tmp_path / 'out', [clip],
        scene_plan=[{'visual_type': 'licensed_clip', 'text': 'Short spoken line.', 'purpose': 'clip',
                     'motion': {'type': 'hold', 'amount': 0.0, 'reason': 'video clip'}, 'transition_in': 'cut'}],
        slide_kinds=['clip'], revision=1,
    )
    assert out_video.is_file()
    cmd = json.loads((out_video.parent / 'render-command.json').read_text(encoding='utf8'))
    assert cmd[cmd.index('-filter_complex_threads') + 1] == '0'
    assert cmd[cmd.index('-threads') + 1] == '0'
    assert '-an' in cmd and '-sn' in cmd
    fg_str = cmd[cmd.index('-filter_complex') + 1]
    assert 'scale=270:480' in fg_str and 'boxblur=8:2' in fg_str


def test_kokoro_provider_reuses_warm_worker_and_sets_backend_cwd(tmp_path, monkeypatch):
    from app.tts import providers

    monkeypatch.setattr(providers, '_KOKORO_WORKERS', {})
    runtime = tmp_path / 'rt'
    (runtime / 'models').mkdir(parents=True)
    (runtime / 'models/verified-int8.json').write_text('{}', encoding='utf8')
    py = tmp_path / 'python.exe'
    py.write_text('stub', encoding='utf8')
    monkeypatch.setenv('KOKORO_PYTHON', str(py))

    # Point providers.__file__ parents[3] lookup? Instead test _ensure_worker + generate_voice via monkeypatch
    spawn_calls = []

    class FakeStdin:
        def __init__(self):
            self.lines = []
        def write(self, data):
            self.lines.append(data)
        def flush(self):
            pass

    class FakeStdout:
        def __init__(self, responses):
            self._responses = list(responses)
        def readline(self):
            return self._responses.pop(0) if self._responses else ''

    class FakeProc:
        def __init__(self, responses):
            self.stdin = FakeStdin()
            self.stdout = FakeStdout(responses)
            self.stderr = FakeStdout([])
        def poll(self):
            return None
        def kill(self):
            pass

    def fake_popen(cmd, **kwargs):
        spawn_calls.append((cmd, kwargs))
        return FakeProc(['{"ready": true}\n', '{"ok": true}\n', '{"ok": true}\n'])

    monkeypatch.setattr(providers.subprocess, 'Popen', fake_popen)
    proc1 = KokoroTTSProvider._ensure_worker(py, runtime)
    proc2 = KokoroTTSProvider._ensure_worker(py, runtime)
    assert proc1 is proc2
    assert len(spawn_calls) == 1
    assert spawn_calls[0][1]['cwd'] == str(Path(providers.__file__).resolve().parents[2])

