"""Unit tests for pipeline.step4_translate (utils, main)"""

import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import srt

from pipeline.step4_translate.utils import (
    batch,
    build_prompt,
    clean_subtitles,
    parse_json_response,
    _build_scene_note,
    BATCH_SIZE,
    BATCH_CHARS,
)
from pipeline.step4_translate.main import translate


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sub(idx, content, start=0.0, end=1.0):
    return srt.Subtitle(
        index=idx,
        start=timedelta(seconds=start),
        end=timedelta(seconds=end),
        content=content,
    )


# ── clean_subtitles ───────────────────────────────────────────────────────────

class TestCleanSubtitles:
    def test_drops_single_cjk(self):
        subs = [_sub(1, "研")]
        assert clean_subtitles(subs) == []

    def test_keeps_two_or_more_cjk(self):
        subs = [_sub(1, "你好")]
        assert len(clean_subtitles(subs)) == 1

    def test_drops_punctuation_only(self):
        subs = [_sub(1, "。！")]
        assert clean_subtitles(subs) == []

    def test_reindexes(self):
        subs = [_sub(1, "研"), _sub(2, "你好世界")]
        result = clean_subtitles(subs)
        assert result[0].index == 1

    def test_empty_input(self):
        assert clean_subtitles([]) == []


# ── batch ─────────────────────────────────────────────────────────────────────

class TestBatch:
    def test_single_batch_for_few_segments(self):
        subs = [_sub(i, "你好世界") for i in range(1, 6)]
        batches = batch(subs)
        assert len(batches) == 1

    def test_splits_at_batch_size(self):
        subs = [_sub(i, "你好") for i in range(1, BATCH_SIZE + 2)]
        batches = batch(subs)
        assert len(batches) >= 2

    def test_no_batch_exceeds_batch_size(self):
        subs = [_sub(i, "你好") for i in range(1, BATCH_SIZE * 3)]
        for b in batch(subs):
            assert len(b) <= BATCH_SIZE

    def test_all_subtitles_preserved(self):
        subs = [_sub(i, "内容") for i in range(1, 20)]
        batches = batch(subs)
        total = sum(len(b) for b in batches)
        assert total == len(subs)

    def test_splits_on_char_limit(self):
        # Each sub is ~100 chars; BATCH_CHARS=4000 → ~40 per batch
        subs = [_sub(i, "你" * 100) for i in range(1, 60)]
        batches = batch(subs)
        assert len(batches) > 1

    def test_empty_list_returns_empty(self):
        assert batch([]) == []

    def test_single_sub_in_one_batch(self):
        subs = [_sub(1, "你好")]
        assert batch(subs) == [subs]


# ── parse_json_response ───────────────────────────────────────────────────────

class TestParseJsonResponse:
    def test_parses_valid_json_array(self):
        result = parse_json_response('["xin chào", "tạm biệt"]', 2)
        assert result == ["xin chào", "tạm biệt"]

    def test_pads_short_array(self):
        result = parse_json_response('["xin chào"]', 3)
        assert len(result) == 3
        assert result[1] == ""
        assert result[2] == ""

    def test_truncates_long_array(self):
        result = parse_json_response('["a", "b", "c", "d"]', 2)
        assert result == ["a", "b"]

    def test_strips_markdown_fence(self):
        text = '```json\n["xin chào"]\n```'
        result = parse_json_response(text, 1)
        assert result == ["xin chào"]

    def test_fallback_line_split(self):
        text = "xin chào\ntạm biệt"
        result = parse_json_response(text, 2)
        assert result == ["xin chào", "tạm biệt"]

    def test_fallback_pads_if_short(self):
        result = parse_json_response("only one line", 3)
        assert len(result) == 3

    def test_exact_count(self):
        result = parse_json_response('["a", "b"]', 2)
        assert len(result) == 2

    def test_non_string_items_coerced(self):
        result = parse_json_response('[1, 2, 3]', 3)
        assert result == ["1", "2", "3"]


# ── _build_scene_note ─────────────────────────────────────────────────────────

class TestBuildSceneNote:
    def test_returns_empty_when_no_cuts(self):
        subs = [_sub(1, "你好", start=0.0, end=5.0)]
        assert _build_scene_note(subs, None) == ""
        assert _build_scene_note(subs, []) == ""

    def test_returns_empty_when_no_cuts_in_range(self):
        subs = [_sub(1, "你好", start=0.0, end=5.0)]
        assert _build_scene_note(subs, [10.0, 20.0]) == ""

    def test_includes_cut_timestamp(self):
        subs = [_sub(1, "你好", start=0.0, end=10.0)]
        note = _build_scene_note(subs, [5.0])
        assert "5.00s" in note

    def test_includes_multiple_cuts(self):
        subs = [_sub(1, "你好", start=0.0, end=30.0)]
        note = _build_scene_note(subs, [5.0, 15.0, 25.0])
        assert "5.00s" in note
        assert "15.00s" in note
        assert "25.00s" in note

    def test_boundary_cut_included(self):
        subs = [_sub(1, "你好", start=0.0, end=10.0)]
        # Cut at batch_start boundary
        note = _build_scene_note(subs, [0.0])
        assert "0.00s" in note


