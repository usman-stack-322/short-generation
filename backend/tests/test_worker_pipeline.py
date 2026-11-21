"""Automated QA tests for the Phase 2 Local PC Render Worker & video streaming API."""

import os
from pathlib import Path
import subprocess
import tempfile

import pytest

from worker.clip_resolver import ResolvedCut
from worker.ffmpeg_renderer import probe_rendered_video, render_video
from worker.script_service import generate_script
from worker.tts_service import create_ass_from_script
from worker.web_fetcher import is_allowed_original_video


def _ffmpeg_generate_clip(path: Path, color: str, size: str, duration: int = 3) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s={size}:r=30:d={duration}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _ffmpeg_generate_audio(path: Path, duration: int = 5) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=44100:duration={duration}",
            "-c:a",
            "pcm_s16le",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def test_render_5_second_short_with_synthetic_audio_clips_and_captions():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        clip_wide = tmp_dir / "clip_wide.mp4"
        clip_tall = tmp_dir / "clip_tall.mp4"
        audio_path = tmp_dir / "narration.wav"
        ass_path = tmp_dir / "captions.ass"
        output_mp4 = tmp_dir / "short_5s.mp4"

        _ffmpeg_generate_clip(clip_wide, color="blue", size="1280x720", duration=3)
        _ffmpeg_generate_clip(clip_tall, color="gold", size="720x1280", duration=3)
        _ffmpeg_generate_audio(audio_path, duration=5)

        script = "LeBron James stunned fans tonight after this wild fourth quarter comeback win."
        create_ass_from_script(
            script_text=script,
            duration_sec=5.0,
            output_ass=ass_path,
            max_words_per_chunk=3,
            play_res=(1080, 1920),
        )
        ass_text = ass_path.read_text(encoding="utf-8")
        assert ",5,3,2,70,70,390," in ass_text
        assert "&H000BF5FF&" in ass_text
        assert "&H00FFFFFF&" in ass_text
        assert r"\fscx92\fscy92\t(0,80,\fscx100\fscy100)" in ass_text
        style_line = next(line for line in ass_text.splitlines() if line.startswith("Style: Default,"))
        style_parts = style_line.split(",")
        assert 78 <= int(style_parts[2]) <= 86
        assert int(style_parts[16]) == 5  # Outline=5
        assert int(style_parts[17]) == 3  # Shadow=3
        assert 360 <= int(style_parts[21]) <= 420  # MarginV

        import re

        dialogue_lines = [line for line in ass_text.splitlines() if line.startswith("Dialogue:")]
        assert len(dialogue_lines) == len(script.split())
        for line in dialogue_lines:
            raw_payload = line.split(",", 9)[9]
            spoken = re.sub(r"\{[^}]*\}", "", raw_payload).strip()
            assert spoken == spoken.upper()
            assert 2 <= len(spoken.split()) <= 3

        cuts = [
            ResolvedCut(
                clip_id="c1",
                celebrity_id="celeb1",
                local_path=clip_wide,
                start_sec=0.0,
                cut_duration_sec=1.8,
                match_reason="tag_match",
                source_r2_key=f"local://{clip_wide.as_posix()}",
            ),
            ResolvedCut(
                clip_id="c2",
                celebrity_id="celeb1",
                local_path=clip_tall,
                start_sec=0.0,
                cut_duration_sec=1.6,
                match_reason="celebrity_fallback",
                source_r2_key=f"local://{clip_tall.as_posix()}",
            ),
            ResolvedCut(
                clip_id="c1",
                celebrity_id="celeb1",
                local_path=clip_wide,
                start_sec=0.5,
                cut_duration_sec=1.6,
                match_reason="tag_match",
                source_r2_key=f"local://{clip_wide.as_posix()}",
            ),
        ]

        rendered = render_video(
            cuts=cuts,
            audio_path=audio_path,
            output_path=output_mp4,
            ass_path=ass_path,
            mode="short",
            target_duration_sec=5.0,
            work_dir=tmp_dir / "work",
        )
        assert rendered.is_file()

        info = probe_rendered_video(rendered)
        assert info["width"] == 1080
        assert info["height"] == 1920
        assert info["has_video"] is True
        assert info["has_audio"] is True
        assert info["file_size_bytes"] > 0
        assert 4.8 <= info["duration_sec"] <= 5.2


