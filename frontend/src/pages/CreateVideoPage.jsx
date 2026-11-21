import { useState } from 'react';
import { FileText, Mic, Sparkles, Upload } from 'lucide-react';
import { createProject } from '../api/client';

const VOICES = [
  { id: 'en-US-ChristopherNeural', label: 'Christopher (US Male — Crisp Documentary)' },
  { id: 'en-US-AndrewNeural', label: 'Andrew (US Male — Warm Storytelling)' },
  { id: 'en-US-GuyNeural', label: 'Guy (US Male — Sports Commentary)' },
  { id: 'en-US-AvaNeural', label: 'Ava (US Female — Clear Expressive)' },
];

export default function CreateVideoPage({ onCreated }) {
  const [mode, setMode] = useState('short');
  const [inputType, setInputType] = useState('title');
  const [title, setTitle] = useState('');
  const [notesOrScript, setNotesOrScript] = useState('');
  const [voiceName, setVoiceName] = useState(VOICES[0].id);
  const [durationSec, setDurationSec] = useState(50);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const minDur = mode === 'short' ? 20 : 60;
  const maxDur = mode === 'short' ? 60 : 600;

  function handleModeSwitch(nextMode) {
    setMode(nextMode);
    if (nextMode === 'short') {
      setDurationSec((prev) => Math.min(60, Math.max(20, prev > 60 ? 50 : prev)));
    } else {
      setDurationSec((prev) => (prev < 60 ? 180 : Math.min(600, prev)));
    }
  }

  async function handleTxtUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const content = await file.text();
    setNotesOrScript(content.trim());
    if (!title.trim()) {
      setTitle(file.name.replace(/\.txt$/i, '').replace(/[_-]+/g, ' '));
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    const cleanTitle = title.trim();
    const cleanRaw =
      inputType === 'script'
        ? notesOrScript.trim()
        : notesOrScript.trim() || cleanTitle;

    if (cleanTitle.length < 3) {
      setError('Please enter a project title (at least 3 characters).');
      return;
    }
    if (inputType === 'script' && cleanRaw.length < 10) {
      setError('Please paste or upload your spoken script before queuing.');
      return;
    }

    setSubmitting(true);
    try {
      await createProject({
        mode,
        input_type: inputType,
        title: cleanTitle,
        raw_input: cleanRaw,
        voice_name: voiceName,
        target_duration_sec: durationSec,
      });
      await onCreated();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  const wordCount = notesOrScript.trim()
    ? notesOrScript.trim().split(/\s+/).length
    : 0;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-[#F8FAFC]">Create Video</h1>
        <p className="mt-1 text-sm text-[#94A3B8]">
          Queue a project for your Local PC Worker (Gemini script + edge-tts voice + matched vault clips + FFmpeg).
        </p>
      </div>

      <form
        onSubmit={handleSubmit}
        className="space-y-6 rounded-xl border border-[#22283A] bg-[#131722] p-6"
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="block text-xs font-medium uppercase tracking-wider text-[#94A3B8]">
              Format Mode
            </label>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => handleModeSwitch('short')}
                className={`rounded-lg border px-3 py-2.5 text-sm font-medium transition ${
                  mode === 'short'
                    ? 'border-[#F59E0B] bg-[#F59E0B]/10 text-[#F8FAFC]'
                    : 'border-[#22283A] bg-[#090B10] text-[#94A3B8] hover:text-[#F8FAFC]'
                }`}
              >
                Short 9:16
              </button>
              <button
                type="button"
                onClick={() => handleModeSwitch('long')}
                className={`inline-flex items-center justify-center gap-1.5 rounded-lg border px-3 py-2.5 text-sm font-medium transition ${
                  mode === 'long'
                    ? 'border-[#F59E0B] bg-[#F59E0B]/10 text-[#F8FAFC]'
                    : 'border-[#22283A] bg-[#090B10] text-[#94A3B8] hover:text-[#F8FAFC]'
                }`}
              >
                <span>Long 16:9</span>
                <span className="rounded bg-[#38BDF8]/15 px-1.5 py-0.5 font-mono text-[10px] text-[#38BDF8]">
                  Beta
                </span>
              </button>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium uppercase tracking-wider text-[#94A3B8]">
              Input Method
            </label>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setInputType('title')}
                className={`inline-flex items-center justify-center gap-1.5 rounded-lg border px-3 py-2.5 text-sm font-medium transition ${
                  inputType === 'title'
                    ? 'border-[#F59E0B] bg-[#F59E0B]/10 text-[#F8FAFC]'
                    : 'border-[#22283A] bg-[#090B10] text-[#94A3B8] hover:text-[#F8FAFC]'
                }`}
              >
                <Sparkles className="h-3.5 w-3.5 text-[#F59E0B]" />
                Title → Auto Script
              </button>
              <button
                type="button"
                onClick={() => setInputType('script')}
                className={`inline-flex items-center justify-center gap-1.5 rounded-lg border px-3 py-2.5 text-sm font-medium transition ${
                  inputType === 'script'
                    ? 'border-[#F59E0B] bg-[#F59E0B]/10 text-[#F8FAFC]'
                    : 'border-[#22283A] bg-[#090B10] text-[#94A3B8] hover:text-[#F8FAFC]'
                }`}
              >
                <FileText className="h-3.5 w-3.5 text-[#38BDF8]" />
                Paste / .txt Script
              </button>
            </div>
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-[#94A3B8]">
            Video Title / Headline
          </label>
          <input
            type="text"
            required
            minLength={3}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. LeBron James stunned reporters after Lakers comeback win"
            className="mt-1.5 w-full rounded-lg border border-[#22283A] bg-[#090B10] px-3.5 py-2.5 text-sm text-[#F8FAFC] placeholder-[#94A3B8]/60 focus:border-[#F59E0B] focus:outline-none"
          />
        </div>

        {inputType === 'title' ? (
          <div>
            <label className="block text-xs font-medium text-[#94A3B8]">
              Optional Context / Notes for Gemini (leave blank for pure headline script)
            </label>
            <textarea
              rows={3}
              value={notesOrScript}
              onChange={(e) => setNotesOrScript(e.target.value)}
              placeholder="Optional talking points, game stats, or interview quote to highlight..."
              className="mt-1.5 w-full rounded-lg border border-[#22283A] bg-[#090B10] px-3.5 py-2.5 text-sm text-[#F8FAFC] placeholder-[#94A3B8]/60 focus:border-[#F59E0B] focus:outline-none"
            />
          </div>
        ) : (
          <div>
            <div className="flex items-center justify-between">
              <label className="block text-xs font-medium text-[#94A3B8]">
                Exact Spoken Script (preserved word-for-word)
              </label>
              <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-[#22283A] bg-[#090B10] px-2.5 py-1 text-xs font-medium text-[#F8FAFC] hover:border-[#F59E0B]">
                <Upload className="h-3.5 w-3.5 text-[#F59E0B]" />
                Upload .txt
                <input
                  type="file"
                  accept=".txt,text/plain"
                  onChange={handleTxtUpload}
                  className="hidden"
                />
              </label>
            </div>
            <textarea
              rows={6}
              required
              value={notesOrScript}
              onChange={(e) => setNotesOrScript(e.target.value)}
              placeholder="Paste your exact voiceover narration here..."
              className="mt-1.5 w-full rounded-lg border border-[#22283A] bg-[#090B10] px-3.5 py-2.5 text-sm text-[#F8FAFC] placeholder-[#94A3B8]/60 focus:border-[#F59E0B] focus:outline-none"
            />
            <p className="mt-1 font-mono text-xs text-[#94A3B8]">
              {wordCount} words (~{Math.max(1, Math.round(wordCount / 2.5))}s spoken)
            </p>
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="flex items-center gap-1.5 text-xs font-medium text-[#94A3B8]">
              <Mic className="h-3.5 w-3.5 text-[#F59E0B]" />
              Free AI Voice (edge-tts)
            </label>
            <select
              value={voiceName}
              onChange={(e) => setVoiceName(e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-[#22283A] bg-[#090B10] px-3 py-2.5 text-sm text-[#F8FAFC] focus:border-[#F59E0B] focus:outline-none"
            >
              {VOICES.map((voice) => (
                <option key={voice.id} value={voice.id}>
                  {voice.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <div className="flex items-center justify-between text-xs">
              <label className="font-medium text-[#94A3B8]">Target Duration</label>
              <span className="font-mono font-semibold text-[#F59E0B]">{durationSec}s</span>
            </div>
            <input
              type="range"
              min={minDur}
              max={maxDur}
              step={mode === 'short' ? 5 : 15}
              value={durationSec}
              onChange={(e) => setDurationSec(Number(e.target.value))}
              className="mt-3.5 h-2 w-full cursor-pointer accent-[#F59E0B]"
            />
            <div className="mt-1 flex justify-between font-mono text-[11px] text-[#94A3B8]">
              <span>{minDur}s</span>
              <span>{maxDur}s</span>
            </div>
          </div>
        </div>

        {error && (
          <p className="rounded-lg border border-[#F43F5E]/30 bg-[#F43F5E]/10 px-3.5 py-2.5 text-xs text-[#F43F5E]">
            {error}
          </p>
        )}

        <div className="flex items-center justify-end border-t border-[#22283A] pt-4">
          <button
            type="submit"
            disabled={submitting}
            className="inline-flex items-center gap-2 rounded-lg bg-[#F59E0B] px-6 py-2.5 text-sm font-semibold text-[#090B10] transition hover:bg-[#D97706] disabled:opacity-60"
          >
            {submitting ? 'Queuing Job...' : 'Generate Video'}
          </button>
        </div>
      </form>
    </div>
  );
}
