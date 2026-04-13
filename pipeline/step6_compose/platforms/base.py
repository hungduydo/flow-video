"""Base class for video composition platforms."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class VideoPaths:
    """Paths for video composition."""
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
    """Composition configuration."""
    crf: int = 23
    tiktok_crop_x: Optional[int] = None
    subtitle_position: str = "bottom"
    show_subtitle: bool = True
    verbose: bool = False
    ollama_url: str = "https://ollama.com"
    model: str = "gemini-3-flash-preview:cloud"
    ollama_api_key: Optional[str] = None


class ComposePlatform(ABC):
    """Base class for platform-specific composition."""
    
    name: str = "base"
    
    @abstractmethod
    def compose(
        self,
        paths: VideoPaths,
        config: ComposeConfig,
        force_style: str,
        src_w: int,
        src_h: int,
        delogo_region: Optional[tuple[int, int, int, int]] = None,
    ) -> Path:
        """Compose video for this platform.
        
        Args:
            paths: VideoPaths instance
            config: ComposeConfig instance
            force_style: ASS force_style string
            src_w: source video width
            src_h: source video height
            delogo_region: (x, y, w, h) tuple or None
            
        Returns:
            Path to the composed video
        """
        ...
