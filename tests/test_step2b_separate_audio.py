"""Unit tests for pipeline.step2b_separate_audio.main"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.step2b_separate_audio.main import separate_audio


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_audio(output_dir: Path) -> Path:
    p = output_dir / "audio.wav"
    p.touch()
    return p


def _ok_subprocess():
    m = MagicMock()
    m.returncode = 0
    m.stderr = ""
    return m


# ── Sentinel ──────────────────────────────────────────────────────────────────

class TestSeparateAudioSentinel:
    def test_skips_when_sentinel_exists(self, tmp_path):
        _make_audio(tmp_path)
        (tmp_path / ".step2b.done").touch()
        (tmp_path / "vocals.wav").touch()
        (tmp_path / "accompaniment.mp3").touch()

        with patch("subprocess.run") as mock_run:
            vocals, acc = separate_audio(tmp_path)

        mock_run.assert_not_called()
        assert vocals == tmp_path / "vocals.wav"
        assert acc == tmp_path / "accompaniment.mp3"

    def test_sentinel_created_on_success(self, tmp_path):
        _make_audio(tmp_path)

        # Simulate demucs creating output files
        demucs_dir = tmp_path / "demucs_tmp" / "htdemucs" / "audio"
        demucs_dir.mkdir(parents=True)
        (demucs_dir / "vocals.mp3").touch()
        (demucs_dir / "no_vocals.mp3").touch()

        with patch("subprocess.run", return_value=_ok_subprocess()):
            separate_audio(tmp_path)

        assert (tmp_path / ".step2b.done").exists()

    def test_returns_tuple_of_paths(self, tmp_path):
        _make_audio(tmp_path)

        demucs_dir = tmp_path / "demucs_tmp" / "htdemucs" / "audio"
        demucs_dir.mkdir(parents=True)
        (demucs_dir / "vocals.mp3").touch()
        (demucs_dir / "no_vocals.mp3").touch()

        with patch("subprocess.run", return_value=_ok_subprocess()):
            result = separate_audio(tmp_path)

        assert isinstance(result, tuple)
        assert len(result) == 2


# ── Error handling ─────────────────────────────────────────────────────────────

class TestSeparateAudioErrors:
    def test_raises_if_no_audio_wav(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            separate_audio(tmp_path)

    def test_raises_on_demucs_failure(self, tmp_path):
        _make_audio(tmp_path)
        fail_result = MagicMock(returncode=1, stderr="demucs error")

        with patch("subprocess.run", return_value=fail_result):
            with pytest.raises(RuntimeError, match="demucs failed"):
                separate_audio(tmp_path)

    def test_raises_if_demucs_output_missing(self, tmp_path):
        _make_audio(tmp_path)
        # demucs "succeeds" but doesn't produce output files
        with patch("subprocess.run", return_value=_ok_subprocess()):
            with pytest.raises(FileNotFoundError):
                separate_audio(tmp_path)


# ── Output files ──────────────────────────────────────────────────────────────

class TestSeparateAudioOutputs:
    def _setup_demucs(self, tmp_path):
        _make_audio(tmp_path)
        demucs_dir = tmp_path / "demucs_tmp" / "htdemucs" / "audio"
        demucs_dir.mkdir(parents=True)
        (demucs_dir / "vocals.mp3").write_bytes(b"\x00" * 100)
        (demucs_dir / "no_vocals.mp3").write_bytes(b"\x00" * 100)
        return demucs_dir

    def test_outputs_vocals_wav(self, tmp_path):
        self._setup_demucs(tmp_path)

        with patch("subprocess.run", return_value=_ok_subprocess()):
            vocals, _ = separate_audio(tmp_path)

        assert vocals.name == "vocals.wav"

    def test_outputs_accompaniment_mp3(self, tmp_path):
        self._setup_demucs(tmp_path)

        with patch("subprocess.run", return_value=_ok_subprocess()):
            _, acc = separate_audio(tmp_path)

        assert acc.name == "accompaniment.mp3"

    def test_cleans_up_temp_dir(self, tmp_path):
        self._setup_demucs(tmp_path)

        with patch("subprocess.run", return_value=_ok_subprocess()):
            separate_audio(tmp_path)

        assert not (tmp_path / "demucs_tmp").exists()
