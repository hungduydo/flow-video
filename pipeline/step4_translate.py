"""
Step 4: Translate captions_cn.srt (Chinese) → captions_vn.srt (Vietnamese)
        using Gemini 1.5 Flash.

Strategy:
  - Parse SRT → extract text segments only (never send raw SRT to Gemini)
  - Send batches of ≤50 segments or ≤4000 source chars to preserve context
  - Gemini returns numbered lines; we re-inject original timestamps after
  - Never trust Gemini to preserve SRT format

Output:
  output/{video_id}/captions_vn.srt
  output/{video_id}/.step4.done  (sentinel)
"""

import os
import sys
import time
from pathlib import Path

import google.generativeai as genai
import srt
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

BATCH_SIZE = 50
BATCH_CHARS = 4000
MODEL = "gemini-3.1-flash-lite-preview"

SYSTEM_PROMPT = """\
You are a professional subtitle translator. T
Vai trò: Bạn là một chuyên gia dịch thuật phim (Dubbing Editor) chuyên nghiệp.

Nhiệm vụ: ranslate the following Chinese subtitle lines to Vietnamese. 

Yêu cầu khắt khe về định dạng và độ dài:

Nguyên tắc "Đồng âm tiết": Số lượng chữ (âm tiết) trong câu tiếng Việt phải tương đương hoặc chỉ chênh lệch tối đa ±10% so với câu gốc để khớp với khẩu hình và thời lượng video (Time-sync).

Văn phong: Sử dụng từ Hán Việt hoặc từ ghép súc tích để nén nghĩa. Loại bỏ các từ đệm không cần thiết (thì, mà, là, rằng, những...) nhưng vẫn phải giữ được sắc thái biểu cảm và sự mượt mà.
Rules:
- Output ONLY the translated lines, one per line, in the same order and count
- Do NOT add line numbers, timestamps, or any extra text
- Preserve speaker tone (formal/informal) and natural spoken Vietnamese
- Keep short — subtitles must be readable on screen
"""


def _batch(subtitles: list[srt.Subtitle]) -> list[list[srt.Subtitle]]:
    """Split into batches by segment count or total source character count."""
    batches: list[list[srt.Subtitle]] = []
    current: list[srt.Subtitle] = []
    current_chars = 0
    for sub in subtitles:
        char_count = len(sub.content)
        if current and (len(current) >= BATCH_SIZE or current_chars + char_count > BATCH_CHARS):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(sub)
        current_chars += char_count
    if current:
        batches.append(current)
    return batches


def _translate_batch(model: genai.GenerativeModel, subs: list[srt.Subtitle]) -> list[str]:
    """Send one batch to Gemini, return translated lines (same count as input)."""
    source_text = "\n".join(sub.content for sub in subs)
    prompt = f"{SYSTEM_PROMPT}\n\n---\n{source_text}\n---"

    delay = 1.0
    for attempt in range(5):
        try:
            response = model.generate_content(prompt)
            lines = [l.strip() for l in response.text.strip().splitlines() if l.strip()]
            # Pad or trim to match input count (defensive)
            if len(lines) < len(subs):
                lines += [""] * (len(subs) - len(lines))
            return lines[: len(subs)]
        except Exception as e:
            if attempt == 4:
                raise
            print(f"\n[step4] Gemini error ({e}), retry in {delay:.0f}s …")
            time.sleep(delay)
            delay = min(delay * 2, 60)
    return []  # unreachable


def translate(output_dir: Path) -> Path:
    sentinel = output_dir / ".step4.done"
    if sentinel.exists():
        print("[step4] Skip — captions_vn.srt already exists")
        return output_dir / "captions_vn.srt"

    cn_srt_path = output_dir / "captions_cn.srt"
    if not cn_srt_path.exists():
        raise FileNotFoundError(f"captions_cn.srt not found in {output_dir}")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY not set — add it to .env")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(MODEL)

    subtitles = list(srt.parse(cn_srt_path.read_text(encoding="utf-8")))
    print(f"[step4] Translating {len(subtitles)} segments (Chinese → Vietnamese) …")

    batches = _batch(subtitles)
    translated_lines: list[str] = []

    for batch in tqdm(batches, desc="[step4] batches", unit="batch"):
        translated_lines.extend(_translate_batch(model, batch))
        time.sleep(0.5)  # gentle rate-limit buffer between batches

    # Rebuild SRT with original timestamps + translated text
    vn_subtitles = [
        srt.Subtitle(
            index=sub.index,
            start=sub.start,
            end=sub.end,
            content=translated_lines[i],
        )
        for i, sub in enumerate(subtitles)
    ]

    vn_srt_path = output_dir / "captions_vn.srt"
    vn_srt_path.write_text(srt.compose(vn_subtitles), encoding="utf-8")

    sentinel.touch()
    print(f"[step4] Done — {vn_srt_path}")
    return vn_srt_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m pipeline.step4_translate <output_dir>")
        sys.exit(1)
    translate(Path(sys.argv[1]))
