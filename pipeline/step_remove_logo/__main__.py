import argparse
import os
import sys
from pathlib import Path

import cv2

from .main import detect_all_regions_llm, remove_logo


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
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * 0.20))
    ok, frame = cap.read()
    cap.release()

    if not ok:
        print("[remove_logo] Warning: could not read frame for debug image", file=sys.stderr)
        return

    for i, (corner, x, y, w, h) in enumerate(regions):
        colour = _COLOURS[i % len(_COLOURS)]
        overlay = frame.copy()
        cv2.rectangle(overlay, (x, y), (x + w - 1, y + h - 1), colour, -1)
        frame = cv2.addWeighted(overlay, 0.25, frame, 0.75, 0)
        cv2.rectangle(frame, (x, y), (x + w - 1, y + h - 1), colour, 3)
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
        description="Remove persistent corner logo/watermark from a video using LLM detection.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m pipeline.step_remove_logo input.mp4
  python -m pipeline.step_remove_logo input.mp4 output_clean.mp4
  python -m pipeline.step_remove_logo input.mp4 --detect-only
  python -m pipeline.step_remove_logo input.mp4 --detect-only --debug --verbose
  python -m pipeline.step_remove_logo input.mp4 --model llava:13b
  python -m pipeline.step_remove_logo input.mp4 --ollama-url http://localhost:11434
  OLLAMA_URL=http://localhost:11434 python -m pipeline.step_remove_logo input.mp4
""",
    )
    parser.add_argument("input", help="Input video path")
    parser.add_argument("output", nargs="?", default=None,
                        help="Output video path (default: {stem}_clean.mp4)")
    parser.add_argument(
        "--model", default="gemini-3-flash-preview:cloud",
        help="Ollama model name (default: gemini-3-flash-preview:cloud)",
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
        help="Print per-frame LLM detection results",
    )

    args = parser.parse_args()
    input_path = Path(args.input)

    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    if args.detect_only:
        print(f"[remove_logo] Detecting watermarks in {input_path.name} …")
        logos, subtitle = detect_all_regions_llm(
            input_path,
            ollama_url=args.ollama_url,
            model=args.model,
            api_key=args.ollama_api_key,
            verbose=args.verbose,
        )
        if not logos and not subtitle:
            print("[remove_logo] No watermarks or subtitle detected")
        else:
            if logos:
                print(f"[remove_logo] Found {len(logos)} logo(s):")
                for corner, x, y, w, h in logos:
                    print(f"  {corner}: x={x} y={y} w={w} h={h}")
            if subtitle:
                sx, sy, sw, sh = subtitle
                print(f"[remove_logo] Subtitle: x={sx} y={sy} w={sw} h={sh}")
            if args.debug:
                all_regions = list(logos)
                if subtitle:
                    all_regions.append(("subtitle", *subtitle))
                debug_path = input_path.parent / f"{input_path.stem}_debug.jpg"
                _draw_debug_frame(input_path, all_regions, debug_path)
        return

    remove_logo(
        input_path, args.output,
        ollama_url=args.ollama_url,
        model=args.model,
        api_key=args.ollama_api_key,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
