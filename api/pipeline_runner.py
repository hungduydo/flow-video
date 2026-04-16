"""
pipeline_runner.py
==================
Wraps the flow-video pipeline (main.py logic) for background execution inside
the API. Each job runs in a ThreadPoolExecutor thread.

Log capture: contextlib.redirect_stdout/stderr into a per-job log buffer so
that all pipeline print() calls are stored and retrievable via the API.
subprocess calls (ffmpeg, demucs, yt-dlp) still write to OS-level stdout —
that's acceptable and expected.
"""
from __future__ import annotations

import contextlib
import io
import traceback
from datetime import datetime
from pathlib import Path

from .job_manager import Job


# ── Sentinel constants (mirrored from main.py) ────────────────────────────────

SENTINELS = {
    1: ".step1.done",
    2: ".step2.done",
    3: ".step3.done",
    4: ".step4.done",
    5: ".step5.done",
    6: ".step6.done",
    7: ".step7.done",
}

SENTINEL_1B = ".step1b.done"
SENTINEL_1C = ".step1c.done"


# ── Exceptions ────────────────────────────────────────────────────────────────

class PipelineCancelledError(Exception):
    pass


# ── Log writer ────────────────────────────────────────────────────────────────

class _JobLogWriter(io.RawIOBase):
    """Redirects print() output into job.log_buffer."""

    def __init__(self, job: Job) -> None:
        self._job = job

    def write(self, b: bytes | str) -> int:  # type: ignore[override]
        if isinstance(b, bytes):
            s = b.decode("utf-8", errors="replace")
        else:
            s = b
        if s.strip():
            self._job.append_log(s.rstrip("\n"))
        return len(b)

    def readable(self) -> bool:
        return False

    def writable(self) -> bool:
        return True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _update_step(job: Job, step: int | str, name: str) -> None:
    job.current_step = step
    job.current_step_name = name
    job.append_log(f"[API] Starting step {step}: {name}")


def _check_cancel(job: Job) -> None:
    if job.cancel_event.is_set():
        raise PipelineCancelledError("Cancelled by user")


def _clear_sentinels_from(output_dir: Path, from_step: int) -> None:
    for step, name in SENTINELS.items():
        if step >= from_step:
            sentinel = output_dir / name
            if sentinel.exists():
                sentinel.unlink()
                print(f"  Cleared sentinel for step {step}")


def _apply_sentinel_clearing(output_dir: Path, force: bool, from_step: int | None) -> None:
    """Mirror of main.py lines 209–234."""
    if force:
        print("[API] --force: clearing all sentinels")
        _clear_sentinels_from(output_dir, from_step=1)
        for name in [
            SENTINEL_1B, SENTINEL_1C,
            ".step2b.done",
            ".step5a.done", ".step5b.done",
            ".step6.youtube.done", ".step6.tiktok.done",
        ]:
            (output_dir / name).unlink(missing_ok=True)
    elif from_step is not None:
        print(f"[API] --from-step {from_step}: clearing sentinels from step {from_step}")
        _clear_sentinels_from(output_dir, from_step=from_step)
        if from_step <= 2:
            (output_dir / SENTINEL_1B).unlink(missing_ok=True)
            (output_dir / SENTINEL_1C).unlink(missing_ok=True)
        if from_step <= 3:
            (output_dir / ".step2b.done").unlink(missing_ok=True)
        if from_step <= 5:
            (output_dir / ".step5a.done").unlink(missing_ok=True)
            (output_dir / ".step5b.done").unlink(missing_ok=True)
        if from_step <= 6:
            (output_dir / ".step6.youtube.done").unlink(missing_ok=True)
            (output_dir / ".step6.tiktok.done").unlink(missing_ok=True)
        if from_step <= 7:
            (output_dir / ".step7.done").unlink(missing_ok=True)


# ── Pipeline execution ────────────────────────────────────────────────────────

