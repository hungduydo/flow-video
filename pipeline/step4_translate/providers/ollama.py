"""Local Ollama translation provider (http://localhost:11434)."""

import os
import time

import srt
from tqdm import tqdm

from ..utils import CONTEXT_SIZE, batch, build_prompt, parse_json_response

DEFAULT_MODEL = "qwen2.5:7b"
OLLAMA_BASE_URL = "http://localhost:11434"


def _translate_batch(client, model: str, subs: list[srt.Subtitle], context: list[srt.Subtitle], system_prompt: str) -> list[str]:
    prompt = build_prompt(subs, context, system_prompt)
    delay = 1.0
    for attempt in range(5):
        try:
            response = client.chat(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                stream=False,
            )
            text = response.message.content if hasattr(response, "message") else response.get("message", {}).get("content", "")
            if not text:
                raise RuntimeError(f"Empty response from model {model!r}")
            result = parse_json_response(text, len(subs))
            if result is not None:
                return result
            if attempt == 4:
                print(f"[step4] WARNING: count mismatch after 5 attempts, padding with empty strings")
                return [""] * len(subs)
            print(f"[step4] Retrying batch (attempt {attempt + 2}/5) in {delay:.0f}s …")
            time.sleep(delay)
            delay = min(delay * 2, 60)
        except Exception as e:
            if attempt == 4:
                raise
            print(f"\n[step4] Ollama error ({e}), retry in {delay:.0f}s …")
            time.sleep(delay)
            delay = min(delay * 2, 60)
    return [""] * len(subs)


def run(subtitles: list[srt.Subtitle], system_prompt: str) -> list[str]:
    try:
        from ollama import Client
    except ImportError:
        raise ImportError("Ollama SDK required. Install: pip install ollama")

    model = os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)
    base_url = os.getenv("OLLAMA_BASE_URL", OLLAMA_BASE_URL)
    client = Client(host=base_url)

    print(f"[step4] Ollama local: {base_url} — model: {model}")
    batches = batch(subtitles)
    print(f"[step4] Total segments: {len(subtitles)}, split into {len(batches)} batch(es)")
    translated: list[str] = []

    for i, b in enumerate(tqdm(batches, desc="[step4] Ollama", unit="batch"), 1):
        context = subtitles[max(0, len(translated) - CONTEXT_SIZE) : len(translated)]
        result = _translate_batch(client, model, b, context, system_prompt)
        translated.extend(result)
        print(f"[step4] Batch {i}: {len(b)} segments → {len(result)} translations")

    print(f"[step4] Total translations: {len(translated)} (expected {len(subtitles)})")
    return translated
