import time
from pathlib import Path

import requests

from .base import TTSProvider

ELEVENLABS_VOICE_ID_DEFAULT = "UsgbMVmY3U59ijwK5mdh"  # https://elevenlabs.io/app/voice-library?voiceId=UsgbMVmY3U59ijwK5mdh
ELEVENLABS_MODEL_DEFAULT = "eleven_v3"
_API_BASE = "https://api.elevenlabs.io/v1"


class ElevenLabsProvider(TTSProvider):
    """ElevenLabs TTS — high quality, requires API key (ELEVENLABS_API_KEY)."""

    def __init__(
        self,
        api_key: str,
        voice_id: str = ELEVENLABS_VOICE_ID_DEFAULT,
        model_id: str = ELEVENLABS_MODEL_DEFAULT,
    ) -> None:
        if not api_key:
            raise EnvironmentError(
                "ELEVENLABS_API_KEY is not set. "
                "Get a key at https://elevenlabs.io and add it to your .env file."
            )
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id

    @property
    def audio_format(self) -> dict:
        return {"sample_rate": 44100, "channels": "stereo"}

    def synth(self, text: str, output_path: Path, retries: int = 3) -> None:
        url = f"{_API_BASE}/text-to-speech/{self.voice_id}"
        params = {"output_format": "mp3_44100_128"}
        headers = {"xi-api-key": self.api_key, "Content-Type": "application/json"}
        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }

        backoff = 2.0
        for attempt in range(retries):
            response = requests.post(url, params=params, headers=headers, json=payload, timeout=60)

            if response.status_code == 200:
                if not response.content:
                    raise RuntimeError(f"ElevenLabs returned empty audio for text: {text!r:.60}")
                output_path.write_bytes(response.content)
                return

            if response.status_code == 429:
                if attempt == retries - 1:
                    raise RuntimeError(f"ElevenLabs rate limit exceeded after {retries} retries.")
                time.sleep(min(backoff, 60.0))
                backoff *= 2
                continue

            if response.status_code in (401, 403):
                raise EnvironmentError(
                    f"ElevenLabs authentication failed (HTTP {response.status_code}). "
                    "Check your ELEVENLABS_API_KEY."
                )

            response.raise_for_status()
