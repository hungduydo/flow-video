"""
Step 6: Compose the final video.

Operations (in one ffmpeg pass):
  1. Zoom 5% + center crop → removes corner watermarks
     (scale to 105%, then crop back to original dimensions)
     Note: crop's iw/ih reference the *scaled* frame, not the original.
  2. Replace audio with audio_vn_full.mp3
  3. Burn Vietnamese captions (native ASS format with platform styling)

Platform profiles:
  youtube  16:9, white-text-on-black-box ASS captions, bottom center
  tiktok   9:16 center crop, larger bold captions, higher position
  both     produces both final_youtube.mp4 and final_tiktok.mp4

Output:
  output/{video_id}/captions_vn_{platform}.ass   (intermediate, retained for debugging)
  output/{video_id}/final_youtube.mp4            (--platform youtube or both)
  output/{video_id}/final_tiktok.mp4             (--platform tiktok or both)
  output/{video_id}/final.mp4                    (copy of youtube output, backward compat)
  output/{video_id}/.step6.youtube.done          (per-platform sentinel)
  output/{video_id}/.step6.tiktok.done           (per-platform sentinel)
  output/{video_id}/.step6.done                  (legacy sentinel, backward compat)
"""

import shutil
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import srt

# ffmpeg-full (brew install ffmpeg-full) includes libass required for the
# ass filter.  Fall back to plain ffmpeg if it's not installed yet.
_FFMPEG_FULL = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
_FFMPEG_BIN = str(_FFMPEG_FULL) if _FFMPEG_FULL.exists() else "ffmpeg"


# ── ASS styling ───────────────────────────────────────────────────────────────
#
# ASS colour format: &HAABBGGRR  (alpha, blue, green, red — reversed channels)
#   &H00FFFFFF = fully opaque white text
#   &H80000000 = 50% transparent black box  (alpha=0x80)  — YouTube style
#   &H99000000 = 60% transparent black box  (alpha=0x99)  — TikTok (brighter screens)
#
# BorderStyle values in native ASS format:
#   1 = outline only   3 = opaque background box  (what we want)
# Note: FFmpeg's force_style= uses a different numbering (4 = box in that context).
# Since we're writing a native .ass file, BorderStyle=3 is the correct value.

_ASS_STYLE_YOUTUBE = (
    "Style: Default,"
    "Arial,22,"            # font, size
    "&H00FFFFFF,"          # PrimaryColour: white text
    "&H000000FF,"          # SecondaryColour (unused)
    "&H00000000,"          # OutlineColour (unused with BorderStyle=3)
    "&H80000000,"          # BackColour: 50% black box
    "0,0,0,0,"             # Bold, Italic, Underline, StrikeOut
    "100,100,0,0,"         # ScaleX, ScaleY, Spacing, Angle
    "3,"                   # BorderStyle=3: opaque background box
    "0,0,"                 # Outline, Shadow
    "2,"                   # Alignment=2: bottom center
    "10,10,30,1"           # MarginL, MarginR, MarginV, Encoding
)

_ASS_STYLE_TIKTOK = (
    "Style: Default,"
    "Arial,28,"
    "&H00FFFFFF,"
    "&H000000FF,"
    "&H00000000,"
    "&H99000000,"          # 60% black box — more opaque for bright mobile screens
    "-1,0,0,0,"            # Bold=-1 (on) for readability on small screens
    "100,100,0,0,"
    "3,"
    "0,0,"
    "2,"
    "10,10,80,1"           # MarginV=80: higher to avoid TikTok UI / thumbs
)

_ASS_STYLES = {"youtube": _ASS_STYLE_YOUTUBE, "tiktok": _ASS_STYLE_TIKTOK}

_ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{style}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _td_to_ass(td: timedelta) -> str:
    """Convert timedelta to ASS timestamp H:MM:SS.cc (centiseconds)."""
    total_cs = int(td.total_seconds() * 100)
    cc = total_cs % 100
    total_s = total_cs // 100
    ss = total_s % 60
    mm = (total_s // 60) % 60
    hh = total_s // 3600
    return f"{hh}:{mm:02d}:{ss:02d}.{cc:02d}"


def _srt_to_ass(srt_path: Path, platform: str, width: int, height: int) -> Path:
    """Convert SRT to native ASS with platform-appropriate styling.

    width/height should be the *output* frame dimensions for this platform
    (so TikTok passes the cropped 9:16 dimensions, not the source dimensions).

    Output: same directory as srt_path, named captions_vn_{platform}.ass.
    Retained as a pipeline artifact — not cleaned up after compose.
    Returns the Path to the written .ass file.
    """
    ass_path = srt_path.parent / f"captions_vn_{platform}.ass"
    style = _ASS_STYLES[platform]

    subtitles = list(srt.parse(srt_path.read_text(encoding="utf-8")))

    lines = [_ASS_HEADER.format(width=width, height=height, style=style)]
    for sub in subtitles:
        start = _td_to_ass(sub.start)
        end = _td_to_ass(sub.end)
        # Replace newlines with ASS hard newline; escape { to avoid ASS override tags
        text = sub.content.strip().replace("{", "\\{").replace("\n", "\\N")
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    ass_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ass_path


# ── Video helpers ─────────────────────────────────────────────────────────────

def _get_video_dimensions(video_path: Path) -> tuple[int, int]:
    """Return (width, height) of the first video stream via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return 1920, 1080  # safe fallback
    parts = result.stdout.strip().split(",")
    return int(parts[0]), int(parts[1])


def _get_tiktok_crop(width: int, height: int, crop_x: int | None = None) -> str:
    """Return ffmpeg crop filter string for 9:16 vertical crop from 16:9 source.

    crop_x: horizontal pixel offset from the left edge of the source frame.
    If None, defaults to center crop: (width - target_w) // 2.
    Clamped to valid range [0, width - target_w].
    """
    target_w = int(height * 9 / 16)
    if crop_x is None:
        x_offset = (width - target_w) // 2
    else:
        x_offset = max(0, min(crop_x, width - target_w))
    return f"crop={target_w}:{height}:{x_offset}:0"


# ── Compose ───────────────────────────────────────────────────────────────────

def _compose_one(
    video_path: Path,
    audio_path: Path,
    ass_path: Path,
    final_path: Path,
    crf: int,
    extra_vf: str = "",
) -> None:
    """Run one ffmpeg compose pass.

    extra_vf is inserted between the watermark crop and the ASS overlay —
    used for the TikTok 9:16 crop filter.
    """
    # ass filter requires an absolute path with colons escaped (macOS/Linux)
    ass_escaped = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:")

    vf_parts = [
        "scale=iw*1.05:ih*1.05",    # zoom 5% (watermark removal)
        "crop=iw/1.05:ih/1.05",      # crop back to original dims (refs scaled frame)
    ]
    if extra_vf:
        vf_parts.append(extra_vf)    # TikTok 9:16 crop
    vf_parts.append(f"ass={ass_escaped}")

    cmd = [
        _FFMPEG_BIN, "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-vf", ",".join(vf_parts),
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
        raise RuntimeError(f"ffmpeg compose failed:\n{result.stderr[-3000:]}")


def compose(
    output_dir: Path,
    crf: int = 23,
    platform: str = "youtube",
    tiktok_crop_x: int | None = None,
) -> Path:
    """Compose final video(s) with professional ASS captions.

    platform: "youtube" | "tiktok" | "both"

    Sentinels: .step6.youtube.done / .step6.tiktok.done (per-platform).
    Legacy .step6.done and final.mp4 are also written for backward compat.

    Returns path to the primary output file.
    """
    platforms = ["youtube", "tiktok"] if platform == "both" else [platform]

    sentinel_map = {
        "youtube": output_dir / ".step6.youtube.done",
        "tiktok":  output_dir / ".step6.tiktok.done",
    }
    legacy_sentinel = output_dir / ".step6.done"

    remaining = [p for p in platforms if not sentinel_map[p].exists()]
    if not remaining:
        print("[step6] Skip — all platform outputs already composed")
        yt = output_dir / "final_youtube.mp4"
        return yt if yt.exists() else output_dir / "final.mp4"

    video_path = output_dir / "original.mp4"
    audio_path = output_dir / "audio_vn_full.mp3"
    srt_path   = output_dir / "captions_vn.srt"

    for p in (video_path, audio_path, srt_path):
        if not p.exists():
            raise FileNotFoundError(f"Required file missing: {p}")

    src_w, src_h = _get_video_dimensions(video_path)
    print(f"[step6] Source: {src_w}x{src_h}, platform={platform}, CRF={crf}")

    primary_path: Path | None = None

    for plat in remaining:
        if sentinel_map[plat].exists():
            continue

        if plat == "tiktok":
            out_w = int(src_h * 9 / 16)   # 9:16 output width
            out_h = src_h
            ass_path = _srt_to_ass(srt_path, plat, out_w, out_h)
            extra_vf = _get_tiktok_crop(src_w, src_h, tiktok_crop_x)
        else:
            ass_path = _srt_to_ass(srt_path, plat, src_w, src_h)
            extra_vf = ""

        final_path = output_dir / f"final_{plat}.mp4"
        print(f"[step6] Composing {plat} …")
        _compose_one(video_path, audio_path, ass_path, final_path, crf, extra_vf)

        sentinel_map[plat].touch()
        size_mb = final_path.stat().st_size / 1_048_576
        print(f"[step6] {plat} → {final_path} ({size_mb:.1f} MB)")

        if primary_path is None:
            primary_path = final_path

    # Backward compat: write final.mp4 (copy of youtube; tiktok if youtube not produced)
    yt_out = output_dir / "final_youtube.mp4"
    tt_out = output_dir / "final_tiktok.mp4"
    if yt_out.exists():
        shutil.copy2(yt_out, output_dir / "final.mp4")
        legacy_sentinel.touch()
    elif tt_out.exists():
        shutil.copy2(tt_out, output_dir / "final.mp4")
        legacy_sentinel.touch()

    return primary_path or output_dir / "final.mp4"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Step 6: compose final video")
    parser.add_argument("output_dir")
    parser.add_argument("--crf", type=int, default=23)
    parser.add_argument("--platform", default="youtube",
                        choices=["youtube", "tiktok", "both"])
    parser.add_argument("--tiktok-crop-x", type=int, default=None,
                        dest="tiktok_crop_x")
    args = parser.parse_args()
    compose(Path(args.output_dir), crf=args.crf, platform=args.platform,
            tiktok_crop_x=args.tiktok_crop_x)
