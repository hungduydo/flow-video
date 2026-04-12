"""Ollama Cloud translation provider using gemini-3-flash-preview:cloud."""

import os
import time

import srt
from tqdm import tqdm

from ..utils import CONTEXT_SIZE, batch, build_prompt, parse_json_response

MODEL = "gemini-3-flash-preview:cloud"
OLLAMA_BASE_URL = "https://ollama.com"  # Ollama Cloud API endpoint


def _make_ollama_client(base_url: str, api_key: str | None):
    """Create an Ollama client with API key authentication."""
    from ollama import Client
    resolved_key = api_key or os.environ.get("OLLAMA_API_KEY", "")
    return Client(
        host=base_url,
        headers={"Authorization": f"Bearer {resolved_key}"} if resolved_key else {},
    )


def _translate_batch(client, subs: list[srt.Subtitle], context: list[srt.Subtitle], system_prompt: str) -> list[str]:
    """Translate a batch of subtitles using Ollama Cloud."""
    prompt = build_prompt(subs, context, system_prompt)
    delay = 1.0
    for attempt in range(5):
        try:
            response = client.chat(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                stream=False,
            )
            # ollama SDK returns a Pydantic ChatResponse — use attribute access
            text = response.message.content if hasattr(response, 'message') else response.get('message', {}).get('content', '')
            if not text:
                raise RuntimeError(f"Empty response from model {MODEL!r}")
            return parse_json_response(text, len(subs))
        except Exception as e:
            if attempt == 4:
                raise
            print(f"\n[step4] Ollama Cloud error ({e}), retry in {delay:.0f}s …")
            time.sleep(delay)
            delay = min(delay * 2, 60)
    return []


def run(subtitles: list[srt.Subtitle], system_prompt: str) -> list[str]:
    """Translate subtitles using Ollama Cloud."""
    try:
        from ollama import Client
    except ImportError:
        raise ImportError("Ollama SDK required for Ollama Cloud. Install: pip install ollama")

    api_key = os.getenv("OLLAMA_API_KEY")
    if not api_key:
        raise EnvironmentError("OLLAMA_API_KEY not set — add it to .env")

    client = _make_ollama_client(OLLAMA_BASE_URL, api_key)

    batches = batch(subtitles)
    print(f"[step4] Total segments: {len(subtitles)}, split into {len(batches)} batch(es)")
    translated: list[str] = []

    for i, b in enumerate(tqdm(batches, desc="[step4] Ollama Cloud", unit="batch"), 1):
        context = subtitles[max(0, len(translated) - CONTEXT_SIZE) : len(translated)]
        result = _translate_batch(client, b, context, system_prompt)
        translated.extend(result)
        print(f"[step4] Batch {i}: {len(b)} segments → {len(result)} translations")
        time.sleep(0.5)

    print(f"[step4] Total translations: {len(translated)} (expected {len(subtitles)})")
    return translated
