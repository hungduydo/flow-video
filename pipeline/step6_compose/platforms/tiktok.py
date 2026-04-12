"""TikTok platform composition (9:16)."""

import subprocess
from pathlib import Path
from typing import Optional

from .base import ComposePlatform, VideoPaths, ComposeConfig


_FFMPEG_FULL = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
_FFMPEG_BIN = str(_FFMPEG_FULL) if _FFMPEG_FULL.exists() else "ffmpeg"

TIKTOK_W, TIKTOK_H = 1080, 1920


def _escape_srt_path(srt_path: Path) -> str:
    """Escape SRT path for ffmpeg subtitles filter."""
    return str(srt_path.resolve()).replace("\\", "/").replace(":", "\\:")


def _get_tiktok_crop(width: int, height: int, crop_x: Optional[int] = None) -> str:
    """Build TikTok 9:16 crop filter."""
    target_w = int(height * 9 / 16)
    x_offset = (width - target_w) // 2 if crop_x is None else max(0, min(crop_x, width - target_w))
    return f"crop={target_w}:{height}:{x_offset}:0"


class TikTokPortrait(ComposePlatform):
    """TikTok 9:16 portrait (center crop from landscape). Watermark/logo removal done in step_remove_logo."""
    
    name = "tiktok_portrait"
    
    def compose(
        self,
        paths: VideoPaths,
        config: ComposeConfig,
        force_style: str,
        src_w: int,
        src_h: int,
        delogo_region: Optional[tuple[int, int, int, int]] = None,
    ) -> Path:
        """Compose TikTok portrait video (9:16 center crop with subtitles)."""
        # TikTok 9:16 crop
        crop_filter = _get_tiktok_crop(src_w, src_h, config.tiktok_crop_x)
        
        # Subtitles
        srt_escaped = _escape_srt_path(paths.srt)
        vf_filter = f"{crop_filter},subtitles={srt_escaped}:force_style='{force_style}'"
        
        # Build ffmpeg command
        final_path = paths.output_dir / "final_tiktok.mp4"
        cmd = [
            _FFMPEG_BIN, "-y",
            "-i", str(paths.video),
            "-i", str(paths.audio),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-vf", vf_filter,
            "-c:v", "libx264",
            "-crf", str(config.crf),
            "-preset", "fast",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(final_path),
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg TikTok portrait composition failed:\n{result.stderr[-3000:]}")
        
        return final_path


class TikTokBlurBg(ComposePlatform):
    """TikTok 9:16 with blurred background (landscape source). Watermark/logo removal done in step_remove_logo."""
    
    name = "tiktok_blur_bg"
    
    def compose(
        self,
        paths: VideoPaths,
        config: ComposeConfig,
        force_style: str,
        src_w: int,
        src_h: int,
        delogo_region: Optional[tuple[int, int, int, int]] = None,
    ) -> Path:
        """Compose TikTok video with blurred background layout and subtitles."""
        srt_escaped = _escape_srt_path(paths.srt)
        
        # Background: scale + crop + blur
        bg_filter = f"scale=-2:{TIKTOK_H},crop={TIKTOK_W}:{TIKTOK_H},boxblur=20:5"
        
        # Foreground: scale to canvas width
        fg_filter = f"scale={TIKTOK_W}:-2"
        
        # Build filter_complex with overlay and subtitles
        filter_complex = (
            f"[0:v]split=2[bg_in][fg_in];"
            f"[bg_in]{bg_filter}[bg];"
            f"[fg_in]{fg_filter}[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[composed];"
            f"[composed]subtitles={srt_escaped}:force_style='{force_style}'[out]"
        )
        
        # Build ffmpeg command
        final_path = paths.output_dir / "final_tiktok.mp4"
        cmd = [
            _FFMPEG_BIN, "-y",
            "-i", str(paths.video),
            "-i", str(paths.audio),
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-map", "1:a:0",
            "-c:v", "libx264",
            "-crf", str(config.crf),
            "-preset", "fast",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(final_path),
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg TikTok blur-bg composition failed:\n{result.stderr[-3000:]}")
        
        return final_path
