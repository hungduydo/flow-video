import os

from .base import TTSProvider
from .edge_tts_provider import EdgeTTSProvider
from .elevenlabs_provider import ElevenLabsProvider, ELEVENLABS_VOICE_ID_DEFAULT

__all__ = ["TTSProvider", "get_provider"]


def get_provider(name: str) -> TTSProvider:
    """Return a TTSProvider instance for the given provider name.

    Available providers: edge_tts, elevenlabs

    To add a new provider:
      1. Create pipeline/tts_providers/my_provider.py implementing TTSProvider
      2. Add an elif branch here
      3. Add the name to --tts-provider choices in main.py and flow_v2/main_v2.py
    """
    if name == "edge_tts":
        return EdgeTTSProvider()
    elif name == "elevenlabs":
        return ElevenLabsProvider(
            api_key=os.getenv("ELEVENLABS_API_KEY", "sk_f1d1f2879e004adb762ad2b57aba0b4859ca9fafab0540d7"),
            voice_id=os.environ.get("ELEVENLABS_VOICE_ID", ELEVENLABS_VOICE_ID_DEFAULT),
        )
    else:
        raise ValueError(f"Unknown TTS provider: {name!r}. Available: edge_tts, elevenlabs")
