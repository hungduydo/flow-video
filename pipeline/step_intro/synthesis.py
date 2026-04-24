"""Generate TTS audio for intro text."""

import logging
import subprocess
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)


def _get_audio_duration(audio_path: Path) -> float:
    """Get duration of audio file in seconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        duration = float(result.stdout.strip())
        return duration
    except Exception as e:
        logger.error(f"Failed to get audio duration: {e}")
        return 0.0


def synthesize_intro(
    intro_text: str,
    output_path: Path,
    provider: str = "edge_tts",
    language: str = "vi-VN",
) -> Tuple[Path, float]:
    """
    Synthesize intro text to speech.

    Args:
        intro_text: Vietnamese intro text
        output_path: Path to save audio
        provider: TTS provider ("edge_tts" or "elevenlabs")
        language: Language code (default "vi-VN")

    Returns:
        (audio_file_path, duration_seconds)
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if provider == "edge_tts":
        _synthesize_edge_tts(intro_text, output_path, language)
    elif provider == "elevenlabs":
        _synthesize_elevenlabs(intro_text, output_path, language)
    else:
        raise ValueError(f"Unsupported TTS provider: {provider}")

    # Measure duration
    duration = _get_audio_duration(output_path)
    logger.info(f"TTS synthesis complete: {output_path} ({duration:.2f}s)")

    return output_path, duration


def _synthesize_edge_tts(
    intro_text: str,
    output_path: Path,
    language: str = "vi-VN",
) -> None:
    """Synthesize using Microsoft Edge TTS."""
    try:
        import edge_tts

        async def tts():
            voice = "vi-VN-HoaiMyNeural"  # Vietnamese female voice
            communicate = edge_tts.Communicate(intro_text, voice=voice, rate="+0%")
            await communicate.save(str(output_path))

        import asyncio

        asyncio.run(tts())
        logger.info(f"Edge TTS synthesis complete: {output_path}")

    except ImportError:
        raise ImportError("edge_tts not installed. Run: pip install edge-tts")
    except Exception as e:
        logger.error(f"Edge TTS synthesis failed: {e}")
        raise


def _synthesize_elevenlabs(
    intro_text: str,
    output_path: Path,
    language: str = "vi-VN",
) -> None:
    """Synthesize using ElevenLabs TTS."""
    try:
        import os

        from elevenlabs.client import ElevenLabs

        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY not set")

        client = ElevenLabs(api_key=api_key)

        # Vietnamese voice
        voice_id = "EXAVITQu4vr4xnSDxMaL"  # Example Vietnamese voice

        audio = client.text_to_speech.convert(
            text=intro_text,
            voice_id=voice_id,
            model_id="eleven_multilingual_v2",
        )

        with open(output_path, "wb") as f:
            for chunk in audio:
                f.write(chunk)

        logger.info(f"ElevenLabs TTS synthesis complete: {output_path}")

    except ImportError:
        raise ImportError("elevenlabs not installed. Run: pip install elevenlabs")
    except Exception as e:
        logger.error(f"ElevenLabs TTS synthesis failed: {e}")
        raise
