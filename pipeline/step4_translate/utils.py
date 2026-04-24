import json
import re

import srt

BATCH_SIZE = 30  # reduced from 50 to avoid Gemini rate limits & ensure accuracy
BATCH_CHARS = 4000
CONTEXT_SIZE = 3  # previous segments passed as read-only context each batch

_CJK_RE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]')


def count_cjk(text: str) -> int:
    return len(_CJK_RE.findall(text))


def clean_subtitles(subtitles: list[srt.Subtitle]) -> list[srt.Subtitle]:
    """Drop noise segments: pure punctuation or single-character fragments."""
    cleaned = [s for s in subtitles if count_cjk(s.content) >= 2]
    for i, sub in enumerate(cleaned, 1):
        sub.index = i
    return cleaned


def batch(subtitles: list[srt.Subtitle]) -> list[list[srt.Subtitle]]:
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


def parse_json_response(text: str, expected: int) -> list[str] | None:
    """Parse a JSON array from LLM output.

    Returns a list of exactly `expected` strings, or None if the count
    doesn't match (signals the caller to retry the batch).
    """
    cleaned = text.strip()
    cleaned = re.sub(r'^```[^\n]*\n?', '', cleaned, flags=re.MULTILINE)
    cleaned = cleaned.rstrip('`').strip()
    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            lines = [str(item).strip() for item in result]
            if len(lines) == expected:
                return lines
            print(f"\n[step4] WARNING: Expected {expected} translations, got {len(lines)} — will retry")
            return None
    except (json.JSONDecodeError, ValueError):
        pass
    # Fallback: plain line split
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if len(lines) == expected:
        return lines
    print(f"\n[step4] WARNING: Line-split fallback got {len(lines)}, expected {expected} — will retry")
    return None


def _build_scene_note(subs: list[srt.Subtitle], cuts: list[float] | None) -> str:
    """Return a note about scene boundaries that fall within this batch, or ''."""
    if not cuts or not subs:
        return ""
    batch_start = subs[0].start.total_seconds()
    batch_end = subs[-1].end.total_seconds()
    relevant = [c for c in cuts if batch_start <= c <= batch_end]
    if not relevant:
        return ""
    timestamps = ", ".join(f"{c:.2f}s" for c in sorted(relevant))
    return f"\n[Lưu ý cảnh quay: có cắt cảnh tại {timestamps}.]"


def build_prompt(
    subs: list[srt.Subtitle],
    context: list[srt.Subtitle],
    system_prompt: str,
    cuts: list[float] | None = None,
) -> str:
    """Build the user-facing translation prompt with optional context prefix."""
    parts: list[str] = [system_prompt, ""]

    if context:
        parts.append("Ngữ cảnh trước (KHÔNG dịch, chỉ để hiểu mạch văn):")
        parts.extend(s.content.strip() for s in context)
        parts.append("---")

    for i, s in enumerate(subs, 1):
        parts.append(f"{i}. {s.content.strip()}")

    n = len(subs)
    parts.append("")
    parts.append(f'Trả về CHỈ một mảng JSON đúng {n} phần tử, tương ứng 1-1 với {n} dòng trên:')
    parts.append(f'["dịch dòng 1", "dịch dòng 2", ..., "dịch dòng {n}"]')
    parts.append(f'BẮT BUỘC đúng {n} phần tử. KHÔNG gộp hay tách bất kỳ dòng nào. Dòng rất ngắn vẫn phải có 1 phần tử riêng.')

    scene_note = _build_scene_note(subs, cuts)
    if scene_note:
        parts.append(scene_note)

    return "\n".join(parts)
