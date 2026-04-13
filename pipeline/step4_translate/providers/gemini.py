"""Gemini 2.0 Flash translation provider."""

import os
import time

import srt
from tqdm import tqdm

from ..utils import CONTEXT_SIZE, batch, build_prompt, parse_json_response

MODEL = "gemini-3.1-flash-lite-preview"


def _translate_batch(model, subs: list[srt.Subtitle], context: list[srt.Subtitle], system_prompt: str) -> list[str]:
    prompt = build_prompt(subs, context, system_prompt)
    delay = 1.0
    for attempt in range(5):
        try:
            response = model.generate_content(prompt)
            if not response.candidates:
                reason = getattr(response.prompt_feedback, "block_reason", "unknown")
                print(f"\n[step4] Gemini blocked (reason={reason}), skipping batch with empty translations")
                return [""] * len(subs)
            result = parse_json_response(response.text, len(subs))
            if result is not None:
                return result
            # Count mismatch — retry with same delay logic
            if attempt == 4:
                print(f"[step4] WARNING: count mismatch after 5 attempts, padding with empty strings")
                return [""] * len(subs)
            print(f"[step4] Retrying batch (attempt {attempt + 2}/5) in {delay:.0f}s …")
            time.sleep(delay)
            delay = min(delay * 2, 60)
        except Exception as e:
            if attempt == 4:
                raise
            print(f"\n[step4] Gemini error ({e}), retry in {delay:.0f}s …")
            time.sleep(delay)
            delay = min(delay * 2, 60)
    return [""] * len(subs)


def run(subtitles: list[srt.Subtitle], system_prompt: str) -> list[str]:
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY not set — add it to .env")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(MODEL)

    batches = batch(subtitles)
    print(f"[step4] Total segments: {len(subtitles)}, split into {len(batches)} batch(es)")
    translated: list[str] = []

    for i, b in enumerate(tqdm(batches, desc="[step4] Gemini", unit="batch"), 1):
        context = subtitles[max(0, len(translated) - CONTEXT_SIZE) : len(translated)]
        result = _translate_batch(model, b, context, system_prompt)
        translated.extend(result)
        print(f"[step4] Batch {i}: {len(b)} segments → {len(result)} translations")
        time.sleep(0.5)

    print(f"[step4] Total translations: {len(translated)} (expected {len(subtitles)})")
    return translated
