"""Claude Sonnet 4.6 translation provider."""

import os
import time

import srt
from tqdm import tqdm

from ..utils import CONTEXT_SIZE, batch, build_prompt, parse_json_response

MODEL = "claude-sonnet-4-6"


def _translate_batch(client, subs: list[srt.Subtitle], context: list[srt.Subtitle], system_prompt: str) -> list[str]:
    import anthropic

    # For Claude, system prompt goes via system param; build_prompt gets empty system
    user_msg = build_prompt(subs, context, "")
    delay = 1.0
    for attempt in range(5):
        try:
            with client.messages.stream(
                model=MODEL,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_msg}],
            ) as stream:
                response = stream.get_final_message()
            text = next((b.text for b in response.content if b.type == "text"), "")
            result = parse_json_response(text, len(subs))
            if result is not None:
                return result
            # Count mismatch — retry
            if attempt == 4:
                print(f"[step4] WARNING: count mismatch after 5 attempts, padding with empty strings")
                return [""] * len(subs)
            print(f"[step4] Retrying batch (attempt {attempt + 2}/5) in {delay:.0f}s …")
            time.sleep(delay)
            delay = min(delay * 2, 60)
        except anthropic.RateLimitError as e:
            if attempt == 4:
                raise
            wait = int(e.response.headers.get("retry-after", delay))
            print(f"\n[step4] Claude rate limit, retry in {wait}s …")
            time.sleep(wait)
        except Exception as e:
            if attempt == 4:
                raise
            print(f"\n[step4] Claude error ({e}), retry in {delay:.0f}s …")
            time.sleep(delay)
            delay = min(delay * 2, 60)
    return [""] * len(subs)


def run(subtitles: list[srt.Subtitle], system_prompt: str) -> list[str]:
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set — add it to .env")

    client = anthropic.Anthropic(api_key=api_key)
    batches = batch(subtitles)
    print(f"[step4] Total segments: {len(subtitles)}, split into {len(batches)} batch(es)")
    translated: list[str] = []

    for i, b in enumerate(tqdm(batches, desc="[step4] Claude", unit="batch"), 1):
        context = subtitles[max(0, len(translated) - CONTEXT_SIZE) : len(translated)]
        result = _translate_batch(client, b, context, system_prompt)
        translated.extend(result)
        print(f"[step4] Batch {i}: {len(b)} segments → {len(result)} translations")
        time.sleep(0.3)

    print(f"[step4] Total translations: {len(translated)} (expected {len(subtitles)})")
    return translated
