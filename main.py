#!/usr/bin/env python3
"""
flow-video — Bilibili Re-Up Pipeline
=====================================
Converts a Bilibili video URL into a re-dubbed Vietnamese video with
burned-in captions.

Pipeline:
  step1   Download video (yt-dlp)
  step2   Extract audio (ffmpeg → 16 kHz mono WAV)
  step2b  Separate vocals / accompaniment (Spleeter 2stems)
  step3   Transcribe Chinese speech (faster-whisper or Deepgram → captions_cn.srt)
  step4   Translate to Vietnamese (Gemini 2.0 Flash → captions_vn.srt)
  step5   Generate Vietnamese TTS + sync to timestamps (edge-tts + atempo + amix)
  step6   Compose final video (ffmpeg: watermark crop + dub + captions)

Usage:
  python main.py <bilibili_url> [options]

Options:
  --from-step N   Resume from step N (1–6), clears sentinels for N and later
  --force         Re-run all steps (clears all sentinels)
  --crf N         Output video quality, default 23 (lower = better, larger)
  --cookies FILE  Netscape cookie file for login-required Bilibili videos
  --model SIZE        Whisper model size: large-v3 (default), medium, small
  --transcriber NAME  Transcription provider: whisper (default) or deepgram
  --output DIR        Base output directory, default ./output
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


# ── Interactive chooser ───────────────────────────────────────────────────────

def _choose(prompt: str, options: list[str], default: str) -> str:
    """Show a numbered menu and return the chosen option."""
    print(f"\n{prompt}")
    for i, opt in enumerate(options, 1):
        marker = " (default)" if opt == default else ""
        print(f"  {i}) {opt}{marker}")
    while True:
        raw = input(f"  Choice [1-{len(options)}, Enter={default}]: ").strip()
        if raw == "":
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print(f"  Please enter a number between 1 and {len(options)}.")

# Must be set before grpcio is imported (google-generativeai pulls it in at step 4).
# Without this, gRPC's at-fork handler fires a FATAL check when subprocess.run()
# calls fork() in step 5, crashing the child process before ffmpeg can exec.
os.environ.setdefault("GRPC_ENABLE_FORK_SUPPORT", "1")
os.environ.setdefault("GRPC_POLL_STRATEGY", "poll")

from dotenv import load_dotenv

load_dotenv()


# ── Preflight checks ─────────────────────────────────────────────────────────

def _check_ffmpeg() -> None:
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
    if result.returncode != 0:
        print("ERROR: ffmpeg not found. Install it first:")
        print("  macOS:  brew install ffmpeg")
        print("  Ubuntu: sudo apt install ffmpeg")
        sys.exit(1)


# ── Sentinel helpers ──────────────────────────────────────────────────────────

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


def _clear_sentinels_from(output_dir: Path, from_step: int) -> None:
    for step, name in SENTINELS.items():
        if step >= from_step:
            sentinel = output_dir / name
            if sentinel.exists():
                sentinel.unlink()
                print(f"  Cleared sentinel for step {step}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bilibili → Vietnamese re-dub pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", help="Bilibili video URL")
    parser.add_argument("--from-step", type=int, metavar="N", default=None,
                        help="Re-run from step N onward (clears sentinels)")
    parser.add_argument("--force", action="store_true",
                        help="Re-run all steps (clears all sentinels)")
    parser.add_argument("--crf", type=int, default=23,
                        help="Output video CRF quality (default: 23)")
    parser.add_argument("--cookies", metavar="FILE", default=None,
                        help="Netscape cookie file for Bilibili login")
    parser.add_argument("--model", default=None,
                        choices=["large-v3", "large-v2", "medium", "small", "base"],
                        help="Whisper model size (default: large-v3; prompted if omitted)")
    parser.add_argument("--transcriber", default=None,
                        choices=["whisper", "deepgram"],
                        help="Transcription provider (prompted if omitted)")
    parser.add_argument("--tts-provider", default=None,
                        choices=["edge_tts", "elevenlabs"],
                        help="TTS provider for step 5 (prompted if omitted)")
    parser.add_argument("--translator", default=None,
                        choices=["gemini", "claude", "ollama_cloud", "ollama"],
                        help="Translation provider for step 4 (prompted if omitted)")
    parser.add_argument("--platform", default=None,
                        choices=["youtube", "tiktok", "both"],
                        help="Output platform profile: youtube (16:9), tiktok (9:16 crop), "
                             "both (prompted if omitted)")
    parser.add_argument("--no-subtitle", action="store_false", dest="show_subtitle", default=None,
                        help="Disable burned-in subtitles in the output video")
    parser.add_argument("--tiktok-crop-x", type=int, default=None, metavar="X",
                        dest="tiktok_crop_x",
                        help="Horizontal pixel offset for TikTok 9:16 crop (default: center). "
                             "Use when the subject is off-center in the frame.")
    parser.add_argument("--output", default="output", metavar="DIR",
                        help="Base output directory (default: ./output)")
    args = parser.parse_args()

    # ── Interactive prompts for unspecified options ───────────────────────────
    if sys.stdin.isatty():
        if args.transcriber is None:
            args.transcriber = _choose(
                "Transcription provider:", ["whisper", "deepgram"], "whisper"
            )
        if args.transcriber == "whisper" and args.model is None:
            args.model = _choose(
                "Whisper model size:", ["large-v3", "large-v2", "medium", "small", "base"], "large-v3"
            )
        if args.tts_provider is None:
            args.tts_provider = _choose(
                "TTS provider:", ["edge_tts", "elevenlabs"], "edge_tts"
            )
        if args.translator is None:
            args.translator = _choose(
                "Translation provider:", ["gemini", "claude", "ollama_cloud", "ollama"], "gemini"
            )
        if args.platform is None:
            args.platform = _choose(
                "Output platform:", ["youtube", "tiktok", "both"], "youtube"
            )
        if args.show_subtitle is None:
            choice = _choose(
                "Show subtitles in video?", ["yes", "no"], "yes"
            )
            args.show_subtitle = choice == "yes"
    else:
        # Non-interactive: fall back to defaults
        args.transcriber = args.transcriber or "whisper"
        args.model = args.model or "large-v3"
        args.tts_provider = args.tts_provider or "edge_tts"
        args.translator = args.translator or "gemini"
        args.platform = args.platform or "youtube"
        if args.show_subtitle is None:
            args.show_subtitle = True

    _check_ffmpeg()

    output_base = Path(args.output)
    output_base.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Download ──────────────────────────────────────────────────────
    # We need the video_id before we can clear sentinels, so always run step 1
    # probe to get the ID, then apply --force / --from-step logic.
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

    print("=" * 60)
    print("flow-video pipeline")
    print(f"  URL:          {args.url}")
    print(f"  Transcriber:  {args.transcriber}  Model: {args.model}  Translator: {args.translator}  CRF: {args.crf}  TTS: {args.tts_provider}  Platform: {args.platform}")
    print("=" * 60)

    # Step 1 always runs the probe to get video_id (fast, no download if done)
    output_dir = download(args.url, output_base, cookies_file=args.cookies)

    # Now apply --force / --from-step (we have output_dir)
    if args.force:
        print("[main] --force: clearing all sentinels")
        _clear_sentinels_from(output_dir, from_step=1)
        (output_dir / SENTINEL_1B).unlink(missing_ok=True)
        (output_dir / SENTINEL_1C).unlink(missing_ok=True)
        (output_dir / ".step2b.done").unlink(missing_ok=True)
        (output_dir / ".step5a.done").unlink(missing_ok=True)
        (output_dir / ".step5b.done").unlink(missing_ok=True)
        (output_dir / ".step6.youtube.done").unlink(missing_ok=True)
        (output_dir / ".step6.tiktok.done").unlink(missing_ok=True)
    elif args.from_step is not None:
        print(f"[main] --from-step {args.from_step}: clearing sentinels from step {args.from_step}")
        _clear_sentinels_from(output_dir, from_step=args.from_step)
        if args.from_step <= 2:
            (output_dir / SENTINEL_1B).unlink(missing_ok=True)
            (output_dir / SENTINEL_1C).unlink(missing_ok=True)
        if args.from_step <= 3:  # step2b sits between steps 2 and 3
            (output_dir / ".step2b.done").unlink(missing_ok=True)
        if args.from_step <= 5:
            (output_dir / ".step5a.done").unlink(missing_ok=True)
            (output_dir / ".step5b.done").unlink(missing_ok=True)
        if args.from_step <= 6:
            (output_dir / ".step6.youtube.done").unlink(missing_ok=True)
            (output_dir / ".step6.tiktok.done").unlink(missing_ok=True)
        if args.from_step <= 7:
            (output_dir / ".step7.done").unlink(missing_ok=True)

    # ── Step 1b: Detect scenes ────────────────────────────────────────────────
    detect_scenes(output_dir)

    # ── Step 1c: Detect + remove logos and burned-in subtitles ───────────────
    clean_video(output_dir)

    # ── Step 2: Extract audio ─────────────────────────────────────────────────
    extract_audio(output_dir)

    # ── Step 2b: Separate vocals / accompaniment ──────────────────────────────
    separate_audio(output_dir)

    # ── Step 3: Transcribe ────────────────────────────────────────────────────
    transcribe(output_dir, model_size=args.model, provider=args.transcriber)

    # ── Step 4: Translate ─────────────────────────────────────────────────────
    translate(output_dir, provider=args.translator)

    # ── Step 5: TTS ───────────────────────────────────────────────────────────
    generate_tts(output_dir, provider=args.tts_provider)

    # ── Step 6: Compose ───────────────────────────────────────────────────────
    final_path = compose(
        output_dir,
        crf=args.crf,
        platform=args.platform,
        tiktok_crop_x=args.tiktok_crop_x,
        subtitle_position="auto",
        show_subtitle=args.show_subtitle,
    )

    # ── Step 7: Banner thumbnails ─────────────────────────────────────────────
    banner(output_dir, platform=args.platform)

    # ── Done ──────────────────────────────────────────────────────────────────
    metadata_path = output_dir / "metadata.json"
    title = ""
    if metadata_path.exists():
        title = json.loads(metadata_path.read_text()).get("title", "")

    print()
    print("=" * 60)
    print("DONE")
    if title:
        print(f"  Title:  {title}")
    print(f"  Video:   {final_path}")
    print(f"  Banner:  {output_dir / 'banner_youtube.jpg'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
