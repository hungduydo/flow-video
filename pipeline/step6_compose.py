"""
Step 6: Compose the final video.

Operations (in one ffmpeg pass):
  1. Zoom 5% + center crop → removes corner watermarks
     (scale to 105%, then crop back to original dimensions)
     Note: crop's iw/ih reference the *scaled* frame, not the original.
  2. Replace audio with audio_vn_full.mp3
  3. Burn Vietnamese captions from captions_vn.srt

Output:
  output/{video_id}/final.mp4
  output/{video_id}/.step6.done  (sentinel)
"""

import subprocess
import sys
from pathlib import Path

# ffmpeg-full (brew install ffmpeg-full) includes libass required for the
# subtitles filter.  Fall back to plain ffmpeg if it's not installed yet.
_FFMPEG_FULL = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
_FFMPEG_BIN = str(_FFMPEG_FULL) if _FFMPEG_FULL.exists() else "ffmpeg"


def compose(output_dir: Path, crf: int = 23) -> Path:
    sentinel = output_dir / ".step6.done"
    if sentinel.exists():
        print("[step6] Skip — final.mp4 already composed")
        return output_dir / "final.mp4"

    video_path = output_dir / "original.mp4"
    audio_path = output_dir / "audio_vn_full.mp3"
    srt_path   = output_dir / "captions_vn.srt"
    final_path = output_dir / "final.mp4"

    for p in (video_path, audio_path, srt_path):
        if not p.exists():
            raise FileNotFoundError(f"Required file missing: {p}")

    print("[step6] Composing final video …")
    print(f"        CRF={crf}, watermark zoom 5%, Vietnamese dub + captions")

    # subtitles filter requires an absolute path with colons escaped (macOS/Linux)
    srt_escaped = str(srt_path.resolve()).replace("\\", "/").replace(":", "\\:")

    vf = (
        "scale=iw*1.05:ih*1.05,"          # zoom 5%
        "crop=iw/1.05:ih/1.05,"            # crop back to original size (refs scaled dims)
        f"subtitles=filename={srt_escaped}"
        ":force_style='FontName=Arial,FontSize=16,"
        "PrimaryColour=&H00FFFFFF,"        # white text
        "BackColour=&H70000000,"           # semi-transparent black box (56% opacity)
        "BorderStyle=4,Outline=0,Shadow=0,"  # BorderStyle=4 = box background
        "MarginV=20,"                      # distance from bottom edge
        "Alignment=2'"                     # bottom-center
    )

    cmd = [
        _FFMPEG_BIN, "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v:0",       # video from original
        "-map", "1:a:0",       # audio from VN dub
        "-vf", vf,
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
        raise RuntimeError(f"ffmpeg compose failed:\n{result.stderr}")

    sentinel.touch()
    size_mb = final_path.stat().st_size / 1_048_576
    print(f"[step6] Done — {final_path} ({size_mb:.1f} MB)")
    return final_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m pipeline.step6_compose <output_dir> [crf]")
        sys.exit(1)
    _crf = int(sys.argv[2]) if len(sys.argv) > 2 else 23
    compose(Path(sys.argv[1]), crf=_crf)
