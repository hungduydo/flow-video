"""
Workflow: Reaction & Commentary (Group 4)

Semi-original content where the original video plays in a picture-in-picture
(PiP) window while the user's commentary audio plays over it.

This workflow requires a user-provided commentary track. If the file is absent
the pipeline exits gracefully with instructions.

Steps:
  (download + extract_audio done in main_v2 before routing)
  step6r  Compose PiP layout: original video scaled to ~35% in corner,
            black background, commentary audio as main track

User action required:
  Place commentary.mp3 in the output directory, then re-run.

Sentinel: .step6r.done → final.mp4
"""

import argparse
import subprocess
from pathlib import Path

_FFMPEG_FULL = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
_FFMPEG_BIN  = str(_FFMPEG_FULL) if _FFMPEG_FULL.exists() else "ffmpeg"


def run(output_dir: Path, args: argparse.Namespace) -> Path | None:
    commentary_path = output_dir / "commentary.mp3"
    if not commentary_path.exists():
        print()
        print("[reaction] Commentary audio not found.")
        print("[reaction] To continue, place your recorded commentary track at:")
        print(f"           {commentary_path.resolve()}")
        print("[reaction] Then re-run the pipeline — it will skip to composition.")
        return None
    return compose_pip(output_dir, crf=args.crf)


def compose_pip(
    output_dir: Path,
    crf: int = 23,
    pip_scale: float = 0.35,
    pip_x: int = 20,
    pip_y: int = 20,
) -> Path:
    """Compose a picture-in-picture video.

    The original video is scaled to pip_scale of the frame dimensions and
    placed at (pip_x, pip_y) over a solid black background. The commentary
    audio replaces the original audio track.
    """
    sentinel       = output_dir / ".step6r.done"
    video_path     = output_dir / "original.mp4"
    commentary_path = output_dir / "commentary.mp3"
    final_path     = output_dir / "final.mp4"

    if sentinel.exists():
        print("[step6r] Skip — final.mp4 already composed (PiP/reaction mode)")
        return final_path

    for p in (video_path, commentary_path):
        if not p.exists():
            raise FileNotFoundError(f"Required file missing: {p}")

    # Probe original video dimensions
    probe_cmd = [
        "ffprobe", "-v", "quiet",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0",
        str(video_path),
    ]
    probe = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
    width, height = map(int, probe.stdout.strip().split(","))

    pip_w = int(width  * pip_scale)
    pip_h = int(height * pip_scale)
    # libx264 requires even dimensions
    pip_w -= pip_w % 2
    pip_h -= pip_h % 2

    print(f"[step6r] Composing PiP video …")
    print(f"         Original: {width}×{height}  PiP: {pip_w}×{pip_h} at ({pip_x},{pip_y})")

    filter_complex = (
        f"[0:v] scale={pip_w}:{pip_h} [pip];"
        f"color=black:size={width}x{height}:rate=25 [bg];"
        f"[bg][pip] overlay={pip_x}:{pip_y} [out]"
    )

    cmd = [
        _FFMPEG_BIN, "-y",
        "-i", str(video_path),
        "-i", str(commentary_path),
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "1:a:0",     # commentary audio
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(final_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg PiP compose failed:\n{result.stderr}")

    sentinel.touch()
    size_mb = final_path.stat().st_size / 1_048_576
    print(f"[step6r] Done — {final_path} ({size_mb:.1f} MB)")
    return final_path
