import argparse
import os
import sys
from pathlib import Path

import cv2
import numpy as np

from .main import detect_watermark_regions, detect_watermark_regions_llm, remove_logo


# Colours for up to 4 detected regions (BGR)
_COLOURS = [
    (0,   255,  0),    # green
    (0,   128, 255),   # orange
    (255,  0,   0),    # blue
    (0,   0,   255),   # red
]


def _draw_debug_frame(input_path: Path, regions: list, out_path: Path) -> None:
    """Extract a mid-video frame, draw detected rectangles, save to out_path."""
    cap = cv2.VideoCapture(str(input_path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    # Use frame at 20% into the video so logos are usually visible
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * 0.20))
    ok, frame = cap.read()
    cap.release()

    if not ok:
        print("[remove_logo] Warning: could not read frame for debug image", file=sys.stderr)
        return

    for i, (corner, x, y, w, h) in enumerate(regions):
        colour = _COLOURS[i % len(_COLOURS)]
        # Draw filled semi-transparent rectangle
        overlay = frame.copy()
        cv2.rectangle(overlay, (x, y), (x + w - 1, y + h - 1), colour, -1)
        frame = cv2.addWeighted(overlay, 0.25, frame, 0.75, 0)
        # Draw solid border
        cv2.rectangle(frame, (x, y), (x + w - 1, y + h - 1), colour, 3)
        # Label (corner name + size)
        label = f"{corner}  {w}x{h}"
        lx = x + 6
        ly = y + 26 if y + 26 < y + h else y + h - 6
        cv2.putText(frame, label, (lx, ly),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame, label, (lx, ly),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, colour,   1, cv2.LINE_AA)

    cv2.imwrite(str(out_path), frame)
    print(f"[remove_logo] Debug frame saved → {out_path}")


def main() -> None:
    default_ollama_url = os.environ.get("OLLAMA_URL", "https://ollama.com")
    default_api_key    = os.environ.get("OLLAMA_API_KEY", "")

    parser = argparse.ArgumentParser(
        description="Remove persistent corner logo/watermark from a video.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m pipeline.step_remove_logo input.mp4
  python -m pipeline.step_remove_logo input.mp4 output_clean.mp4
  python -m pipeline.step_remove_logo input.mp4 --quality high
  python -m pipeline.step_remove_logo input.mp4 --detect-only
  python -m pipeline.step_remove_logo input.mp4 --detect-only --debug --verbose

  # LLM detection via Ollama
  python -m pipeline.step_remove_logo input.mp4 --provider llm
  python -m pipeline.step_remove_logo input.mp4 --provider llm --model llava:13b
  python -m pipeline.step_remove_logo input.mp4 --provider llm --ollama-url http://my-server:11434
  OLLAMA_URL=http://my-server:11434 python -m pipeline.step_remove_logo input.mp4 --provider llm
""",
    )
    parser.add_argument("input", help="Input video path")
    parser.add_argument("output", nargs="?", default=None,
                        help="Output video path (default: {stem}_clean.mp4)")
    parser.add_argument(
        "--quality", choices=["fast", "high"], default="fast",
        help="fast=ffmpeg filters (default), high=OpenCV TELEA inpainting",
    )
    parser.add_argument(
        "--provider", choices=["cv", "llm"], default="cv",
        help="Detection provider: cv=pixel-variance (default), llm=Ollama vision model",
    )
    parser.add_argument(
        "--model", default="gemini-3-flash-preview:cloud",
        help="Ollama model name for --provider llm (default: gemini-3-flash-preview:cloud)",
    )
    parser.add_argument(
        "--ollama-url", default=default_ollama_url,
        help=f"Ollama base URL (default: {default_ollama_url}, or set OLLAMA_URL env var)",
    )
    parser.add_argument(
        "--ollama-api-key", default=default_api_key or None,
        help="Ollama Cloud API key (or set OLLAMA_API_KEY env var)",
    )
    parser.add_argument(
        "--detect-only", action="store_true",
        help="Only detect watermark regions, do not process video",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="With --detect-only: save a frame with detected rectangles drawn on it",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print per-corner detection scores and threshold comparisons",
    )

    args = parser.parse_args()
    input_path = Path(args.input)

    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    if args.detect_only:
        print(f"[remove_logo] Detecting watermarks in {input_path.name} "
              f"(provider={args.provider!r}) …")
        if args.provider == "llm":
            results = detect_watermark_regions_llm(
                input_path,
                ollama_url=args.ollama_url,
                model=args.model,
                api_key=args.ollama_api_key,
                verbose=args.verbose,
            )
        else:
            results = detect_watermark_regions(input_path, verbose=args.verbose)

        if not results:
            print("[remove_logo] No watermarks detected")
        else:
            print(f"[remove_logo] Found {len(results)} watermark(s):")
            for corner, x, y, w, h in results:
                print(f"  {corner}: x={x} y={y} w={w} h={h}")
            if args.debug:
                debug_path = input_path.parent / f"{input_path.stem}_debug.jpg"
                _draw_debug_frame(input_path, results, debug_path)
        return

    remove_logo(
        input_path, args.output,
        quality=args.quality,
        provider=args.provider,
        ollama_url=args.ollama_url,
        model=args.model,
        api_key=args.ollama_api_key,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
