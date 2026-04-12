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


def parse_json_response(text: str, expected: int) -> list[str]:
    """Parse a JSON array from LLM output, with line-split fallback.

    If Gemini returns more items than expected (due to splitting),
    concatenate excess items into the last segment to preserve total count.
    """
    cleaned = text.strip()
    cleaned = re.sub(r'^```[^\n]*\n?', '', cleaned, flags=re.MULTILINE)
    cleaned = cleaned.rstrip('`').strip()
    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            lines = [str(item).strip() for item in result]
            if len(lines) > expected:
                print(f"\n[step4] WARNING: Expected {expected} translations, got {len(lines)}")
                print(f"[step4] Merging excess items into final segment to prevent data loss...")
                # Merge excess items into the last expected segment
                excess = lines[expected-1:] + lines[expected:]
                merged = " ".join(excess)
                lines = lines[:expected-1] + [merged]
            elif len(lines) < expected:
                print(f"\n[step4] WARNING: Expected {expected} translations, got {len(lines)}")
                lines += [""] * (expected - len(lines))
            return lines
    except (json.JSONDecodeError, ValueError):
        pass
    # Fallback: plain line split
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if len(lines) < expected:
        lines += [""] * (expected - len(lines))
    return lines[:expected]


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
    return (
        f"\n[Lưu ý cảnh quay: có cắt cảnh tại {timestamps}. "
        "Hãy dịch ngắn gọn ở các phân đoạn gần ranh giới cảnh.]"
    )


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

    parts.extend(s.content.strip() for s in subs)
    parts.append("")
    parts.append('Trả về CHỈ một mảng JSON các chuỗi đã dịch, đúng thứ tự: ["dịch 1", "dịch 2", ...]')

    scene_note = _build_scene_note(subs, cuts)
    if scene_note:
        parts.append(scene_note)

    return "\n".join(parts)
