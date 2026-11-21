"""Phase 2 Local PC Render Worker Daemon for AI Shorts Studio v2."""

import argparse
import os
from pathlib import Path
import time
from typing import Optional

from dotenv import load_dotenv
import httpx

from worker.clip_resolver import ClipResolver
from worker.ffmpeg_renderer import get_render_profile, render_video
from worker.script_service import generate_script
from worker.tts_service import synthesize_narration


def _report_progress(
    api_base_url: str,
    job_id: str,
    worker_token: str,
    current_step: str,
    progress_pct: int,
    status: str = "processing",
    final_script: Optional[str] = None,
    output_r2_key: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    payload: dict = {
        "current_step": current_step,
        "progress_pct": progress_pct,
        "status": status,
    }
    if final_script is not None:
        payload["final_script"] = final_script
    if output_r2_key is not None:
        payload["output_r2_key"] = output_r2_key
    if error_message is not None:
        payload["error_message"] = error_message[:1500]

    with httpx.Client(timeout=30) as client:
        resp = client.post(
            f"{api_base_url.rstrip('/')}/api/projects/worker/jobs/{job_id}/progress",
            headers={"x-worker-token": worker_token},
            json=payload,
        )
        resp.raise_for_status()


def process_project(
    project: dict,
    api_base_url: str,
    worker_token: str,
    storage_mode: str = "local",
    gemini_api_key: Optional[str] = None,
    renders_dir: Path = Path("generated/renders"),
    enable_web_fallback: bool = True,
) -> Path:
    """Executes the full pipeline for one claimed render job."""
    job = project.get("latest_job") or {}
    job_id = job["id"]
    project_id = project["id"]
    mode = project.get("mode") or "short"
    profile = get_render_profile(mode)
    work_dir = renders_dir / f".work_{project_id}"
    work_dir.mkdir(parents=True, exist_ok=True)
    output_path = renders_dir / f"{project_id}.mp4"

    resolver = ClipResolver(
        api_base_url=api_base_url,
        worker_token=worker_token,
        storage_mode=storage_mode,
        enable_web_fallback=enable_web_fallback,
    )

    try:
        # 1. Script
        _report_progress(api_base_url, job_id, worker_token, "script", 15)
        script_text = generate_script(
            input_type=project.get("input_type", "title"),
            title=project.get("title", ""),
            raw_input=project.get("raw_input", ""),
            target_duration_sec=int(project.get("target_duration_sec") or 55),
            api_key=gemini_api_key,
        )

        # 2. Audio + WordBoundary Captions
        _report_progress(api_base_url, job_id, worker_token, "audio", 35, final_script=script_text)
        narration = synthesize_narration(
            script_text=script_text,
            output_dir=work_dir,
            voice=project.get("voice_name") or "en-US-ChristopherNeural",
            max_words_per_chunk=3,
            play_res=(profile.width, profile.height),
        )

        # 3. Clips
        _report_progress(api_base_url, job_id, worker_token, "clips", 55)
        cuts = resolver.resolve_cuts_for_script(
            script_text=script_text,
            target_duration_sec=narration.duration_sec,
            cut_length_sec=profile.cut_length_sec,
            project_detected_names=project.get("detected_celebrities") or [],
            title=project.get("title", ""),
        )

        # 4. Captions ready
        _report_progress(api_base_url, job_id, worker_token, "captions", 70)

        # 5. Render
        _report_progress(api_base_url, job_id, worker_token, "render", 85)
        rendered_mp4 = render_video(
            cuts=cuts,
            audio_path=narration.audio_path,
            output_path=output_path,
            ass_path=narration.ass_path,
            mode=mode,
            target_duration_sec=narration.duration_sec,
            work_dir=work_dir,
        )

        if (storage_mode or "local").strip().lower() == "r2":
            from backend.app.services.r2_storage import R2StorageService

            output_key = f"renders/{project_id}.mp4"
            R2StorageService().upload_file_multipart(rendered_mp4, output_key)
        else:
            output_key = f"local://{rendered_mp4.resolve().as_posix()}"

        resolver.mark_clips_used([c.clip_id for c in cuts])
        _report_progress(
            api_base_url,
            job_id,
            worker_token,
            "completed",
            100,
            status="completed",
            final_script=script_text,
            output_r2_key=output_key,
        )
        return rendered_mp4
    except Exception as exc:
        try:
            _report_progress(
                api_base_url,
                job_id,
                worker_token,
                "failed",
                100,
                status="failed",
                error_message=str(exc),
            )
        except Exception:
            pass
        raise


def run_worker_loop(
    api_base_url: str,
    worker_id: str,
    poll_interval: float = 5.0,
    run_once: bool = False,
    enable_web_fallback: bool = True,
) -> int:
    """Polls backend /api/projects/worker/claim and renders queued jobs locally."""
    load_dotenv(override=False)
    worker_token = os.environ.get("WORKER_SHARED_SECRET", "dev-worker-secret")
    storage_mode = os.environ.get("STORAGE_MODE", "local")
    gemini_api_key = os.environ.get("GEMINI_API_KEY", "")

    processed = 0
    while True:
        with httpx.Client(timeout=30) as client:
            claim_resp = client.post(
                f"{api_base_url.rstrip('/')}/api/projects/worker/claim",
                params={"worker_id": worker_id},
                headers={"x-worker-token": worker_token},
            )
            claim_resp.raise_for_status()
            project = claim_resp.json()

        if project:
            print(f"[worker:{worker_id}] Claimed project {project['id']} ({project['title']})")
            output = process_project(
                project=project,
                api_base_url=api_base_url,
                worker_token=worker_token,
                storage_mode=storage_mode,
                gemini_api_key=gemini_api_key,
                enable_web_fallback=enable_web_fallback,
            )
            print(f"[worker:{worker_id}] Completed render -> {output}")
            processed += 1
        elif run_once:
            break

        if run_once:
            break
        time.sleep(poll_interval)

    return processed


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Shorts Studio v2 — Phase 2 Local PC Render Worker")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="Backend FastAPI base URL")
    parser.add_argument("--worker-id", default="local-pc-worker", help="Worker identifier saved on RenderJob")
    parser.add_argument("--poll-interval", type=float, default=5.0, help="Seconds between queue polls")
    parser.add_argument("--once", action="store_true", help="Claim at most one job and exit")
    parser.add_argument("--disable-web-fallback", action="store_true", help="Disable yt-dlp web clip fallback")
    args = parser.parse_args()

    run_worker_loop(
        api_base_url=args.api_url,
        worker_id=args.worker_id,
        poll_interval=args.poll_interval,
        run_once=args.once,
        enable_web_fallback=not args.disable_web_fallback,
    )


if __name__ == "__main__":
    main()