# ── build_prompt ──────────────────────────────────────────────────────────────

class TestBuildPrompt:
    def test_includes_system_prompt(self):
        subs = [_sub(1, "你好")]
        prompt = build_prompt(subs, [], "SYSTEM")
        assert "SYSTEM" in prompt

    def test_includes_subtitle_content(self):
        subs = [_sub(1, "你好世界")]
        prompt = build_prompt(subs, [], "SYS")
        assert "你好世界" in prompt

    def test_includes_context_section(self):
        subs = [_sub(2, "再见")]
        context = [_sub(1, "你好")]
        prompt = build_prompt(subs, context, "SYS")
        assert "你好" in prompt
        assert "KHÔNG dịch" in prompt

    def test_no_context_section_when_empty(self):
        subs = [_sub(1, "你好")]
        prompt = build_prompt(subs, [], "SYS")
        assert "KHÔNG dịch" not in prompt

    def test_includes_json_instruction(self):
        subs = [_sub(1, "你好")]
        prompt = build_prompt(subs, [], "SYS")
        assert "JSON" in prompt

    def test_appends_scene_note_when_cuts_in_range(self):
        subs = [_sub(1, "你好", start=0.0, end=10.0)]
        prompt = build_prompt(subs, [], "SYS", cuts=[5.0])
        assert "5.00s" in prompt

    def test_no_scene_note_when_cuts_is_none(self):
        subs = [_sub(1, "你好", start=0.0, end=10.0)]
        prompt = build_prompt(subs, [], "SYS", cuts=None)
        assert "cắt cảnh" not in prompt


# ── translate (main) ──────────────────────────────────────────────────────────

class TestTranslate:
    def _write_cn_srt(self, output_dir: Path):
        subs = [
            srt.Subtitle(1, timedelta(seconds=0), timedelta(seconds=2), "你好世界"),
            srt.Subtitle(2, timedelta(seconds=2), timedelta(seconds=4), "再见朋友"),
        ]
        (output_dir / "captions_cn.srt").write_text(srt.compose(subs), encoding="utf-8")

    def test_skips_when_sentinel_exists(self, tmp_path):
        self._write_cn_srt(tmp_path)
        (tmp_path / ".step4.done").touch()
        (tmp_path / "captions_vn.srt").write_text("", encoding="utf-8")

        with patch("pipeline.step4_translate.providers.gemini.run") as mock_run:
            result = translate(tmp_path)

        mock_run.assert_not_called()

    def test_raises_if_no_cn_srt(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            translate(tmp_path)

    def test_creates_sentinel(self, tmp_path):
        self._write_cn_srt(tmp_path)

        with patch("pipeline.step4_translate.providers.gemini.run", return_value=["Xin chào", "Tạm biệt"]):
            translate(tmp_path)

        assert (tmp_path / ".step4.done").exists()

    def test_writes_vn_srt(self, tmp_path):
        self._write_cn_srt(tmp_path)

        with patch("pipeline.step4_translate.providers.gemini.run", return_value=["Xin chào", "Tạm biệt"]):
            result = translate(tmp_path)

        assert result.name == "captions_vn.srt"
        assert result.exists()

    def test_loads_cuts_from_scenes_json(self, tmp_path):
        self._write_cn_srt(tmp_path)
        scenes_data = {"cuts": [1.5, 3.0], "scenes": [], "detector": "ffmpeg_scdet", "video_duration": 4.0}
        (tmp_path / "scenes.json").write_text(json.dumps(scenes_data), encoding="utf-8")

        with patch("pipeline.step4_translate.providers.gemini.run", return_value=["A", "B"]) as mock_run:
            translate(tmp_path)

        # run() should have been called — scene info was injected into system_prompt
        mock_run.assert_called_once()

    def test_uses_title_in_system_prompt(self, tmp_path):
        self._write_cn_srt(tmp_path)
        metadata = {"title": "Amazing Video Title", "id": "BV1xx"}
        (tmp_path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

        captured_prompts = []

        def capture_run(subs, system_prompt):
            captured_prompts.append(system_prompt)
            return ["A"] * len(subs)

        with patch("pipeline.step4_translate.providers.gemini.run", side_effect=capture_run):
            translate(tmp_path)

        assert any("Amazing Video Title" in p for p in captured_prompts)

    def test_uses_claude_provider(self, tmp_path):
        self._write_cn_srt(tmp_path)

        with patch("pipeline.step4_translate.providers.claude.run", return_value=["A", "B"]) as mock_run:
            translate(tmp_path, provider="claude")

        mock_run.assert_called_once()