def test_single_clip_bypasses_xfade_and_schedule_math():
    from worker.ffmpeg_renderer import compute_xfade_schedule

    prep_1, tr_1 = compute_xfade_schedule([2.0], transition_sec=0.25, total_duration_sec=2.0)
    assert prep_1 == [2.0]
    assert tr_1 == []

    prep_5, tr_5 = compute_xfade_schedule([2.0, 2.0, 2.0, 2.0, 2.0], transition_sec=0.25, total_duration_sec=10.0)
    assert prep_5 == [2.25, 2.25, 2.25, 2.25, 2.0]
    assert [(name, round(dur, 2), round(off, 2)) for name, dur, off in tr_5] == [
        ("fade", 0.25, 2.0),
        ("smoothleft", 0.25, 4.0),
        ("wipeleft", 0.25, 6.0),
        ("dissolve", 0.25, 8.0),
    ]

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        clip = tmp_dir / "single.mp4"
        audio = tmp_dir / "audio.wav"
        out_mp4 = tmp_dir / "single_out.mp4"
        _ffmpeg_generate_clip(clip, color="navy", size="1280x720", duration=3)
        _ffmpeg_generate_audio(audio, duration=2)

        cut = ResolvedCut(
            clip_id="c1",
            celebrity_id="celeb1",
            local_path=clip,
            start_sec=0.0,
            cut_duration_sec=2.0,
            match_reason="tag_match",
            source_r2_key=f"local://{clip.as_posix()}",
        )
        render_video(cuts=[cut], audio_path=audio, output_path=out_mp4, mode="short", target_duration_sec=2.0)
        info = probe_rendered_video(out_mp4)
        assert info["width"] == 1080
        assert info["height"] == 1920
        assert info["has_audio"] is True
        assert 1.8 <= info["duration_sec"] <= 2.2


def test_script_service_and_web_fetcher_filters():
    preserved = generate_script(
        input_type="script",
        title="Ignored title",
        raw_input="  Keep my exact script words here.  ",
    )
    assert preserved == "Keep my exact script words here."

    fallback = generate_script(
        input_type="title",
        title="Stephen Curry Postgame Reaction",
        raw_input="",
        target_duration_sec=50,
        api_key="your_gemini_api_key",
    )
    assert "Stephen Curry Postgame Reaction" in fallback
    assert "[" not in fallback and "**" not in fallback
    assert len(fallback.split()) >= 40

    assert is_allowed_original_video("Stephen Curry Postgame Interview Warriors") is True
    assert is_allowed_original_video("Stephen Curry AI Generated Sora Concept") is False
    assert is_allowed_original_video("NBA 2K26 Deepfake Parody Clip") is False


