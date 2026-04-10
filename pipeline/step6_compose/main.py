"""
Step 6: Compose the final video.

Operations (in one ffmpeg pass):
  1. Zoom 5% + center crop → removes corner watermarks
     (scale to 105%, then crop back to original dimensions)
     Note: crop's iw/ih reference the *scaled* frame, not the original.
  2. Replace audio with audio_vn_full.mp3
  3. Burn Vietnamese captions from captions_vn.srt

Platform profiles:
  youtube  16:9, subtitles bottom center
  tiktok   9:16 center crop, subtitles higher position
  both     produces both final_youtube.mp4 and final_tiktok.mp4

Output:
  output/{video_id}/final_youtube.mp4            (--platform youtube or both)
  output/{video_id}/final_tiktok.mp4             (--platform tiktok or both)
  output/{video_id}/final.mp4                    (copy of youtube output, backward compat)
  output/{video_id}/.step6.youtube.done          (per-platform sentinel)
  output/{video_id}/.step6.tiktok.done           (per-platform sentinel)
  output/{video_id}/.step6.done                  (legacy sentinel, backward compat)
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

# ffmpeg-full (brew install ffmpeg-full) includes libass required for the
# subtitles filter.  Fall back to plain ffmpeg if it's not installed yet.
_FFMPEG_FULL = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
_FFMPEG_BIN = str(_FFMPEG_FULL) if _FFMPEG_FULL.exists() else "ffmpeg"


# ── Subtitle position force_style ─────────────────────────────────────────────
#
# force_style Alignment values (numpad layout):
#   7  8  9     (top-left, top-center, top-right)
#   4  5  6
#   1  2  3     (bottom-left, bottom-center, bottom-right)
#
# Use "top" when the source video has a burned-in title at the bottom
# that subtitles would otherwise cover.

_SUBTITLE_FORCE_STYLE = {
    ("youtube", "bottom"): "Alignment=2,MarginV=30",
    ("youtube", "top"):    "Alignment=8,MarginV=20",
    ("tiktok",  "bottom"): "Alignment=2,MarginV=80",   # higher to avoid TikTok UI
    ("tiktok",  "top"):    "Alignment=8,MarginV=30",
}


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
    srt_path: Path,
    final_path: Path,
    crf: int,
    platform: str = "youtube",
    extra_vf: str = "",
    subtitle_position: str = "bottom",
    delogo_region: tuple[int, int, int, int] | None = None,
) -> None:
    """Run one ffmpeg compose pass.

    delogo_region: (x, y, w, h) in original-frame pixels — removes burned-in
    subtitle/title text before any scaling.  Coordinates come from
    detect_subtitle_region() which already includes 10 px padding.

    extra_vf is inserted between the watermark crop and the subtitles filter —
    used for the TikTok 9:16 crop filter.
    """
    # subtitles filter requires an absolute path with colons escaped (macOS/Linux)
    srt_escaped = str(srt_path.resolve()).replace("\\", "/").replace(":", "\\:")
    force_style = _SUBTITLE_FORCE_STYLE[(platform, subtitle_position)]

    vf_parts = []

    # delogo first — coordinates are in original frame space, before any scaling
    if delogo_region:
        dx, dy, dw, dh = delogo_region
        vf_parts.append(f"delogo=x={dx}:y={dy}:w={dw}:h={dh}")

    vf_parts += [
        "scale=iw*1.05:ih*1.05",    # zoom 5% (watermark removal)
        "crop=iw/1.05:ih/1.05",      # crop back to original dims (refs scaled frame)
    ]
    if extra_vf:
        vf_parts.append(extra_vf)    # TikTok 9:16 crop
    vf_parts.append(f"subtitles={srt_escaped}:force_style='{force_style}'")

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
    subtitle_position: str = "bottom",
    ollama_url: str = "https://ollama.com",
    model: str = "gemini-3-flash-preview:cloud",
    ollama_api_key: str | None = None,
    verbose: bool = False,
) -> Path:
    """Compose final video(s) with burned-in Vietnamese captions.

    platform: "youtube" | "tiktok" | "both"
    subtitle_position: "bottom" (default) | "top" | "auto"
        "auto" uses a vision LLM (via Ollama) to detect where the source video
        has burned-in title/subtitle text, then places Vietnamese subtitles at
        the opposite region so they don't cover the original.

    ollama_url / model / ollama_api_key: used only when subtitle_position="auto".

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

    # Resolve subtitle region: prefer detected_regions.json (written by step_remove_logo),
    # fall back to running LLM detection directly if the file doesn't exist.
    delogo_region: tuple[int, int, int, int] | None = None
    if subtitle_position == "auto":
        bbox: tuple[int, int, int, int] | None = None

        regions_file = output_dir / "detected_regions.json"
        if regions_file.exists():
            try:
                data = json.loads(regions_file.read_text(encoding="utf-8"))
                sub = data.get("subtitle")
                if sub:
                    bbox = (sub["x"], sub["y"], sub["w"], sub["h"])
                    print(f"[step6] Loaded subtitle region from {regions_file.name}")
            except Exception as exc:
                print(f"[step6] Warning: could not read {regions_file.name} — {exc}")

        if bbox is None:
            from .detect_subtitle import detect_subtitle_region
            print("[step6] detected_regions.json not found — running LLM detection …")
            bbox = detect_subtitle_region(
                video_path,
                ollama_url=ollama_url,
                model=model,
                api_key=ollama_api_key,
                verbose=verbose,
            )

        if bbox:
            delogo_region = bbox
            _, by, _, bh = bbox
            if (by + bh / 2) > src_h / 2:
                subtitle_position = "top"
                print(f"[step6] Original text at bottom (y={by} h={bh}) → delogo + subtitles at top")
            else:
                subtitle_position = "bottom"
                print(f"[step6] Original text at top (y={by} h={bh}) → delogo + subtitles at bottom")
        else:
            subtitle_position = "bottom"
            print("[step6] No original text detected → using default bottom position")

    primary_path: Path | None = None

    for plat in remaining:
        if sentinel_map[plat].exists():
            continue

        extra_vf = _get_tiktok_crop(src_w, src_h, tiktok_crop_x) if plat == "tiktok" else ""

        final_path = output_dir / f"final_{plat}.mp4"
        print(f"[step6] Composing {plat} …")
        _compose_one(
            video_path, audio_path, srt_path, final_path, crf,
            platform=plat, extra_vf=extra_vf,
            subtitle_position=subtitle_position, delogo_region=delogo_region,
        )

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
    parser.add_argument("--subtitle-position", default="bottom",
                        choices=["bottom", "top", "auto"], dest="subtitle_position",
                        help="'top' keeps source bottom titles visible; "
                             "'auto' detects via LLM and places at opposite region")
    parser.add_argument("--ollama-url", default="https://ollama.com", dest="ollama_url")
    parser.add_argument("--model", default="gemini-3-flash-preview:cloud")
    parser.add_argument("--ollama-api-key", default=None, dest="ollama_api_key")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    compose(Path(args.output_dir), crf=args.crf, platform=args.platform,
            tiktok_crop_x=args.tiktok_crop_x,
            subtitle_position=args.subtitle_position,
            ollama_url=args.ollama_url, model=args.model,
            ollama_api_key=args.ollama_api_key, verbose=args.verbose)
