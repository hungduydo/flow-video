"""
gen_frames.py — Extract frames from a video file.

Usage:
  python gen_frames.py <video> [options]

Examples:
  # 1 frame every 2 seconds → output/frames/
  python gen_frames.py output/BV123/original.mp4

  # 1 frame per second, custom output dir
  python gen_frames.py video.mp4 --interval 1 --out frames/

  # Fixed FPS (e.g. 5 fps)
  python gen_frames.py video.mp4 --fps 5

  # Only at scene cut timestamps (reads scenes.json from same dir as video)
  python gen_frames.py output/BV123/original.mp4 --scenes

  # Specific time range
  python gen_frames.py video.mp4 --start 10 --end 60 --interval 2
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _video_duration(video: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video),
        ],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def extract_at_timestamps(video: Path, timestamps: list[float], out_dir: Path) -> list[Path]:
    """Extract one frame per timestamp using ffmpeg select filter."""
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []

    for i, ts in enumerate(timestamps):
        out_path = out_dir / f"frame_{i:05d}_{ts:.3f}s.jpg"
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(ts),
            "-i", str(video),
            "-frames:v", "1",
            "-q:v", "2",
            str(out_path),
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode == 0:
            saved.append(out_path)
            print(f"  [{i+1}/{len(timestamps)}] {out_path.name}")
        else:
            print(f"  [warn] Failed at {ts:.3f}s", file=sys.stderr)

    return saved


def extract_by_fps(
    video: Path,
    out_dir: Path,
    fps: float | None = None,
    interval: float | None = None,
    start: float = 0.0,
    end: float | None = None,
) -> list[Path]:
    """Extract frames at a fixed rate using ffmpeg fps filter."""
    out_dir.mkdir(parents=True, exist_ok=True)

    if fps is None and interval is not None:
        fps = 1.0 / interval
    elif fps is None:
        fps = 0.5  # default: 1 frame every 2 seconds

    filters = [f"fps={fps}"]

    cmd = ["ffmpeg", "-y"]
    if start:
        cmd += ["-ss", str(start)]
    cmd += ["-i", str(video)]
    if end is not None:
        duration = end - start
        cmd += ["-t", str(duration)]
    cmd += [
        "-vf", ",".join(filters),
        "-q:v", "2",
        str(out_dir / "frame_%05d.jpg"),
    ]

    print(f"[gen_frames] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    frames = sorted(out_dir.glob("frame_*.jpg"))
    return frames


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract frames from a video.")
    parser.add_argument("video", type=Path, help="Input video file")
    parser.add_argument("--out", type=Path, default=None, help="Output directory (default: <video_dir>/frames/)")
    parser.add_argument("--fps", type=float, default=None, help="Frames per second to extract")
    parser.add_argument("--interval", type=float, default=None, help="Seconds between frames (overridden by --fps)")
    parser.add_argument("--start", type=float, default=0.0, help="Start time in seconds")
    parser.add_argument("--end", type=float, default=None, help="End time in seconds")
    parser.add_argument("--scenes", action="store_true", help="Extract frames at scene cut timestamps (reads scenes.json)")
    args = parser.parse_args()

    video = args.video.resolve()
    if not video.exists():
        print(f"[error] Video not found: {video}", file=sys.stderr)
        sys.exit(1)

    out_dir = args.out or (video.parent / "frames")

    # ── Scene-cut mode ────────────────────────────────────────────────────────
    if args.scenes:
        scenes_file = video.parent / "scenes.json"
        if not scenes_file.exists():
            print(f"[error] scenes.json not found at {scenes_file}", file=sys.stderr)
            sys.exit(1)
        data = json.loads(scenes_file.read_text())
        cuts: list[float] = data.get("cuts", [])
        if not cuts:
            print("[warn] scenes.json has no cuts — falling back to interval mode")
        else:
            # Extract one frame slightly after each cut
            timestamps = [max(0.0, t + 0.1) for t in cuts]
            print(f"[gen_frames] Extracting {len(timestamps)} frames at scene cuts → {out_dir}")
            frames = extract_at_timestamps(video, timestamps, out_dir)
            print(f"[gen_frames] Done — {len(frames)} frames saved to {out_dir}")
            return

    # ── FPS / interval mode ───────────────────────────────────────────────────
    end = args.end
    if end is None:
        duration = _video_duration(video)
        if duration:
            end = duration

    rate = args.fps or (1.0 / args.interval if args.interval else None)
    desc = f"{rate} fps" if rate else "0.5 fps (default)"
    print(f"[gen_frames] Extracting frames at {desc} → {out_dir}")

    frames = extract_by_fps(
        video, out_dir,
        fps=args.fps,
        interval=args.interval,
        start=args.start,
        end=end,
    )
    print(f"[gen_frames] Done — {len(frames)} frames saved to {out_dir}")


if __name__ == "__main__":
    main()
