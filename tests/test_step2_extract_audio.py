"""Unit tests for pipeline.step2_extract_audio.main"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.step2_extract_audio.main import extract_audio


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_video(output_dir: Path) -> Path:
    p = output_dir / "original.mp4"
    p.touch()
    return p


def _ok_ffmpeg():
    m = MagicMock()
    m.returncode = 0
    m.stderr = ""
    return m


# ── Sentinel ──────────────────────────────────────────────────────────────────

class TestExtractAudioSentinel:
    def test_skips_when_sentinel_exists(self, tmp_path):
        _make_video(tmp_path)
        (tmp_path / ".step2.done").touch()
        (tmp_path / "audio.wav").touch()

        with patch("subprocess.run") as mock_run:
            result = extract_audio(tmp_path)

        mock_run.assert_not_called()
        assert result == tmp_path / "audio.wav"

    def test_sentinel_created_after_extraction(self, tmp_path):
        _make_video(tmp_path)

        with patch("subprocess.run", return_value=_ok_ffmpeg()):
            extract_audio(tmp_path)

        assert (tmp_path / ".step2.done").exists()

    def test_returns_audio_wav_path(self, tmp_path):
        _make_video(tmp_path)

        with patch("subprocess.run", return_value=_ok_ffmpeg()):
            result = extract_audio(tmp_path)

        assert result == tmp_path / "audio.wav"


# ── Error handling ─────────────────────────────────────────────────────────────

class TestExtractAudioErrors:
    def test_raises_if_no_video(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            extract_audio(tmp_path)

    def test_raises_on_ffmpeg_failure(self, tmp_path):
        _make_video(tmp_path)
        fail_result = MagicMock(returncode=1, stderr="ffmpeg error msg")

        with patch("subprocess.run", return_value=fail_result):
            with pytest.raises(RuntimeError, match="ffmpeg audio extraction failed"):
                extract_audio(tmp_path)

    def test_sentinel_not_created_on_failure(self, tmp_path):
        _make_video(tmp_path)
        fail_result = MagicMock(returncode=1, stderr="error")

        with patch("subprocess.run", return_value=fail_result):
            with pytest.raises(RuntimeError):
                extract_audio(tmp_path)

        assert not (tmp_path / ".step2.done").exists()


# ── ffmpeg invocation ─────────────────────────────────────────────────────────

class TestExtractAudioFfmpeg:
    def test_calls_ffmpeg(self, tmp_path):
        _make_video(tmp_path)

        with patch("subprocess.run", return_value=_ok_ffmpeg()) as mock_run:
            extract_audio(tmp_path)

        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ffmpeg"

    def test_sets_16khz_sample_rate(self, tmp_path):
        _make_video(tmp_path)

        with patch("subprocess.run", return_value=_ok_ffmpeg()) as mock_run:
            extract_audio(tmp_path)

        cmd = mock_run.call_args[0][0]
        assert "-ar" in cmd
        assert "16000" in cmd

    def test_sets_mono_channel(self, tmp_path):
        _make_video(tmp_path)

        with patch("subprocess.run", return_value=_ok_ffmpeg()) as mock_run:
            extract_audio(tmp_path)

        cmd = mock_run.call_args[0][0]
        assert "-ac" in cmd
        assert "1" in cmd

    def test_uses_pcm_s16le_codec(self, tmp_path):
        _make_video(tmp_path)

        with patch("subprocess.run", return_value=_ok_ffmpeg()) as mock_run:
            extract_audio(tmp_path)

        cmd = mock_run.call_args[0][0]
        assert "pcm_s16le" in cmd

    def test_output_is_audio_wav(self, tmp_path):
        _make_video(tmp_path)

        with patch("subprocess.run", return_value=_ok_ffmpeg()) as mock_run:
            extract_audio(tmp_path)

        cmd = mock_run.call_args[0][0]
        assert str(tmp_path / "audio.wav") in cmd
