"""
Step 6: Compose the final video with burned-in Vietnamese captions.

Operations (single ffmpeg pass):
  1. Zoom 5% + center crop → removes corner watermarks
  2. Replace audio with audio_vn_full.mp3
  3. Burn Vietnamese captions from captions_vn.srt

Platform profiles:
  youtube  16:9, subtitles below detected text (or 20% from bottom as fallback)
  tiktok   9:16 blurred background, subtitles at 20% from bottom
  both     produces both final_youtube.mp4 and final_tiktok.mp4

Output:
  output/{video_id}/final_youtube.mp4            (--platform youtube or both)
  output/{video_id}/final_tiktok.mp4             (--platform tiktok or both)
  output/{video_id}/final.mp4                    (backward compat)
  output/{video_id}/.step6.{platform}.done       (per-platform sentinel)
"""

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ── Configuration ──────────────────────────────────────────────────────────────

_FFMPEG_FULL = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
_FFMPEG_BIN = str(_FFMPEG_FULL) if _FFMPEG_FULL.exists() else "ffmpeg"

# Subtitle position defaults (fallback when no detection available)
_SUBTITLE_FORCE_STYLE = {
    ("youtube", "bottom"): "Alignment=8,MarginV=20",   # Top-center, 20px from top
    ("youtube", "top"):    "Alignment=8,MarginV=20",
    ("tiktok",  "bottom"): "Alignment=2,MarginV=384",  # Bottom-center, 20% from bottom
    ("tiktok",  "top"):    "Alignment=8,MarginV=30",
}

# TikTok canvas dimensions (9:16 portrait)
TIKTOK_W, TIKTOK_H = 1080, 1920


# ── Data Classes ───────────────────────────────────────────────────────────────

@dataclass
class VideoPaths:
    """Manages input/output video paths."""
    output_dir: Path
    video: Path
    audio: Path
    srt: Path
    
    @staticmethod
    def from_dir(output_dir: Path) -> "VideoPaths":
        """Resolve video, audio, and subtitle paths from output directory."""
        clean_video = output_dir / "original_clean.mp4"
        video = clean_video if clean_video.exists() else output_dir / "original.mp4"
        
        paths = VideoPaths(
            output_dir=output_dir,
            video=video,
            audio=output_dir / "audio_vn_full.mp3",
            srt=output_dir / "captions_vn.srt",
        )
        paths.validate()
        return paths
    
    def validate(self) -> None:
        """Ensure all required files exist."""
        for path in (self.video, self.audio, self.srt):
            if not path.exists():
                raise FileNotFoundError(f"Required file missing: {path}")


@dataclass
class ComposeConfig:
    """Configuration for video composition."""
    crf: int = 23
    platform: str = "youtube"
    tiktok_crop_x: Optional[int] = None
    subtitle_position: str = "bottom"
    ollama_url: str = "https://ollama.com"
    model: str = "gemini-3-flash-preview:cloud"
    ollama_api_key: Optional[str] = None
    verbose: bool = False


