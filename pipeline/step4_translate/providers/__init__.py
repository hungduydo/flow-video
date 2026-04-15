"""Translation providers (Gemini, Claude, Ollama Cloud, Ollama local)."""

from typing import Protocol

import srt


class TTSProvider(Protocol):
    """Translation provider interface."""

    def run(self, subtitles: list[srt.Subtitle], system_prompt: str) -> list[str]:
        """Translate subtitles. Returns list of translated lines."""
        ...


def get_provider(name: str):
    """Get a translation provider by name."""
    if name == "gemini":
        from . import gemini
        return gemini
    elif name == "claude":
        from . import claude
        return claude
    elif name == "ollama_cloud":
        from . import ollama_cloud
        return ollama_cloud
    elif name == "ollama":
        from . import ollama
        return ollama
    else:
        raise ValueError(f"Unknown translation provider: {name!r}. Available: gemini, claude, ollama_cloud, ollama")