def test_video_endpoint_and_mark_clips_used_api():
    pytest.importorskip("sqlalchemy")
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        sample_mp4 = tmp_dir / "rendered_final.mp4"
        _ffmpeg_generate_clip(sample_mp4, color="green", size="720x1280", duration=2)

        os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/test_worker.db"
        os.environ["WORKER_SHARED_SECRET"] = "test-worker-secret"
        os.environ["STORAGE_MODE"] = "local"

        from backend.app.config import get_settings

        get_settings.cache_clear()
        from backend.app import database

        database.reconfigure_engine(os.environ["DATABASE_URL"])
        from backend.app.main import app

        try:
            with TestClient(app) as client:
                celeb_resp = client.post("/api/celebrities", json={"name": "Stephen Curry", "category": "NBA"})
                assert celeb_resp.status_code == 201
                celeb_id = celeb_resp.json()["id"]

                presign = client.post(
                    "/api/clips/presign-upload",
                    json={"celebrity_id": celeb_id, "filename": "clip.mp4"},
                )
                assert presign.status_code == 503

                bulk = client.post(
                    "/api/clips/bulk-index",
                    json={
                        "clips": [
                            {
                                "celebrity_name": "Stephen Curry",
                                "category": "NBA",
                                "r2_key": f"local://{sample_mp4.resolve().as_posix()}",
                                "filename": sample_mp4.name,
                                "file_hash": "hash_curry_local_1",
                                "file_size_bytes": sample_mp4.stat().st_size,
                                "duration_sec": 2.0,
                                "width": 720,
                                "height": 1280,
                                "aspect_ratio": "9:16",
                                "source_type": "vault_upload",
                                "tags": ["warriors"],
                            }
                        ]
                    },
                )
                assert bulk.status_code == 200
                clip_id = client.get("/api/clips").json()[0]["id"]

                proj = client.post(
                    "/api/projects",
                    json={
                        "mode": "short",
                        "input_type": "title",
                        "title": "Stephen Curry amazing finish",
                        "raw_input": "Stephen Curry amazing finish",
                    },
                )
                assert proj.status_code == 201
                project_id = proj.json()["id"]

                claim = client.post(
                    "/api/projects/worker/claim?worker_id=qa-worker",
                    headers={"x-worker-token": "test-worker-secret"},
                )
                assert claim.status_code == 200
                job_id = claim.json()["latest_job"]["id"]

                bad_mark = client.post(
                    "/api/clips/worker/mark-used",
                    headers={"x-worker-token": "wrong"},
                    json={"clip_ids": [clip_id]},
                )
                assert bad_mark.status_code == 401

                ok_mark = client.post(
                    "/api/clips/worker/mark-used",
                    headers={"x-worker-token": "test-worker-secret"},
                    json={"clip_ids": [clip_id]},
                )
                assert ok_mark.status_code == 200
                assert ok_mark.json()["updated"] == 1
                assert client.get("/api/clips").json()[0]["usage_count"] == 1

                done = client.post(
                    f"/api/projects/worker/jobs/{job_id}/progress",
                    headers={"x-worker-token": "test-worker-secret"},
                    json={
                        "current_step": "completed",
                        "progress_pct": 100,
                        "status": "completed",
                        "output_r2_key": f"local://{sample_mp4.resolve().as_posix()}",
                    },
                )
                assert done.status_code == 200

                video_resp = client.get(f"/api/projects/{project_id}/video")
                assert video_resp.status_code == 200
                assert video_resp.headers["content-type"].startswith("video/mp4")
                assert video_resp.content == sample_mp4.read_bytes()
        finally:
            database.engine.dispose()


def test_upload_local_clips_endpoint(monkeypatch):
    pytest.importorskip("sqlalchemy")
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        sample_mp4 = tmp_dir / "courtside_clip.mp4"
        _ffmpeg_generate_clip(sample_mp4, color="red", size="1280x720", duration=2)

        os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/test_upload.db"
        os.environ["WORKER_SHARED_SECRET"] = "test-worker-secret"
        os.environ["STORAGE_MODE"] = "local"

        from backend.app.config import get_settings

        get_settings.cache_clear()
        from backend.app import database
        from backend.app.api import clips as clips_api

        monkeypatch.setattr(clips_api, "LOCAL_UPLOAD_ROOT", tmp_dir / "vault_uploads")
        database.reconfigure_engine(os.environ["DATABASE_URL"])
        from backend.app.main import app

        try:
            with TestClient(app) as client:
                celeb_resp = client.post("/api/celebrities", json={"name": "LeBron James", "category": "NBA"})
                assert celeb_resp.status_code == 201
                celeb_id = celeb_resp.json()["id"]

                with sample_mp4.open("rb") as fh:
                    up = client.post(
                        "/api/clips/upload-local",
                        data={"celebrity_id": celeb_id, "tags": "lakers, postgame"},
                        files=[("files", ("postgame_tunnel.mp4", fh, "video/mp4"))],
                    )
                assert up.status_code == 200
                payload = up.json()
                assert payload["uploaded"] == 1
                assert payload["skipped_existing"] == 0
                clip = payload["clips"][0]
                assert clip["r2_key"].startswith("local://")
                assert clip["width"] == 1280
                assert clip["height"] == 720
                assert clip["aspect_ratio"] == "16:9"
                saved_path = Path(clip["r2_key"][len("local://"):])
                assert saved_path.is_file()
                assert "lebron-james" in saved_path.parts
        finally:
            database.engine.dispose()


