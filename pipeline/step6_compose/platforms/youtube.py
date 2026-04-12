"""YouTube platform composition (16:9)."""

import subprocess
from pathlib import Path
from typing import Optional

from .base import ComposePlatform, VideoPaths, ComposeConfig


_FFMPEG_FULL = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
_FFMPEG_BIN = str(_FFMPEG_FULL) if _FFMPEG_FULL.exists() else "ffmpeg"


def _escape_srt_path(srt_path: Path) -> str:
    """Escape SRT path for ffmpeg subtitles filter."""
    return str(srt_path.resolve()).replace("\\", "/").replace(":", "\\:")


class YouTubeCompose(ComposePlatform):
    """YouTube 16:9 composition (watermark and logo removal done in step_remove_logo)."""
    
    name = "youtube"
    
    def compose(
        self,
        paths: VideoPaths,
        config: ComposeConfig,
        force_style: str,
        src_w: int,
        src_h: int,
        delogo_region: Optional[tuple[int, int, int, int]] = None,
    ) -> Path:
        """Compose YouTube video (16:9) with burned-in subtitles.
        
        Note: watermark and logo removal are handled in step_remove_logo.
        """
        # Build subtitle filter
        srt_escaped = _escape_srt_path(paths.srt)
        vf_filter = f"subtitles={srt_escaped}:force_style='{force_style}'"
        
        # Build ffmpeg command
        final_path = paths.output_dir / "final_youtube.mp4"
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
            raise RuntimeError(f"ffmpeg YouTube composition failed:\n{result.stderr[-3000:]}")
        
        return final_path
