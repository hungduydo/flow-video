"""
Step 4: Translate captions_cn.srt (Chinese) → captions_vn.srt (Vietnamese).

Two providers (selectable via `provider` argument):
  gemini  (default) — Gemini 2.0 Flash.   Requires GEMINI_API_KEY in .env.
  claude            — Claude Sonnet 4.6.  Requires ANTHROPIC_API_KEY in .env.

Output:
  output/{video_id}/captions_vn.srt
  output/{video_id}/.step4.done  (sentinel)
"""

import json
from pathlib import Path

import srt
from dotenv import load_dotenv

from .prompt import SYSTEM_PROMPT
from .utils import clean_subtitles

load_dotenv()


def translate(output_dir: Path, provider: str = "gemini") -> Path:
    sentinel = output_dir / ".step4.done"
    if sentinel.exists():
        print("[step4] Skip — captions_vn.srt already exists")
        return output_dir / "captions_vn.srt"

    cn_srt_path = output_dir / "captions_cn.srt"
    if not cn_srt_path.exists():
        raise FileNotFoundError(f"captions_cn.srt not found in {output_dir}")

    # Inject video title for domain vocabulary if available
    system_prompt = SYSTEM_PROMPT
    metadata_path = output_dir / "metadata.json"
    if metadata_path.exists():
        try:
            title = json.loads(metadata_path.read_text(encoding="utf-8")).get("title", "")
            if title:
                system_prompt = f'Video: "{title}"\n\n{SYSTEM_PROMPT}'
        except Exception:
            pass

    cuts: list[float] = []
    scenes_path = output_dir / "scenes.json"
    if scenes_path.exists():
        try:
            data = json.loads(scenes_path.read_text(encoding="utf-8"))
            cuts = data.get("cuts", [])
            if cuts:
                timestamps = ", ".join(f"{c:.2f}s" for c in cuts)
                system_prompt = (
                    system_prompt
                    + f"\n\n[Cảnh quay: có cắt cảnh tại {timestamps}. "
                    "Dịch ngắn gọn ở các phân đoạn gần ranh giới cảnh.]"
                )
                print(f"[step4] Loaded {len(cuts)} scene cut(s) from scenes.json")
        except Exception:
            pass

    subtitles = list(srt.parse(cn_srt_path.read_text(encoding="utf-8")))
    raw_count = len(subtitles)
    subtitles = clean_subtitles(subtitles)
    if len(subtitles) < raw_count:
        print(f"[step4] Cleaned {raw_count - len(subtitles)} noise segment(s) from CN")

    print(f"[step4] Translating {len(subtitles)} segments via {provider} …")

    if provider == "claude":
        from .providers.claude import run
    else:
        from .providers.gemini import run

    translated_lines = run(subtitles, system_prompt)

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