def test_scan_local_folder_background_endpoint(monkeypatch):
    pytest.importorskip("sqlalchemy")
    import time
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        vault_dir = tmp_dir / "Vault"
        celeb_names = ["LeBron James", "Stephen Curry", "Kevin Durant", "Luka Doncic"]
        for idx, name in enumerate(celeb_names):
            sub = vault_dir / name / "interviews"
            sub.mkdir(parents=True)
            for clip_idx in range(5):
                # Synthetic 1KB MP4 files test zero-ffprobe / zero-read os.scandir throughput cleanly.
                (sub / f"clip_{idx}_{clip_idx}.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"0" * 512)

        probe_dir = tmp_dir / "ProbeVault"
        (probe_dir / "Giannis Antetokounmpo").mkdir(parents=True)
        real_clip = probe_dir / "Giannis Antetokounmpo" / "media_day.mp4"
        _ffmpeg_generate_clip(real_clip, color="green", size="1280x720", duration=2)

        os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/test_scan.db"
        os.environ["WORKER_SHARED_SECRET"] = "test-worker-secret"
        os.environ["STORAGE_MODE"] = "local"

        from backend.app.config import get_settings

        get_settings.cache_clear()
        from backend.app import database
        from backend.app.api import clips as clips_api

        probe_calls: list[Path] = []
        original_probe = clips_api.probe_video_metadata

        def tracked_probe(path: Path):
            probe_calls.append(path)
            return original_probe(path)

        monkeypatch.setattr(clips_api, "probe_video_metadata", tracked_probe)
        database.reconfigure_engine(os.environ["DATABASE_URL"])
        from backend.app.main import app

        try:
            with TestClient(app) as client:
                bad = client.post(
                    "/api/clips/scan-local-folder",
                    json={"folder_path": str(tmp_dir / "does_not_exist"), "category": "NBA"},
                )
                assert bad.status_code == 400

                started = client.post(
                    "/api/clips/scan-local-folder",
                    json={"folder_path": f'"{vault_dir}"', "category": "NBA"},
                )
                assert started.status_code == 202
                scan_id = started.json()["scan_id"]

                status_payload = started.json()
                for _ in range(80):
                    poll = client.get(f"/api/clips/scan-local-folder/{scan_id}")
                    assert poll.status_code == 200
                    status_payload = poll.json()
                    if status_payload["status"] != "running":
                        break
                    time.sleep(0.02)

                assert status_payload["status"] == "completed"
                assert status_payload["total_files_found"] == 20
                assert status_payload["processed_files"] == 20
                assert status_payload["inserted"] == 20
                assert status_payload["skipped_existing"] == 0
                assert status_payload["celebrities_created"] == 4
                assert status_payload["elapsed_ms"] < 2000
                assert len(probe_calls) == 0

                clips = client.get("/api/clips").json()
                assert len(clips) == 20
                assert all(c["r2_key"].startswith("local://") for c in clips)
                assert all(c["duration_sec"] == 0.0 and c["width"] == 0 for c in clips)

                # Re-scan skips existing duplicates instantaneously without ffprobe
                rescan = client.post(
                    "/api/clips/scan-local-folder",
                    json={"folder_path": str(vault_dir), "category": "NBA"},
                )
                assert rescan.status_code == 202
                rescan_id = rescan.json()["scan_id"]
                for _ in range(80):
                    poll2 = client.get(f"/api/clips/scan-local-folder/{rescan_id}")
                    status_payload2 = poll2.json()
                    if status_payload2["status"] != "running":
                        break
                    time.sleep(0.02)

                assert status_payload2["status"] == "completed"
                assert status_payload2["inserted"] == 0
                assert status_payload2["skipped_existing"] == 20
                assert len(probe_calls) == 0

                # Optional probe_metadata=True still works when explicitly requested
                opt_scan = client.post(
                    "/api/clips/scan-local-folder",
                    json={"folder_path": str(probe_dir), "category": "NBA", "probe_metadata": True},
                )
                assert opt_scan.status_code == 202
                opt_id = opt_scan.json()["scan_id"]
                for _ in range(80):
                    opt_poll = client.get(f"/api/clips/scan-local-folder/{opt_id}").json()
                    if opt_poll["status"] != "running":
                        break
                    time.sleep(0.05)

                assert opt_poll["status"] == "completed"
                assert opt_poll["inserted"] == 1
                assert len(probe_calls) == 1
                giannis_clip = [c for c in client.get("/api/clips").json() if c["celebrity_name"] == "Giannis Antetokounmpo"][0]
                assert giannis_clip["width"] == 1280
                assert giannis_clip["height"] == 720
                assert giannis_clip["duration_sec"] > 0
        finally:
            database.engine.dispose()


def test_clip_resolver_lazy_ffprobe_for_zero_duration_local_clips(monkeypatch):
    from backend.app.services.clip_matcher import CelebrityProfile, ClipCandidate
    import worker.clip_resolver as clip_resolver_mod

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        lebron_1 = tmp_dir / "lebron_interview.mp4"
        lebron_2 = tmp_dir / "lebron_tunnel.mp4"
        curry_unused = tmp_dir / "curry_practice.mp4"
        _ffmpeg_generate_clip(lebron_1, color="blue", size="1280x720", duration=6)
        _ffmpeg_generate_clip(lebron_2, color="gold", size="720x1280", duration=6)
        _ffmpeg_generate_clip(curry_unused, color="red", size="1280x720", duration=6)

        catalog = [
            CelebrityProfile(id="c_lebron", name="LeBron James", slug="lebron-james", aliases=["LBJ"]),
            CelebrityProfile(id="c_curry", name="Stephen Curry", slug="stephen-curry", aliases=["Steph"]),
        ]
        zero_duration_clips = [
            ClipCandidate(id="clip_l1", celebrity_id="c_lebron", r2_key=f"local://{lebron_1.resolve().as_posix()}", duration_sec=0.0, tags=["interview"]),
            ClipCandidate(id="clip_l2", celebrity_id="c_lebron", r2_key=f"local://{lebron_2.resolve().as_posix()}", duration_sec=0.0, tags=["tunnel"]),
            ClipCandidate(id="clip_c1", celebrity_id="c_curry", r2_key=f"local://{curry_unused.resolve().as_posix()}", duration_sec=0.0, tags=["practice"]),
        ]

        probed_paths: list[Path] = []
        original_probe = clip_resolver_mod.probe_video_metadata

        def tracked_probe(path: Path):
            probed_paths.append(path)
            return original_probe(path)

        monkeypatch.setattr(clip_resolver_mod, "probe_video_metadata", tracked_probe)

        resolver = clip_resolver_mod.ClipResolver(
            api_base_url="http://127.0.0.1:8000",
            worker_token="test-secret",
            storage_mode="local",
            enable_web_fallback=False,
        )
        monkeypatch.setattr(resolver, "_fetch_catalog_and_clips", lambda: (catalog, zero_duration_clips))

        cuts = resolver.resolve_cuts_for_script(
            script_text="LeBron James reacted strongly in his postgame interview.",
            target_duration_sec=7.0,
            cut_length_sec=3.5,
            title="LeBron James interview breakdown",
        )
        assert len(cuts) == 2
        assert all(c.cut_duration_sec == 3.5 for c in cuts)
        assert set(probed_paths) == {lebron_1.resolve(), lebron_2.resolve()}
        assert curry_unused.resolve() not in probed_paths


def test_delete_project_removes_db_rows_and_local_rendered_mp4(monkeypatch):
    pytest.importorskip("sqlalchemy")
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        renders_dir = tmp_dir / "renders"
        renders_dir.mkdir(parents=True)
        outside_file = tmp_dir / "do_not_delete.mp4"
        _ffmpeg_generate_clip(outside_file, color="purple", size="720x1280", duration=2)

        os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/test_delete.db"
        os.environ["WORKER_SHARED_SECRET"] = "test-worker-secret"
        os.environ["STORAGE_MODE"] = "local"

        from backend.app.config import get_settings

        get_settings.cache_clear()
        from backend.app import database
        from backend.app.api import projects as projects_api
        from backend.app.models import RenderJob

        monkeypatch.setattr(projects_api, "LOCAL_RENDERS_ROOT", renders_dir)
        database.reconfigure_engine(os.environ["DATABASE_URL"])
        from backend.app.main import app

        try:
            with TestClient(app) as client:
                proj = client.post(
                    "/api/projects",
                    json={
                        "mode": "short",
                        "input_type": "title",
                        "title": "Delete Me Project",
                        "raw_input": "Delete Me Project",
                    },
                )
                assert proj.status_code == 201
                project_id = proj.json()["id"]

                rendered_mp4 = renders_dir / f"{project_id}.mp4"
                _ffmpeg_generate_clip(rendered_mp4, color="blue", size="720x1280", duration=2)
                work_dir = renders_dir / f".work_{project_id}"
                work_dir.mkdir(parents=True)
                (work_dir / "captions.ass").write_text("[Script Info]\n", encoding="utf-8")

                claim = client.post(
                    "/api/projects/worker/claim?worker_id=delete-worker",
                    headers={"x-worker-token": "test-worker-secret"},
                )
                assert claim.status_code == 200
                job_id = claim.json()["latest_job"]["id"]

                done = client.post(
                    f"/api/projects/worker/jobs/{job_id}/progress",
                    headers={"x-worker-token": "test-worker-secret"},
                    json={
                        "current_step": "completed",
                        "progress_pct": 100,
                        "status": "completed",
                        "output_r2_key": f"local://{rendered_mp4.resolve().as_posix()}",
                    },
                )
                assert done.status_code == 200
                assert rendered_mp4.is_file()

                deleted = client.delete(f"/api/projects/{project_id}")
                assert deleted.status_code == 200
                assert deleted.json() == {"deleted": True, "project_id": project_id}
                assert not rendered_mp4.exists()
                assert not work_dir.exists()
                assert all(p["id"] != project_id for p in client.get("/api/projects").json())
                assert client.get(f"/api/projects/{project_id}/video").status_code == 404
                assert client.delete(f"/api/projects/{project_id}").status_code == 404

                db = database.SessionLocal()
                try:
                    remaining_jobs = db.execute(
                        select(RenderJob).where(RenderJob.project_id == project_id)
                    ).scalars().all()
                    assert remaining_jobs == []
                finally:
                    db.close()

                # Guard: project pointing outside generated/renders/ never deletes external files
                ext_proj = client.post(
                    "/api/projects",
                    json={
                        "mode": "short",
                        "input_type": "title",
                        "title": "External Safe Project",
                        "raw_input": "External Safe Project",
                    },
                )
                ext_id = ext_proj.json()["id"]
                ext_job = client.post(
                    "/api/projects/worker/claim?worker_id=delete-worker",
                    headers={"x-worker-token": "test-worker-secret"},
                ).json()["latest_job"]["id"]
                client.post(
                    f"/api/projects/worker/jobs/{ext_job}/progress",
                    headers={"x-worker-token": "test-worker-secret"},
                    json={
                        "current_step": "completed",
                        "progress_pct": 100,
                        "status": "completed",
                        "output_r2_key": f"local://{outside_file.resolve().as_posix()}",
                    },
                )
                assert client.delete(f"/api/projects/{ext_id}").status_code == 200
                assert outside_file.is_file()
        finally:
            database.engine.dispose()
