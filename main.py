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
  step4   Translate to Vietnamese (Gemini 1.5 Flash → captions_vn.srt)
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
import subprocess
import sys
from pathlib import Path

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
}


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
    parser.add_argument("--model", default="large-v3",
                        choices=["large-v3", "large-v2", "medium", "small", "base"],
                        help="Whisper model size (default: large-v3)")
    parser.add_argument("--transcriber", default="whisper",
                        choices=["whisper", "deepgram"],
                        help="Transcription provider (default: whisper)")
    parser.add_argument("--output", default="output", metavar="DIR",
                        help="Base output directory (default: ./output)")
    args = parser.parse_args()

    _check_ffmpeg()

    output_base = Path(args.output)
    output_base.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Download ──────────────────────────────────────────────────────
    # We need the video_id before we can clear sentinels, so always run step 1
    # probe to get the ID, then apply --force / --from-step logic.
    from pipeline.step1_download import download
    from pipeline.step2_extract_audio import extract_audio
    from pipeline.step2b_separate_audio import separate_audio
    from pipeline.step3_transcribe import transcribe
    from pipeline.step4_translate import translate
    from pipeline.step5_tts import generate_tts
    from pipeline.step6_compose import compose

    print("=" * 60)
    print("flow-video pipeline")
    print(f"  URL:          {args.url}")
    print(f"  Transcriber:  {args.transcriber}  Model: {args.model}  CRF: {args.crf}")
    print("=" * 60)

    # Step 1 always runs the probe to get video_id (fast, no download if done)
    output_dir = download(args.url, output_base, cookies_file=args.cookies)

    # Now apply --force / --from-step (we have output_dir)
    if args.force:
        print("[main] --force: clearing all sentinels")
        _clear_sentinels_from(output_dir, from_step=1)
        (output_dir / ".step2b.done").unlink(missing_ok=True)
    elif args.from_step is not None:
        print(f"[main] --from-step {args.from_step}: clearing sentinels from step {args.from_step}")
        _clear_sentinels_from(output_dir, from_step=args.from_step)
        if args.from_step <= 3:  # step2b sits between steps 2 and 3
            (output_dir / ".step2b.done").unlink(missing_ok=True)

    # ── Step 2: Extract audio ─────────────────────────────────────────────────
    extract_audio(output_dir)

    # ── Step 2b: Separate vocals / accompaniment ──────────────────────────────
    separate_audio(output_dir)

    # ── Step 3: Transcribe ────────────────────────────────────────────────────
    transcribe(output_dir, model_size=args.model, provider=args.transcriber)

    # ── Step 4: Translate ─────────────────────────────────────────────────────
    translate(output_dir)

    # ── Step 5: TTS ───────────────────────────────────────────────────────────
    generate_tts(output_dir)

    # ── Step 6: Compose ───────────────────────────────────────────────────────
    final_path = compose(output_dir, crf=args.crf)

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
    print(f"  Output: {final_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
