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
Bạn là chuyên gia dịch phụ đề phim. Dịch các dòng phụ đề tiếng Trung sang tiếng Việt.

Quy tắc:
- Chỉ xuất các dòng đã dịch, mỗi dòng một dòng, đúng thứ tự và số lượng
- KHÔNG thêm số thứ tự, timestamp, hoặc bất kỳ văn bản nào khác
- Giữ giọng điệu tự nhiên khi nói (trang trọng/thân mật tùy context)
- Phụ đề phải ngắn gọn, dễ đọc trên màn hình
"""

SYSTEM_PROMPT_SYLLABLE_EQ = """\
Bạn là Dubbing Editor chuyên nghiệp. Dịch các dòng phụ đề tiếng Trung sang tiếng Việt.

Nguyên tắc "Đồng âm tiết" (bắt buộc):
- Mỗi dòng được gắn nhãn [Nchữ] cho biết số ký tự Hán nguồn.
- Số từ tiếng Việt phải nằm trong khoảng N đến floor(N × 1.5).
  Ví dụ: [5chữ] → 5–7 từ | [8chữ] → 8–12 từ
- Ưu tiên từ Hán-Việt súc tích: 感情→tình cảm, 重要→quan trọng, 发展→phát triển
- Lược bỏ hư từ không cần thiết: của, thì, mà, là (hệ từ), rằng, những, đã/đang/sẽ (khi ngữ cảnh đủ rõ)
- KHÔNG lược bỏ: không, chưa, nếu, mà (nghịch đảo) — những từ mang nghĩa

Quy tắc đầu ra:
- Chỉ xuất các dòng đã dịch, mỗi dòng một dòng, đúng thứ tự và số lượng
- KHÔNG thêm số thứ tự, timestamp, hoặc bất kỳ văn bản nào khác
- Giữ giọng điệu tự nhiên khi nói (trang trọng/thân mật tùy context)
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


def _call_gemini(model: genai.GenerativeModel, prompt: str, expected: int) -> list[str]:
    """Call Gemini with retry, return exactly `expected` lines."""
    delay = 1.0
    for attempt in range(5):
        try:
            response = model.generate_content(prompt)
            lines = [l.strip() for l in response.text.strip().splitlines() if l.strip()]
            if len(lines) < expected:
                lines += [""] * (expected - len(lines))
            return lines[:expected]
        except Exception as e:
            if attempt == 4:
                raise
            print(f"\n[step4] Gemini error ({e}), retry in {delay:.0f}s …")
            time.sleep(delay)
            delay = min(delay * 2, 60)
    return []  # unreachable


def _translate_batch(model: genai.GenerativeModel, subs: list[srt.Subtitle]) -> list[str]:
    """Send one batch to Gemini, return translated lines (same count as input)."""
    source_text = "\n".join(sub.content for sub in subs)
    prompt = f"{SYSTEM_PROMPT}\n\n---\n{source_text}\n---"
    return _call_gemini(model, prompt, len(subs))


def _translate_batch_syllable_eq(model: genai.GenerativeModel, subs: list[srt.Subtitle]) -> list[str]:
    """Syllable-equivalence strategy: tag each line with char count, verify output length."""
    tagged = [f"[{len(s.content.strip())}chữ] {s.content.strip()}" for s in subs]
    source_text = "\n".join(tagged)
    prompt = f"{SYSTEM_PROMPT_SYLLABLE_EQ}\n\n---\n{source_text}\n---"

    lines = _call_gemini(model, prompt, len(subs))

    # Verify and retry overlong segments individually
    for i, (sub, line) in enumerate(zip(subs, lines)):
        cn_chars = len(sub.content.strip())
        max_words = max(cn_chars, int(cn_chars * 1.5))
        if len(line.split()) > max_words:
            lines[i] = _retry_single_syllable(model, sub.content.strip(), cn_chars, max_words)

    return lines


def _retry_single_syllable(model: genai.GenerativeModel, cn_text: str, cn_chars: int, max_words: int) -> str:
    """Single-segment retry with a strict word-budget prompt."""
    prompt = (
        f"Dịch câu phụ đề tiếng Trung sau sang tiếng Việt, "
        f"dùng TỐI ĐA {max_words} từ. Ưu tiên từ Hán-Việt.\n"
        f"Nguồn [{cn_chars} ký tự]: {cn_text}"
    )
    try:
        response = model.generate_content(prompt)
        return response.text.strip().splitlines()[0].strip()
    except Exception:
        return ""


def translate(output_dir: Path, strategy: str = "standard") -> Path:
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

    translate_fn = _translate_batch_syllable_eq if strategy == "syllable_equivalence" else _translate_batch
    for batch in tqdm(batches, desc="[step4] batches", unit="batch"):
        translated_lines.extend(translate_fn(model, batch))
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
        print("Usage: python -m pipeline.step4_translate <output_dir> [standard|syllable_equivalence]")
        sys.exit(1)
    _strategy = sys.argv[2] if len(sys.argv) > 2 else "standard"
    translate(Path(sys.argv[1]), strategy=_strategy)
