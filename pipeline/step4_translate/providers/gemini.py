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
            return parse_json_response(response.text, len(subs))
        except Exception as e:
            if attempt == 4:
                raise
            print(f"\n[step4] Gemini error ({e}), retry in {delay:.0f}s …")
            time.sleep(delay)
            delay = min(delay * 2, 60)
    return []


def run(subtitles: list[srt.Subtitle], system_prompt: str) -> list[str]:
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY not set — add it to .env")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(MODEL)

    batches = batch(subtitles)
    translated: list[str] = []

    for b in tqdm(batches, desc="[step4] Gemini", unit="batch"):
        context = subtitles[max(0, len(translated) - CONTEXT_SIZE) : len(translated)]
        translated.extend(_translate_batch(model, b, context, system_prompt))
        time.sleep(0.5)

    return translated
