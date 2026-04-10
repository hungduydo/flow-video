"""Unit tests for pipeline.step1b_scenes.main"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from pipeline.step1b_scenes.main import (
    _cuts_to_scenes,
    _get_video_duration,
    _detect_with_ffmpeg,
    detect_scenes,
)


# ── _cuts_to_scenes ───────────────────────────────────────────────────────────

class TestCutsToScenes:
    def test_no_cuts_single_scene(self):
        scenes = _cuts_to_scenes([], 60.0)
        assert scenes == [(0.0, 60.0)]

    def test_one_cut_two_scenes(self):
        scenes = _cuts_to_scenes([30.0], 60.0)
        assert scenes == [(0.0, 30.0), (30.0, 60.0)]

    def test_multiple_cuts(self):
        scenes = _cuts_to_scenes([10.0, 25.0, 45.0], 60.0)
        assert scenes == [(0.0, 10.0), (10.0, 25.0), (25.0, 45.0), (45.0, 60.0)]

    def test_cuts_sorted(self):
        # Unsorted input should still produce sorted scenes
        scenes = _cuts_to_scenes([45.0, 10.0, 25.0], 60.0)
        assert scenes[0] == (0.0, 10.0)
        assert scenes[-1] == (45.0, 60.0)

    def test_zero_duration(self):
        # With duration 0.0, no end boundary added
        scenes = _cuts_to_scenes([10.0], 0.0)
        assert len(scenes) == 1
        assert scenes[0] == (0.0, 10.0)

    def test_scene_count_equals_cuts_plus_one(self):
        cuts = [5.0, 15.0, 30.0, 50.0]
        scenes = _cuts_to_scenes(cuts, 60.0)
        assert len(scenes) == len(cuts) + 1

    def test_start_always_zero(self):
        scenes = _cuts_to_scenes([20.0, 40.0], 60.0)
        assert scenes[0][0] == 0.0

    def test_last_scene_ends_at_duration(self):
        scenes = _cuts_to_scenes([20.0], 100.0)
        assert scenes[-1][1] == 100.0

    def test_adjacent_scenes_share_boundary(self):
        scenes = _cuts_to_scenes([10.0, 30.0], 60.0)
        assert scenes[0][1] == scenes[1][0]
        assert scenes[1][1] == scenes[2][0]


# ── _get_video_duration ───────────────────────────────────────────────────────

class TestGetVideoDuration:
    def test_returns_float_from_ffprobe(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "123.456\n"

        with patch("subprocess.run", return_value=mock_result):
            dur = _get_video_duration(video)

        assert dur == pytest.approx(123.456)

    def test_returns_zero_on_ffprobe_failure(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            dur = _get_video_duration(video)

        assert dur == 0.0

    def test_returns_zero_on_empty_output(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "   "

        with patch("subprocess.run", return_value=mock_result):
            dur = _get_video_duration(video)

        assert dur == 0.0

    def test_returns_zero_on_parse_error(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "N/A\n"

        with patch("subprocess.run", return_value=mock_result):
            dur = _get_video_duration(video)

        assert dur == 0.0


# ── _detect_with_ffmpeg ───────────────────────────────────────────────────────

class TestDetectWithFfmpeg:
    def test_parses_scd_time_lines(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()
        stderr = (
            "frame:  100 pts: 3333\n"
            "  lavfi.scd.time:12.500000\n"
            "  lavfi.scd.score:18.3\n"
            "frame:  200 pts: 6666\n"
            "  lavfi.scd.time:25.000000\n"
        )
        mock_result = MagicMock()
        mock_result.stderr = stderr
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            cuts = _detect_with_ffmpeg(video)

        assert cuts == [12.5, 25.0]

    def test_returns_empty_on_no_cuts(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()
        mock_result = MagicMock()
        mock_result.stderr = "nothing useful here\n"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            cuts = _detect_with_ffmpeg(video)

        assert cuts == []

    def test_deduplicates_cuts(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()
        stderr = "  lavfi.scd.time:10.0\n  lavfi.scd.time:10.0\n"
        mock_result = MagicMock()
        mock_result.stderr = stderr

        with patch("subprocess.run", return_value=mock_result):
            cuts = _detect_with_ffmpeg(video)

        assert cuts == [10.0]

    def test_ignores_malformed_scd_lines(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()
        stderr = "  lavfi.scd.time:NOT_A_FLOAT\n  lavfi.scd.time:5.5\n"
        mock_result = MagicMock()
        mock_result.stderr = stderr

        with patch("subprocess.run", return_value=mock_result):
            cuts = _detect_with_ffmpeg(video)

        assert cuts == [5.5]

    def test_returns_sorted_cuts(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()
        stderr = "  lavfi.scd.time:30.0\n  lavfi.scd.time:5.0\n  lavfi.scd.time:15.0\n"
        mock_result = MagicMock()
        mock_result.stderr = stderr

        with patch("subprocess.run", return_value=mock_result):
            cuts = _detect_with_ffmpeg(video)

        assert cuts == sorted(cuts)


# ── detect_scenes ─────────────────────────────────────────────────────────────

class TestDetectScenes:
    def _make_video(self, output_dir: Path, name="original.mp4") -> Path:
        p = output_dir / name
        p.touch()
        return p

    def test_skips_if_sentinel_exists(self, tmp_path):
        self._make_video(tmp_path)
        (tmp_path / ".step1b.done").touch()
        (tmp_path / "scenes.json").write_text('{"cuts":[]}', encoding="utf-8")

        with patch("subprocess.run") as mock_run:
            result = detect_scenes(tmp_path)

        mock_run.assert_not_called()
        assert result == tmp_path / "scenes.json"

    def test_raises_if_no_video_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            detect_scenes(tmp_path)

    def test_skips_final_video(self, tmp_path):
        # final_*.mp4 should not be used as source
        (tmp_path / "final_youtube.mp4").touch()

        with pytest.raises(FileNotFoundError):
            detect_scenes(tmp_path)

    def test_writes_scenes_json(self, tmp_path):
        self._make_video(tmp_path)

        ffprobe_result = MagicMock(returncode=0, stdout="60.0\n")
        ffmpeg_result = MagicMock(
            stderr="  lavfi.scd.time:20.0\n  lavfi.scd.time:40.0\n",
            returncode=0,
        )

        def side_effect(cmd, **kwargs):
            if "ffprobe" in cmd[0]:
                return ffprobe_result
            return ffmpeg_result

        with patch("subprocess.run", side_effect=side_effect):
            result = detect_scenes(tmp_path)

        assert result == tmp_path / "scenes.json"
        data = json.loads(result.read_text(encoding="utf-8"))
        assert "cuts" in data
        assert "scenes" in data
        assert "detector" in data
        assert "video_duration" in data

    def test_creates_sentinel(self, tmp_path):
        self._make_video(tmp_path)

        ffprobe_result = MagicMock(returncode=0, stdout="60.0\n")
        ffmpeg_result = MagicMock(stderr="  lavfi.scd.time:20.0\n", returncode=0)

        def side_effect(cmd, **kwargs):
            if "ffprobe" in cmd[0]:
                return ffprobe_result
            return ffmpeg_result

        with patch("subprocess.run", side_effect=side_effect):
            detect_scenes(tmp_path)

        assert (tmp_path / ".step1b.done").exists()

    def test_cuts_in_scenes_json(self, tmp_path):
        self._make_video(tmp_path)

        ffprobe_result = MagicMock(returncode=0, stdout="60.0\n")
        ffmpeg_result = MagicMock(
            stderr="  lavfi.scd.time:15.0\n  lavfi.scd.time:35.0\n",
            returncode=0,
        )

        def side_effect(cmd, **kwargs):
            if "ffprobe" in cmd[0]:
                return ffprobe_result
            return ffmpeg_result

        with patch("subprocess.run", side_effect=side_effect):
            detect_scenes(tmp_path)

        data = json.loads((tmp_path / "scenes.json").read_text(encoding="utf-8"))
        assert 15.0 in data["cuts"]
        assert 35.0 in data["cuts"]

    def test_falls_back_to_pyscenedetect_when_no_ffmpeg_cuts(self, tmp_path):
        self._make_video(tmp_path)

        ffprobe_result = MagicMock(returncode=0, stdout="60.0\n")
        ffmpeg_result = MagicMock(stderr="no cuts here\n", returncode=0)

        def side_effect(cmd, **kwargs):
            if "ffprobe" in cmd[0]:
                return ffprobe_result
            return ffmpeg_result

        mock_detect = MagicMock(return_value=[])

        with patch("subprocess.run", side_effect=side_effect):
            with patch("pipeline.step1b_scenes.main._detect_with_pyscenedetect", mock_detect):
                detect_scenes(tmp_path)

        mock_detect.assert_called_once()

    def test_detector_label_ffmpeg(self, tmp_path):
        self._make_video(tmp_path)

        ffprobe_result = MagicMock(returncode=0, stdout="60.0\n")
        ffmpeg_result = MagicMock(stderr="  lavfi.scd.time:10.0\n", returncode=0)

        def side_effect(cmd, **kwargs):
            if "ffprobe" in cmd[0]:
                return ffprobe_result
            return ffmpeg_result

        with patch("subprocess.run", side_effect=side_effect):
            detect_scenes(tmp_path)

        data = json.loads((tmp_path / "scenes.json").read_text(encoding="utf-8"))
        assert data["detector"] == "ffmpeg_scdet"

    def test_prefers_mp4_over_mkv(self, tmp_path):
        self._make_video(tmp_path, "original.mp4")
        (tmp_path / "original.mkv").touch()

        ffprobe_result = MagicMock(returncode=0, stdout="60.0\n")
        ffmpeg_result = MagicMock(stderr="  lavfi.scd.time:10.0\n", returncode=0)

        def side_effect(cmd, **kwargs):
            if "ffprobe" in cmd[0]:
                return ffprobe_result
            return ffmpeg_result

        captured = []

        def capturing_run(cmd, **kwargs):
            captured.append(cmd)
            return side_effect(cmd, **kwargs)

        with patch("subprocess.run", side_effect=capturing_run):
            detect_scenes(tmp_path)

        # The ffmpeg call should reference original.mp4
        ffmpeg_calls = [c for c in captured if "ffmpeg" in c[0]]
        assert any("original.mp4" in " ".join(c) for c in ffmpeg_calls)