def run_pipeline(job: Job) -> None:
    """
    Execute the full pipeline for a job. Mirrors main.py's step sequence.
    Must be called in a background thread (all steps are blocking).
    """
    from pipeline.step1_download.main import download
    from pipeline.step1b_scenes.main import detect_scenes
    from pipeline.step_remove_logo.main import clean as clean_video
    from pipeline.step2_extract_audio.main import extract_audio
    from pipeline.step2b_separate_audio.main import separate_audio
    from pipeline.step3_transcribe.main import transcribe
    from pipeline.step4_translate.main import translate
    from pipeline.step5_tts.main import generate_tts
    from pipeline.step6_compose.main import compose
    from pipeline.step7_banner.main import banner

    req = job.request
    output_base = Path(req.output_dir)
    output_base.mkdir(parents=True, exist_ok=True)

    # Step 1: Download — always runs (fast probe if already done)
    _update_step(job, 1, "download")
    _check_cancel(job)
    output_dir = download(req.url, output_base, cookies_file=req.cookies_file)
    job.video_id = output_dir.name
    job.output_dir = output_dir

    # Apply force / from_step sentinel clearing now that we have output_dir
    _apply_sentinel_clearing(output_dir, req.force, req.from_step)

    # Step 1b: Scene detection
    _update_step(job, "1b", "detect_scenes")
    _check_cancel(job)
    detect_scenes(output_dir)

    # Step 1c: Logo / watermark removal
    _update_step(job, "1c", "clean_video")
    _check_cancel(job)
    clean_video(output_dir)

    # Step 2: Extract audio
    _update_step(job, 2, "extract_audio")
    _check_cancel(job)
    extract_audio(output_dir)

    # Step 2b: Vocal / accompaniment separation
    _update_step(job, "2b", "separate_audio")
    _check_cancel(job)
    separate_audio(output_dir)

    # Step 3: Transcribe (Chinese)
    _update_step(job, 3, "transcribe")
    _check_cancel(job)
    transcribe(output_dir, model_size=req.model, provider=req.transcriber)

    # Step 4: Translate → Vietnamese
    _update_step(job, 4, "translate")
    _check_cancel(job)
    translate(output_dir, provider=req.translator)

    # Step 5: TTS generation
    _update_step(job, 5, "tts")
    _check_cancel(job)
    generate_tts(output_dir, provider=req.tts_provider)

    # Step 6: Video composition
    _update_step(job, 6, "compose")
    _check_cancel(job)
    compose(
        output_dir,
        crf=req.crf,
        platform=req.platform,
        tiktok_crop_x=req.tiktok_crop_x,
        subtitle_position="auto",
        show_subtitle=req.show_subtitle,
    )

    # Step 7: Banner thumbnails
    _update_step(job, 7, "banner")
    _check_cancel(job)
    banner(output_dir, platform=req.platform)


# ── Thread entry point ────────────────────────────────────────────────────────

def run_job(job: Job) -> None:
    """
    Top-level function submitted to ThreadPoolExecutor.
    Manages job lifecycle (status, timestamps, error capture).
    """
    job.status = "running"
    job.started_at = datetime.utcnow()

    raw_writer = _JobLogWriter(job)
    text_writer = io.TextIOWrapper(raw_writer, line_buffering=True)

    try:
        with contextlib.redirect_stdout(text_writer), contextlib.redirect_stderr(text_writer):
            run_pipeline(job)
        job.status = "completed"
        job.current_step = None
        job.current_step_name = None
    except PipelineCancelledError:
        job.status = "failed"
        job.failed_step = job.current_step
        job.failed_step_name = job.current_step_name
        job.error = "Cancelled by user"
        job.append_log("[API] Job cancelled by user")
    except Exception:
        tb = traceback.format_exc()
        job.status = "failed"
        job.failed_step = job.current_step
        job.failed_step_name = job.current_step_name
        job.error = tb
        job.append_log(f"[ERROR] {tb}")
    finally:
        job.finished_at = datetime.utcnow()
        try:
            text_writer.flush()
        except Exception:
            pass