@dataclass
class SubtitleRegion:
    """Detected subtitle region (bounding box)."""
    x: int
    y: int
    w: int
    h: int
    
    @staticmethod
    def from_json_file(path: Path) -> Optional["SubtitleRegion"]:
        """Load subtitle region from detected_regions.json."""
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            sub = data.get("subtitle")
            if sub:
                return SubtitleRegion(sub["x"], sub["y"], sub["w"], sub["h"])
        except Exception as e:
            print(f"[step6] Warning: could not read {path.name} — {e}")
        return None
    
    def enforce_min_width(self, frame_width: int, min_ratio: float = 0.60) -> "SubtitleRegion":
        """Expand width if below minimum threshold."""
        min_w = int(frame_width * min_ratio)
        if self.w < min_w:
            new_x = max(0, (frame_width - min_w) // 2)
            return SubtitleRegion(new_x, self.y, min_w, self.h)
        return self


# ── Subtitle Positioning ──────────────────────────────────────────────────────

def compute_detected_subtitle_style(bbox: SubtitleRegion, _src_w: int, _src_h: int) -> str:
    """Compute ASS force_style for YouTube based on detected subtitle bbox.
    
    Places subtitle 10px below the detected text.
    Alignment=8 (top-center), MarginV from top.
    """
    margin_v = bbox.y + bbox.h + 10
    return f"Alignment=8,MarginV={margin_v}"


def get_subtitle_style(platform: str, position: str, detected_style: Optional[str] = None) -> str:
    """Get subtitle force_style: use detected if available, else use default."""
    if detected_style and platform == "youtube":
        return detected_style
    return _SUBTITLE_FORCE_STYLE.get((platform, position), _SUBTITLE_FORCE_STYLE[("youtube", "bottom")])


# ── FFmpeg Command Building ────────────────────────────────────────────────────

def _escape_srt_path(srt_path: Path) -> str:
    """Escape SRT path for ffmpeg subtitles filter."""
    return str(srt_path.resolve()).replace("\\", "/").replace(":", "\\:")


def _build_watermark_filter() -> list[str]:
    """Build filter chain for watermark removal."""
    return [
        "scale=iw*1.05:ih*1.05",  # zoom 5%
        "crop=iw/1.05:ih/1.05",   # crop back to original
    ]


def _build_delogo_filter(delogo_region: Optional[tuple[int, int, int, int]]) -> Optional[str]:
    """Build delogo filter if region specified."""
    if delogo_region:
        dx, dy, dw, dh = delogo_region
        return f"delogo=x={dx}:y={dy}:w={dw}:h={dh}"
    return None


def _build_simple_vf(vf_parts: list[str], extra_vf: str = "") -> str:
    """Build simple filter chain (YouTube, portrait TikTok)."""
    filters = []
    if vf_parts[0].startswith("delogo"):  # if delogo present
        filters.append(vf_parts.pop(0))
    
    filters.extend(_build_watermark_filter())
    if extra_vf:
        filters.append(extra_vf)
    
    return ",".join(filters)


def _build_ffmpeg_cmd(
    video_path: Path,
    audio_path: Path,
    srt_path: Path,
    final_path: Path,
    crf: int,
    vf_filter: str,
    filter_complex: Optional[str] = None,
) -> list[str]:
    """Build ffmpeg command."""
    cmd = [_FFMPEG_BIN, "-y", "-i", str(video_path), "-i", str(audio_path)]
    
    if filter_complex:
        cmd.extend(["-filter_complex", filter_complex])
        cmd.extend(["-map", "[out]", "-map", "1:a:0"])
    else:
        cmd.extend(["-map", "0:v:0", "-map", "1:a:0", "-vf", vf_filter])
    
    cmd.extend([
        "-c:v", "libx264", "-crf", str(crf), "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        str(final_path),
    ])
    return cmd


# ── Platform-Specific Composition ──────────────────────────────────────────────

def _compose_youtube(
    paths: VideoPaths,
    config: ComposeConfig,
    force_style: str,
    delogo_region: Optional[tuple[int, int, int, int]] = None,
) -> Path:
    """Compose YouTube video (16:9)."""
    vf_parts = []
    if delogo_region:
        vf_parts.append(_build_delogo_filter(delogo_region))
    
    vf_parts.extend(_build_watermark_filter())
    srt_escaped = _escape_srt_path(paths.srt)
    vf_parts.append(f"subtitles={srt_escaped}:force_style='{force_style}'")
    
    final_path = paths.output_dir / "final_youtube.mp4"
    cmd = _build_ffmpeg_cmd(
        paths.video, paths.audio, paths.srt, final_path,
        config.crf, ",".join([p for p in vf_parts if p])
    )
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg YouTube compose failed:\n{result.stderr[-3000:]}")
    return final_path


def _compose_tiktok_portrait(
    paths: VideoPaths,
    config: ComposeConfig,
    force_style: str,
    delogo_region: Optional[tuple[int, int, int, int]] = None,
) -> Path:
    """Compose TikTok 9:16 portrait (center crop)."""
    video_w, video_h = _get_video_dimensions(paths.video)
    crop_filter = _get_tiktok_crop(video_w, video_h, config.tiktok_crop_x)
    
    vf_parts = []
    if delogo_region:
        vf_parts.append(_build_delogo_filter(delogo_region))
    vf_parts.extend(_build_watermark_filter())
    vf_parts.append(crop_filter)
    
    srt_escaped = _escape_srt_path(paths.srt)
    vf_parts.append(f"subtitles={srt_escaped}:force_style='{force_style}'")
    
    final_path = paths.output_dir / "final_tiktok.mp4"
    cmd = _build_ffmpeg_cmd(
        paths.video, paths.audio, paths.srt, final_path,
        config.crf, ",".join([p for p in vf_parts if p])
    )
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg TikTok portrait compose failed:\n{result.stderr[-3000:]}")
    return final_path


def _compose_tiktok_blur_bg(
    paths: VideoPaths,
    config: ComposeConfig,
    force_style: str,
    src_w: int,
    src_h: int,
    delogo_region: Optional[tuple[int, int, int, int]] = None,
) -> Path:
    """Compose TikTok 9:16 with blurred background (landscape source)."""
    srt_escaped = _escape_srt_path(paths.srt)
    
    # Background: blur
    bg_filter = f"scale=-2:{TIKTOK_H},crop={TIKTOK_W}:{TIKTOK_H},boxblur=20:5"
    
    # Foreground: zoom + crop + scale to canvas width
    fg_parts = []
    if delogo_region:
        dx, dy, dw, dh = delogo_region
        fg_parts.append(f"delogo=x={dx}:y={dy}:w={dw}:h={dh}")
    fg_parts.extend(["scale=iw*1.05:ih*1.05", "crop=iw/1.05:ih/1.05", f"scale={TIKTOK_W}:-2"])
    fg_filter = ",".join(fg_parts)
    
    filter_complex = (
        f"[0:v]split=2[bg_in][fg_in];"
        f"[bg_in]{bg_filter}[bg];"
        f"[fg_in]{fg_filter}[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[composed];"
        f"[composed]subtitles={srt_escaped}:force_style='{force_style}'[out]"
    )
    
    final_path = paths.output_dir / "final_tiktok.mp4"
    cmd = _build_ffmpeg_cmd(
        paths.video, paths.audio, paths.srt, final_path,
        config.crf, "", filter_complex
    )
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg TikTok blur-bg compose failed:\n{result.stderr[-3000:]}")
    return final_path


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_video_dimensions(video_path: Path) -> tuple[int, int]:
    """Get video width and height via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return 1920, 1080
    w, h = result.stdout.strip().split(",")
    return int(w), int(h)


def _get_tiktok_crop(width: int, height: int, crop_x: Optional[int] = None) -> str:
    """Build TikTok 9:16 crop filter."""
    target_w = int(height * 9 / 16)
    x_offset = (width - target_w) // 2 if crop_x is None else max(0, min(crop_x, width - target_w))
    return f"crop={target_w}:{height}:{x_offset}:0"


def _detect_subtitle_region(
    video_path: Path,
    output_dir: Path,
    config: ComposeConfig,
) -> Optional[SubtitleRegion]:
    """Detect subtitle region: check file first, then run LLM if needed."""
    regions_file = output_dir / "detected_regions.json"
    bbox = SubtitleRegion.from_json_file(regions_file)
    
    if bbox is None:
        from .detect_subtitle import detect_subtitle_region
        print("[step6] Running LLM subtitle detection …")
        bbox = detect_subtitle_region(
            video_path,
            ollama_url=config.ollama_url,
            model=config.model,
            api_key=config.ollama_api_key,
            verbose=config.verbose,
        )
    else:
        print(f"[step6] Loaded subtitle region from {regions_file.name}")
    
    return bbox


# ── Main Composition ───────────────────────────────────────────────────────────

def compose(
    output_dir: Path,
    crf: int = 23,
    platform: str = "youtube",
    tiktok_crop_x: Optional[int] = None,
    subtitle_position: str = "bottom",
    ollama_url: str = "https://ollama.com",
    model: str = "gemini-3-flash-preview:cloud",
    ollama_api_key: Optional[str] = None,
    verbose: bool = False,
) -> Path:
    """Compose final video(s) with burned-in Vietnamese captions.
    
    Args:
        output_dir: output directory
        crf: ffmpeg quality (0-51, lower = better)
        platform: "youtube", "tiktok", or "both"
        tiktok_crop_x: horizontal crop offset for portrait TikTok
        subtitle_position: "bottom" (default), "top", or "auto" (LLM detect)
        ollama_url/model/ollama_api_key: for LLM detection
        verbose: print debug info
    
    Returns:
        Path to primary output file
    """
    config = ComposeConfig(
        crf=crf, platform=platform, tiktok_crop_x=tiktok_crop_x,
        subtitle_position=subtitle_position, ollama_url=ollama_url, model=model,
        ollama_api_key=ollama_api_key, verbose=verbose
    )
    
    # Load video paths
    paths = VideoPaths.from_dir(output_dir)
    src_w, src_h = _get_video_dimensions(paths.video)
    is_landscape = src_w > src_h
    print(f"[step6] Source: {src_w}×{src_h}, platform={platform}, CRF={crf}")
    
    # Determine platforms to compose
    platforms = ["youtube", "tiktok"] if platform == "both" else [platform]
    sentinels = {
        "youtube": output_dir / ".step6.youtube.done",
        "tiktok": output_dir / ".step6.tiktok.done",
    }
    remaining = [p for p in platforms if not sentinels[p].exists()]
    
    if not remaining:
        print("[step6] Skip — all platform outputs already composed")
        yt = output_dir / "final_youtube.mp4"
        return yt if yt.exists() else output_dir / "final.mp4"
    
    # Detect subtitle region if using auto mode
    delogo_region = None
    detected_style = None
    if subtitle_position == "auto":
        bbox = _detect_subtitle_region(paths.video, output_dir, config)
        if bbox:
            bbox = bbox.enforce_min_width(src_w)
            delogo_region = (bbox.x, bbox.y, bbox.w, bbox.h)
            detected_style = compute_detected_subtitle_style(bbox, src_w, src_h)
            print(f"[step6] Detected box y={bbox.y} h={bbox.h}")
        else:
            print("[step6] No original text detected → using default position")
            subtitle_position = "bottom"
    
    # Compose each platform
    primary_path = None
    for plat in remaining:
        if sentinels[plat].exists():
            continue
        
        print(f"[step6] Composing {plat} …")
        force_style = get_subtitle_style(plat, subtitle_position, detected_style)
        
        if plat == "tiktok" and is_landscape:
            final_path = _compose_tiktok_blur_bg(
                paths, config, force_style, src_w, src_h, delogo_region
            )
        elif plat == "tiktok":
            final_path = _compose_tiktok_portrait(
                paths, config, force_style, delogo_region
            )
        else:  # youtube
            final_path = _compose_youtube(
                paths, config, force_style, delogo_region
            )
        
        sentinels[plat].touch()
        size_mb = final_path.stat().st_size / 1_048_576
        print(f"[step6] {plat} → {final_path} ({size_mb:.1f} MB)")
        
        if primary_path is None:
            primary_path = final_path
    
    # Backward compat: write final.mp4
    yt_out = output_dir / "final_youtube.mp4"
    tt_out = output_dir / "final_tiktok.mp4"
    if yt_out.exists():
        shutil.copy2(yt_out, output_dir / "final.mp4")
        (output_dir / ".step6.done").touch()
    elif tt_out.exists():
        shutil.copy2(tt_out, output_dir / "final.mp4")
        (output_dir / ".step6.done").touch()
    
    return primary_path or output_dir / "final.mp4"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Step 6: compose final video")
    parser.add_argument("output_dir")
    parser.add_argument("--crf", type=int, default=23)
    parser.add_argument("--platform", default="youtube", choices=["youtube", "tiktok", "both"])
    parser.add_argument("--tiktok-crop-x", type=int, default=None, dest="tiktok_crop_x")
    parser.add_argument("--subtitle-position", default="bottom", choices=["bottom", "top", "auto"], dest="subtitle_position")
    parser.add_argument("--ollama-url", default="https://ollama.com", dest="ollama_url")
    parser.add_argument("--model", default="gemini-3-flash-preview:cloud")
    parser.add_argument("--ollama-api-key", default=None, dest="ollama_api_key")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    compose(
        Path(args.output_dir), crf=args.crf, platform=args.platform,
        tiktok_crop_x=args.tiktok_crop_x, subtitle_position=args.subtitle_position,
        ollama_url=args.ollama_url, model=args.model,
        ollama_api_key=args.ollama_api_key, verbose=args.verbose
    )
