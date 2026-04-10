#!/usr/bin/env python3
"""
flow-video v2 — Multi-Type Video Re-Up Pipeline
================================================
Extends the original pipeline with automatic video type detection and
per-type processing workflows.

Video types:
  music      Group 1 — Dance, DIY, Pets: keep original audio, translate captions
  narration  Group 2 — Story, Podcast, News: full voice replacement (default)
  silent     Group 3 — ASMR, Cooking: keep ambient sounds, add captions
  reaction   Group 4 — Reaction/Commentary: PiP layout + user commentary audio
  hybrid     Group 5 — Vlog, Review: music + voice (uses narration pipeline)

Usage:
  python flow_v2/main_v2.py <url> [options]

Options:
  --video-type TYPE   Override auto-classification (music|narration|silent|reaction|hybrid)
  --from-step N       Resume from step N (1–6), clears sentinels for N and later
  --force             Re-run all steps (clears all sentinels)
  --crf N             Output video quality, default 23 (lower = better, larger)
  --cookies FILE      Netscape cookie file for login-required videos
  --model SIZE        Whisper model size: large-v3 (default), medium, small
  --transcriber NAME  Transcription provider: whisper (default) or deepgram
  --output DIR        Base output directory, default ./output

The original main.py and pipeline/ directory are NOT modified.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Ensure project root is on sys.path when running as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()


# ── Preflight ─────────────────────────────────────────────────────────────────

def _check_ffmpeg() -> None:
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
    if result.returncode != 0:
        print("ERROR: ffmpeg not found. Install it first:")
        print("  macOS:  brew install ffmpeg")
        print("  Ubuntu: sudo apt install ffmpeg")
        sys.exit(1)


# ── Sentinel helpers ──────────────────────────────────────────────────────────

_NUMBERED_SENTINELS = {
    1: ".step1.done",
    2: ".step2.done",
    3: ".step3.done",
    4: ".step4.done",
    5: ".step5.done",
    6: ".step6.done",
}

_SENTINEL_1B = ".step1b.done"


def _clear_sentinels_from(output_dir: Path, from_step: int) -> None:
    for step, name in _NUMBERED_SENTINELS.items():
        if step >= from_step:
            sentinel = output_dir / name
            if sentinel.exists():
                sentinel.unlink()
                print(f"  Cleared sentinel for step {step}")
    if from_step <= 2:
        (output_dir / _SENTINEL_1B).unlink(missing_ok=True)
    # step2b sits between steps 2 and 3
    if from_step <= 3:
        (output_dir / ".step2b.done").unlink(missing_ok=True)
    # workflow-specific compose sentinels
    if from_step <= 6:
        for extra in (".step6m.done", ".step6r.done",
                      ".step6.youtube.done", ".step6.tiktok.done"):
            (output_dir / extra).unlink(missing_ok=True)


def _clear_classify_sentinel(output_dir: Path) -> None:
    (output_dir / ".stepC.done").unlink(missing_ok=True)
    (output_dir / "classification.json").unlink(missing_ok=True)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="flow-video v2 — multi-type video re-up pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", help="Video URL (any yt-dlp supported platform)")
    parser.add_argument(
        "--video-type", default=None,
        choices=["music", "narration", "silent", "reaction", "hybrid"],
        help="Override auto-classification",
    )
    parser.add_argument("--from-step", type=int, metavar="N", default=None,
                        help="Re-run from step N onward (clears sentinels)")
    parser.add_argument("--force", action="store_true",
                        help="Re-run all steps (clears all sentinels)")
    parser.add_argument("--crf", type=int, default=23,
                        help="Output video CRF quality (default: 23)")
    parser.add_argument("--cookies", metavar="FILE", default=None,
                        help="Netscape cookie file for login-required videos")
    parser.add_argument("--model", default="large-v3",
                        choices=["large-v3", "large-v2", "medium", "small", "base"],
                        help="Whisper model size (default: large-v3)")
    parser.add_argument("--transcriber", default="whisper",
                        choices=["whisper", "deepgram"],
                        help="Transcription provider (default: whisper)")
    parser.add_argument("--tts-provider", default="edge_tts",
                        choices=["edge_tts", "elevenlabs"],
                        help="TTS provider for step 5 (default: edge_tts)")
    parser.add_argument("--translator", default="gemini",
                        choices=["gemini", "claude"],
                        help="Translation provider for step 4 (default: gemini)")
    parser.add_argument("--platform", default="youtube",
                        choices=["youtube", "tiktok", "both"],
                        help="Output platform profile (default: youtube)")
    parser.add_argument("--tiktok-crop-x", type=int, default=None, metavar="X",
                        dest="tiktok_crop_x",
                        help="Horizontal pixel offset for TikTok 9:16 crop (default: center)")
    parser.add_argument("--output", default="output", metavar="DIR",
                        help="Base output directory (default: ./output)")
    args = parser.parse_args()

    _check_ffmpeg()

    output_base = Path(args.output)
    output_base.mkdir(parents=True, exist_ok=True)

    from pipeline.step1_download import download
    from pipeline.step1b_scenes import detect_scenes
    from pipeline.step2_extract_audio import extract_audio
    from flow_v2.classifier import classify, VideoType

    print("=" * 60)
    print("flow-video v2")
    print(f"  URL:  {args.url}")
    print(f"  Type: {args.video_type or 'auto-detect'}")
    print(f"  Transcriber: {args.transcriber}  Model: {args.model}  Translator: {args.translator}  CRF: {args.crf}  TTS: {args.tts_provider}  Platform: {args.platform}")
    print("=" * 60)

    # Step 1: always probe to get video_id (fast if already downloaded)
    output_dir = download(args.url, output_base, cookies_file=args.cookies)

    # Apply --force / --from-step AFTER we have output_dir
    if args.force:
        print("[main] --force: clearing all sentinels")
        _clear_sentinels_from(output_dir, from_step=1)
        (output_dir / _SENTINEL_1B).unlink(missing_ok=True)
        _clear_classify_sentinel(output_dir)
    elif args.from_step is not None:
        print(f"[main] --from-step {args.from_step}: clearing sentinels")
        _clear_sentinels_from(output_dir, from_step=args.from_step)
        if args.from_step <= 2:
            _clear_classify_sentinel(output_dir)

    # Step 1b: detect scene cuts (writes scenes.json; optional for downstream steps)
    detect_scenes(output_dir)

    # Step 2: all workflows need audio.wav
    extract_audio(output_dir)

    # Classify (or use manual override)
    if args.video_type:
        video_type = VideoType(args.video_type)
        print(f"[main] Video type: {video_type.value} (manual override)")
    else:
        video_type = classify(output_dir)
        print(f"[main] Video type: {video_type.value} (auto-detected)")

    # Route to workflow
    if video_type in (VideoType.NARRATION, VideoType.HYBRID):
        from flow_v2.workflows.narration import run
    elif video_type == VideoType.MUSIC_VISUAL:
        from flow_v2.workflows.music_visual import run
    elif video_type == VideoType.SILENT:
        from flow_v2.workflows.silent_ambient import run
    elif video_type == VideoType.REACTION:
        from flow_v2.workflows.reaction import run
    else:
        from flow_v2.workflows.narration import run  # safe fallback

    print(f"[main] Running workflow: {video_type.value}")
    final_path = run(output_dir, args)

    # Summary
    metadata_path = output_dir / "metadata.json"
    title = ""
    if metadata_path.exists():
        title = json.loads(metadata_path.read_text()).get("title", "")

    print()
    print("=" * 60)
    print("DONE")
    if title:
        print(f"  Title:  {title}")
    if final_path:
        print(f"  Output: {final_path}")
    else:
        print("  Output: (pending user action — see instructions above)")
    print("=" * 60)


if __name__ == "__main__":
    main()
