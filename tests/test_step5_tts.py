"""Unit tests for pipeline.step5_tts.main"""

import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
import srt

from pipeline.step5_tts.main import (
    _has_cut_in_range,
    _earliest_cut_in_range,
    _get_audio_duration,
    _is_speakable,
    generate_tts,
    MIN_DURATION,
)


# ── _has_cut_in_range ─────────────────────────────────────────────────────────

class TestHasCutInRange:
    def test_cut_inside_range(self):
        assert _has_cut_in_range({5.0, 10.0}, 3.0, 7.0) is True

    def test_cut_at_start_boundary(self):
        assert _has_cut_in_range({3.0}, 3.0, 7.0) is True

    def test_cut_at_end_boundary(self):
        assert _has_cut_in_range({7.0}, 3.0, 7.0) is True

    def test_cut_outside_range(self):
        assert _has_cut_in_range({1.0, 9.0}, 3.0, 7.0) is False

    def test_empty_cuts(self):
        assert _has_cut_in_range(set(), 0.0, 10.0) is False

    def test_multiple_cuts_one_in_range(self):
        assert _has_cut_in_range({1.0, 5.0, 15.0}, 4.0, 6.0) is True


# ── _earliest_cut_in_range ────────────────────────────────────────────────────

class TestEarliestCutInRange:
    def test_returns_earliest_cut(self):
        result = _earliest_cut_in_range({5.0, 8.0, 3.0}, 1.0, 10.0)
        assert result == 3.0

    def test_returns_none_when_empty(self):
        assert _earliest_cut_in_range(set(), 0.0, 10.0) is None

    def test_exclusive_at_start(self):
        # Cut exactly at start is excluded
        assert _earliest_cut_in_range({3.0}, 3.0, 7.0) is None

    def test_exclusive_at_end(self):
        # Cut exactly at end is excluded
        assert _earliest_cut_in_range({7.0}, 3.0, 7.0) is None

    def test_returns_none_when_no_cut_in_range(self):
        assert _earliest_cut_in_range({1.0, 15.0}, 3.0, 7.0) is None

    def test_single_cut_strictly_inside(self):
        result = _earliest_cut_in_range({5.0}, 3.0, 7.0)
        assert result == 5.0


# ── _is_speakable ─────────────────────────────────────────────────────────────

class TestIsSpeakable:
    def test_latin_text_is_speakable(self):
        assert _is_speakable("Hello world") is True

    def test_vietnamese_text_is_speakable(self):
        assert _is_speakable("Xin chào") is True

    def test_digit_is_speakable(self):
        assert _is_speakable("100") is True

    def test_punctuation_only_not_speakable(self):
        assert _is_speakable("...") is False
        assert _is_speakable("???") is False
        assert _is_speakable("!!!") is False

    def test_empty_string_not_speakable(self):
        assert _is_speakable("") is False

    def test_whitespace_only_not_speakable(self):
        assert _is_speakable("   ") is False


# ── _get_audio_duration ───────────────────────────────────────────────────────

class TestGetAudioDuration:
    def test_returns_float(self, tmp_path):
        audio = tmp_path / "test.mp3"
        audio.touch()
        mock_result = MagicMock(returncode=0, stdout="5.25\n")

        with patch("subprocess.run", return_value=mock_result):
            dur = _get_audio_duration(audio)

        assert dur == pytest.approx(5.25)

    def test_returns_zero_on_failure(self, tmp_path):
        audio = tmp_path / "test.mp3"
        audio.touch()
        mock_result = MagicMock(returncode=1, stdout="")

        with patch("subprocess.run", return_value=mock_result):
            dur = _get_audio_duration(audio)

        assert dur == 0.0


# ── generate_tts (sentinel + integration) ────────────────────────────────────

def _write_vn_srt(output_dir: Path, subs=None):
    if subs is None:
        subs = [
            srt.Subtitle(1, timedelta(seconds=0), timedelta(seconds=2), "Xin chào"),
            srt.Subtitle(2, timedelta(seconds=2), timedelta(seconds=4), "Tạm biệt"),
        ]
    (output_dir / "captions_vn.srt").write_text(srt.compose(subs), encoding="utf-8")


def _fake_ffmpeg_factory():
    """Returns a subprocess.run side_effect that creates the output file and returns success."""
    def fake_ffmpeg(cmd, **kwargs):
        # The output is always the last argument for our ffmpeg calls
        out = cmd[-1]
        Path(out).touch()
        return MagicMock(returncode=0, stderr="", stdout="3.0\n")
    return fake_ffmpeg


def _make_mock_provider(tmp_path):
    """Creates a mock TTS provider whose synth() creates the output file."""
    mock_provider = MagicMock()
    mock_provider.audio_format = {"sample_rate": 24000, "channels": "mono"}

    def synth_creates_file(text, path):
        Path(path).touch()

    mock_provider.synth.side_effect = synth_creates_file
    return mock_provider


class TestGenerateTtsSentinel:
    def test_skips_when_sentinel_exists(self, tmp_path):
        _write_vn_srt(tmp_path)
        (tmp_path / ".step5.done").touch()
        (tmp_path / "audio_vn_full.mp3").touch()

        with patch("pipeline.step5_tts.main.get_provider") as mock_gp:
            result = generate_tts(tmp_path)

        mock_gp.assert_not_called()
        assert result == tmp_path / "audio_vn_full.mp3"

    def test_raises_if_no_srt(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            generate_tts(tmp_path)

    def test_sentinel_created_on_success(self, tmp_path):
        _write_vn_srt(tmp_path)
        (tmp_path / "audio.wav").touch()

        mock_provider = _make_mock_provider(tmp_path)

        with patch("pipeline.step5_tts.main.get_provider", return_value=mock_provider):
            with patch("subprocess.run", side_effect=_fake_ffmpeg_factory()):
                generate_tts(tmp_path)

        assert (tmp_path / ".step5.done").exists()


class TestGenerateTtsSceneAware:
    def test_loads_scenes_json_cuts(self, tmp_path):
        _write_vn_srt(tmp_path)
        scenes = {"cuts": [1.5], "scenes": [], "detector": "ffmpeg_scdet", "video_duration": 4.0}
        (tmp_path / "scenes.json").write_text(json.dumps(scenes), encoding="utf-8")
        (tmp_path / "audio.wav").touch()

        mock_provider = _make_mock_provider(tmp_path)
        recorded_cuts = []
        original_has_cut = _has_cut_in_range

        def capturing_has_cut(cuts, start, end):
            recorded_cuts.extend(cuts)
            return original_has_cut(cuts, start, end)

        with patch("pipeline.step5_tts.main.get_provider", return_value=mock_provider):
            with patch("subprocess.run", side_effect=_fake_ffmpeg_factory()):
                with patch("pipeline.step5_tts.main._has_cut_in_range", side_effect=capturing_has_cut):
                    generate_tts(tmp_path)

        assert 1.5 in recorded_cuts

    def test_no_error_when_scenes_json_absent(self, tmp_path):
        _write_vn_srt(tmp_path)
        (tmp_path / "audio.wav").touch()

        mock_provider = _make_mock_provider(tmp_path)

        # Should not raise even with no scenes.json
        with patch("pipeline.step5_tts.main.get_provider", return_value=mock_provider):
            with patch("subprocess.run", side_effect=_fake_ffmpeg_factory()):
                generate_tts(tmp_path)


# ── MIN_DURATION constant ─────────────────────────────────────────────────────

class TestConstants:
    def test_min_duration_positive(self):
        assert MIN_DURATION > 0

    def test_min_duration_is_subsecond(self):
        assert MIN_DURATION < 1.0
