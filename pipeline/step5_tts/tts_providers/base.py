from abc import ABC, abstractmethod
from pathlib import Path


class TTSProvider(ABC):
    """Abstract TTS provider. Implement to add a new provider."""

    @abstractmethod
    def synth(self, text: str, output_path: Path) -> None:
        """Synthesize text to an MP3 file at output_path."""
        ...

    @property
    @abstractmethod
    def audio_format(self) -> dict:
        """ffmpeg lavfi params for silence generation.

        Returns a dict with keys:
          sample_rate (int)  — e.g. 24000 or 44100
          channels    (str)  — e.g. "mono" or "stereo"
        """
        ...
