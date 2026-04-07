import asyncio
from pathlib import Path

import edge_tts

from .base import TTSProvider

VOICE = "vi-VN-HoaiMyNeural"


class EdgeTTSProvider(TTSProvider):
    """Microsoft Edge TTS — free, no API key required."""

    def __init__(self, voice: str = VOICE) -> None:
        self.voice = voice

    @property
    def audio_format(self) -> dict:
        return {"sample_rate": 24000, "channels": "mono"}

    def synth(self, text: str, output_path: Path, retries: int = 3) -> None:
        asyncio.run(self._synth_async(text, output_path, retries))

    async def _synth_async(self, text: str, output_path: Path, retries: int) -> None:
        for attempt in range(retries):
            try:
                communicate = edge_tts.Communicate(text, self.voice)
                await communicate.save(str(output_path))
                return
            except edge_tts.exceptions.NoAudioReceived:
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(1.5 * (attempt + 1))
