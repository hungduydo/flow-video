"""Unit tests for pipeline.step3_transcribe.main"""

from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import srt

from pipeline.step3_transcribe.main import (
    _clean_subtitles,
    _seconds_to_timedelta,
    transcribe,
    MUSIC_PROB_THRESHOLD,
    DEEPGRAM_CONFIDENCE_THRESHOLD,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sub(idx, content, start=0.0, end=1.0):
    return srt.Subtitle(
        index=idx,
        start=timedelta(seconds=start),
        end=timedelta(seconds=end),
        content=content,
    )


# ── _seconds_to_timedelta ─────────────────────────────────────────────────────

class TestSecondsToTimedelta:
    def test_integer_seconds(self):
        assert _seconds_to_timedelta(60.0) == timedelta(seconds=60)

    def test_fractional_seconds(self):
        td = _seconds_to_timedelta(1.5)
        assert td.total_seconds() == pytest.approx(1.5)

    def test_zero(self):
        assert _seconds_to_timedelta(0.0) == timedelta(0)

    def test_large_value(self):
        assert _seconds_to_timedelta(3600.0) == timedelta(hours=1)


# ── _clean_subtitles ──────────────────────────────────────────────────────────

class TestCleanSubtitles:
    def test_keeps_subtitles_with_two_or_more_cjk(self):
        subs = [_sub(1, "你好世界")]
        result = _clean_subtitles(subs)
        assert len(result) == 1

    def test_drops_single_cjk_character(self):
        subs = [_sub(1, "研")]
        result = _clean_subtitles(subs)
        assert len(result) == 0

    def test_drops_punctuation_only(self):
        subs = [_sub(1, "。"), _sub(2, "！？")]
        result = _clean_subtitles(subs)
        assert len(result) == 0

    def test_drops_empty_content(self):
        subs = [_sub(1, "")]
        result = _clean_subtitles(subs)
        assert len(result) == 0

    def test_reindexes_remaining(self):
        subs = [
            _sub(1, "研"),          # single CJK → dropped
            _sub(2, "你好世界"),    # kept
            _sub(3, "。"),          # punct → dropped
            _sub(4, "测试内容"),    # kept
        ]
        result = _clean_subtitles(subs)
        assert [s.index for s in result] == [1, 2]

    def test_keeps_mixed_cjk_and_ascii(self):
        subs = [_sub(1, "Hello 你好")]
        result = _clean_subtitles(subs)
        assert len(result) == 1

    def test_empty_list(self):
        assert _clean_subtitles([]) == []

    def test_all_valid_kept(self):
        subs = [_sub(i, f"内容{i}号") for i in range(1, 6)]
        result = _clean_subtitles(subs)
        assert len(result) == 5

    def test_two_cjk_boundary(self):
        # Exactly 2 CJK chars — should be kept
        subs = [_sub(1, "你好")]
        result = _clean_subtitles(subs)
        assert len(result) == 1

    def test_one_cjk_with_punctuation_dropped(self):
        subs = [_sub(1, "研。")]
        result = _clean_subtitles(subs)
        assert len(result) == 0


# ── Sentinel / transcribe ────────────────────────────────────────────────────

class TestTranscribeSentinel:
    def test_skips_when_sentinel_exists(self, tmp_path):
        (tmp_path / ".step3.done").touch()
        (tmp_path / "captions_cn.srt").write_text("", encoding="utf-8")
        (tmp_path / "audio.wav").touch()

        with patch("faster_whisper.WhisperModel") as mock_wm:
            result = transcribe(tmp_path)

        mock_wm.assert_not_called()
        assert result == tmp_path / "captions_cn.srt"

    def test_raises_if_no_audio(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            transcribe(tmp_path)

    def test_prefers_vocals_over_audio_wav(self, tmp_path):
        (tmp_path / "vocals.wav").touch()
        (tmp_path / "audio.wav").touch()

        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "你好世界测试"
        mock_segment.start = 0.0
        mock_segment.end = 1.0
        mock_segment.no_speech_prob = 0.0
        mock_model.transcribe.return_value = ([mock_segment], MagicMock(language="zh", language_probability=0.99))

        with patch("faster_whisper.WhisperModel", return_value=mock_model):
            transcribe(tmp_path)

        call_args = mock_model.transcribe.call_args[0]
        assert "vocals.wav" in call_args[0]

    def test_sentinel_created_after_transcription(self, tmp_path):
        (tmp_path / "audio.wav").touch()

        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "你好世界"
        mock_segment.start = 0.0
        mock_segment.end = 1.0
        mock_segment.no_speech_prob = 0.0
        mock_model.transcribe.return_value = ([mock_segment], MagicMock(language="zh", language_probability=0.99))

        with patch("faster_whisper.WhisperModel", return_value=mock_model):
            transcribe(tmp_path)

        assert (tmp_path / ".step3.done").exists()


class TestTranscribeWhisper:
    def test_skips_high_no_speech_prob(self, tmp_path):
        (tmp_path / "audio.wav").touch()

        mock_model = MagicMock()
        seg_music = MagicMock(text="…", start=0.0, end=1.0,
                               no_speech_prob=MUSIC_PROB_THRESHOLD + 0.1)
        seg_speech = MagicMock(text="你好世界", start=1.0, end=2.0,
                                no_speech_prob=0.0)
        mock_model.transcribe.return_value = (
            [seg_music, seg_speech],
            MagicMock(language="zh", language_probability=0.99),
        )

        with patch("faster_whisper.WhisperModel", return_value=mock_model):
            transcribe(tmp_path)

        content = (tmp_path / "captions_cn.srt").read_text(encoding="utf-8")
        # Only the speech segment should appear
        assert "你好世界" in content

    def test_writes_srt_file(self, tmp_path):
        (tmp_path / "audio.wav").touch()

        mock_model = MagicMock()
        seg = MagicMock(text="测试内容", start=0.0, end=2.0, no_speech_prob=0.0)
        mock_model.transcribe.return_value = (
            [seg], MagicMock(language="zh", language_probability=0.99)
        )

        with patch("faster_whisper.WhisperModel", return_value=mock_model):
            result = transcribe(tmp_path)

        assert result.exists()
        assert result.name == "captions_cn.srt"

    def test_uses_deepgram_provider(self, tmp_path):
        (tmp_path / "audio.wav").touch()
        (tmp_path / ".step3.done").touch()
        (tmp_path / "captions_cn.srt").write_text("", encoding="utf-8")

        with patch("pipeline.step3_transcribe.main._transcribe_deepgram") as mock_dg:
            mock_dg.return_value = tmp_path / "captions_cn.srt"
            # Remove sentinel so it runs
            (tmp_path / ".step3.done").unlink()

            with patch.dict("os.environ", {"DEEPGRAM_API_KEY": "test_key"}):
                with patch("pipeline.step3_transcribe.main._transcribe_deepgram") as mock_fn:
                    mock_fn.return_value = tmp_path / "captions_cn.srt"
                    transcribe(tmp_path, provider="deepgram")
                    mock_fn.assert_called_once()


# ── Constants ────────────────────────────────────────────────────────────────

class TestConstants:
    def test_music_prob_threshold_is_reasonable(self):
        assert 0.0 < MUSIC_PROB_THRESHOLD < 1.0

    def test_deepgram_confidence_threshold_is_reasonable(self):
        assert 0.0 < DEEPGRAM_CONFIDENCE_THRESHOLD < 1.0
