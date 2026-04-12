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

from .platforms import (
    VideoPaths, ComposeConfig, get_platform,
)


# Subtitle position defaults (fallback when no detection available)
_SUBTITLE_FORCE_STYLE = {
    ("youtube", "bottom"): "Alignment=2,MarginV=20",   # Top-center, 20px from top
    ("youtube", "top"):    "Alignment=6,MarginV=20",
    ("tiktok",  "bottom"): "Alignment=2,MarginV=384",  # Bottom-center, 20% from bottom
    ("tiktok",  "top"):    "Alignment=6,MarginV=30",
}


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

def compute_detected_subtitle_style(bbox: SubtitleRegion, src_h: int) -> str:
    """Compute ASS force_style for YouTube based on detected subtitle bbox.
    
    Places subtitle 10px below the detected text.
    Alignment=6 (left-center), MarginV as percentage from top.
    
    Args:
        bbox: Detected subtitle bounding box (pixels)
        src_h: Source video height (pixels)
    
    Returns:
        force_style string with MarginV as percentage
    """
    # Calculate pixel position: top of detected box + height + 10px gap
    pixel_pos = max(20, src_h - (bbox.y + bbox.h + 10))
    play_rect = (pixel_pos * 288)/src_h 
    print(f"[step6] Subtitle style: Alignment=2,MarginV={play_rect}")
    return f"Alignment=2,MarginV={play_rect},BorderStyle=3,OutlineColour=&H80000000"


def get_subtitle_style(platform: str, position: str, detected_style: Optional[str] = None) -> str:
    """Get subtitle force_style: use detected if available, else use default."""
    if detected_style and platform == "youtube":
        return detected_style
    return _SUBTITLE_FORCE_STYLE.get((platform, position), _SUBTITLE_FORCE_STYLE[("youtube", "bottom")])


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


def _detect_subtitle_region(
    video_path: Path,
    output_dir: Path,
    config: ComposeConfig,
) -> Optional[SubtitleRegion]:
    """Detect subtitle region from cached file if available.
    
    Note: LLM detection removed. Use detected_regions.json if available.
    """
    regions_file = output_dir / "detected_regions.json"
    bbox = SubtitleRegion.from_json_file(regions_file)
    
    if bbox:
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
        crf=crf, tiktok_crop_x=tiktok_crop_x,
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
            detected_style = compute_detected_subtitle_style(bbox, src_h)
            print(f"[step6] Detected box y={bbox.y} h={bbox.h} → MarginV={detected_style.split('=')[-1]}%")
        else:
            print("[step6] No original text detected → using default position")
            subtitle_position = "bottom"
    
    # Compose each platform
    primary_path = None
    for plat in remaining:
        if sentinels[plat].exists():
            continue
        
        print(f"[step6] Composing {plat} {subtitle_position}…")
        force_style = get_subtitle_style(plat, subtitle_position, detected_style)
        
        # Select platform composer and compose
        if plat == "tiktok":
            if is_landscape:
                composer = get_platform("tiktok_blur_bg")
            else:
                composer = get_platform("tiktok_portrait")
        else:  # youtube
            composer = get_platform(plat)
        
        final_path = composer.compose(
            paths, config, force_style, src_w, src_h, delogo_region
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
