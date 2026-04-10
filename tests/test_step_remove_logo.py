"""Unit tests for pipeline.step_remove_logo.main"""

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
import numpy as np

# cv2 is an optional heavy dependency — stub it out at import time
# so the test module can be collected on machines without OpenCV installed.
_cv2_stub = ModuleType("cv2")
_cv2_stub.VideoCapture = MagicMock()
_cv2_stub.cvtColor = MagicMock(return_value=np.zeros((100, 100), dtype=np.float32))
_cv2_stub.GaussianBlur = MagicMock(return_value=np.zeros((100, 100), dtype=np.float32))
_cv2_stub.bitwise_or = MagicMock(return_value=np.zeros((100, 100), dtype=np.uint8))
_cv2_stub.dilate = MagicMock(return_value=np.zeros((100, 100), dtype=np.uint8))
_cv2_stub.imencode = MagicMock(return_value=(True, np.array([0], dtype=np.uint8)))
_cv2_stub.inpaint = MagicMock(return_value=np.zeros((100, 100, 3), dtype=np.uint8))
_cv2_stub.COLOR_BGR2GRAY = 6
_cv2_stub.CAP_PROP_FRAME_COUNT = 7
_cv2_stub.CAP_PROP_FRAME_WIDTH = 3
_cv2_stub.CAP_PROP_FRAME_HEIGHT = 4
_cv2_stub.CAP_PROP_FPS = 5
_cv2_stub.CAP_PROP_POS_FRAMES = 1
_cv2_stub.INPAINT_TELEA = 1
_cv2_stub.IMWRITE_JPEG_QUALITY = 1
sys.modules.setdefault("cv2", _cv2_stub)

from pipeline.step_remove_logo.main import (  # noqa: E402
    _corner_rects,
    _build_removal_filter,
    _bbox_for_corner,
    remove_logo,
)


# ── _corner_rects ─────────────────────────────────────────────────────────────

class TestCornerRects:
    def test_returns_four_corners(self):
        rects = _corner_rects(1920, 1080)
        assert set(rects.keys()) == {"top_left", "top_right", "bottom_left", "bottom_right"}

    def test_all_rects_have_four_values(self):
        rects = _corner_rects(1920, 1080)
        for v in rects.values():
            assert len(v) == 4

    def test_top_left_starts_at_origin(self):
        rects = _corner_rects(1920, 1080)
        x, y, w, h = rects["top_left"]
        assert x == 0
        assert y == 0

    def test_bottom_right_starts_at_correct_position(self):
        rects = _corner_rects(1920, 1080)
        x, y, w, h = rects["bottom_right"]
        assert x + w == 1920 or x > 0
        assert y + h == 1080 or y > 0

    def test_rects_are_positive_size(self):
        rects = _corner_rects(1920, 1080)
        for _, (x, y, w, h) in rects.items():
            assert w > 0
            assert h > 0

    def test_rects_within_frame(self):
        width, height = 1280, 720
        rects = _corner_rects(width, height)
        for _, (x, y, w, h) in rects.items():
            assert x >= 0
            assert y >= 0
            assert x + w <= width
            assert y + h <= height

    def test_scales_with_frame_dimensions(self):
        rects_hd = _corner_rects(1920, 1080)
        rects_4k = _corner_rects(3840, 2160)
        _, _, w_hd, h_hd = rects_hd["top_left"]
        _, _, w_4k, h_4k = rects_4k["top_left"]
        assert w_4k > w_hd
        assert h_4k > h_hd


# ── _build_removal_filter ─────────────────────────────────────────────────────

class TestBuildRemovalFilter:
    def test_returns_vf_flag(self):
        regions = [("top_left", 0, 0, 200, 100)]
        flag, _, _ = _build_removal_filter(regions, 1920, 1080)
        assert flag == "-vf"

    def test_filter_contains_delogo(self):
        regions = [("top_left", 0, 0, 200, 100)]
        _, filter_str, _ = _build_removal_filter(regions, 1920, 1080)
        assert "delogo" in filter_str

    def test_multiple_regions_chained(self):
        regions = [
            ("top_left", 0, 0, 200, 100),
            ("bottom_right", 1700, 950, 200, 100),
        ]
        _, filter_str, _ = _build_removal_filter(regions, 1920, 1080)
        assert filter_str.count("delogo") == 2

    def test_empty_extra_args(self):
        regions = [("top_left", 0, 0, 200, 100)]
        _, _, extra = _build_removal_filter(regions, 1920, 1080)
        assert extra == []

    def test_delogo_params_include_coordinates(self):
        regions = [("top_left", 50, 30, 200, 100)]
        _, filter_str, _ = _build_removal_filter(regions, 1920, 1080)
        assert "x=" in filter_str
        assert "y=" in filter_str
        assert "w=" in filter_str
        assert "h=" in filter_str


# ── remove_logo public API ────────────────────────────────────────────────────

class TestRemoveLogoApi:
    def test_raises_on_invalid_quality(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()
        with pytest.raises(ValueError, match="quality"):
            remove_logo(video, quality="ultra")

    def test_raises_on_invalid_provider(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()
        with pytest.raises(ValueError, match="provider"):
            remove_logo(video, provider="magic")

    def test_default_output_path(self, tmp_path):
        video = tmp_path / "myvideo.mp4"
        video.touch()

        with patch("pipeline.step_remove_logo.main.detect_watermark_regions", return_value=[]):
            import shutil
            with patch("shutil.copy2") as mock_copy:
                result = remove_logo(video)

        expected = tmp_path / "myvideo_clean.mp4"
        assert result == expected

    def test_copies_when_no_watermark(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()
        out = tmp_path / "out.mp4"

        with patch("pipeline.step_remove_logo.main.detect_watermark_regions", return_value=[]):
            with patch("shutil.copy2") as mock_copy:
                remove_logo(video, out)

        mock_copy.assert_called_once_with(video, out)

    def test_calls_remove_fast_for_fast_quality(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()
        out = tmp_path / "out.mp4"
        regions = [("top_left", 0, 0, 200, 100)]

        with patch("pipeline.step_remove_logo.main.detect_watermark_regions", return_value=regions):
            with patch("pipeline.step_remove_logo.main._remove_fast") as mock_fast:
                mock_fast.return_value = None
                out.touch()  # simulate output created
                remove_logo(video, out, quality="fast")

        mock_fast.assert_called_once()

    def test_calls_remove_high_for_high_quality(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()
        out = tmp_path / "out.mp4"
        regions = [("top_left", 0, 0, 200, 100)]

        with patch("pipeline.step_remove_logo.main.detect_watermark_regions", return_value=regions):
            with patch("pipeline.step_remove_logo.main._remove_high") as mock_high:
                mock_high.return_value = None
                out.touch()
                remove_logo(video, out, quality="high")

        mock_high.assert_called_once()

    def test_accepts_string_path(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()

        with patch("pipeline.step_remove_logo.main.detect_watermark_regions", return_value=[]):
            with patch("shutil.copy2"):
                result = remove_logo(str(video))

        assert isinstance(result, Path)


# ── _bbox_for_corner ─────────────────────────────────────────────────────────

class TestBboxForCorner:
    def _make_arrays(self, x_vals, y_vals):
        import numpy as np
        return np.array(x_vals), np.array(y_vals)

    def test_top_left_x_anchored_to_zero(self):
        import numpy as np
        xs, ys = np.array([10, 50]), np.array([5, 30])
        x, y, w, h = _bbox_for_corner("top_left", xs, ys, 0, 0, 300, 100, 1920, 1080)
        assert x == 0

    def test_top_left_y_anchored_to_zero(self):
        import numpy as np
        xs, ys = np.array([10, 50]), np.array([5, 30])
        x, y, w, h = _bbox_for_corner("top_left", xs, ys, 0, 0, 300, 100, 1920, 1080)
        assert y == 0

    def test_result_within_frame(self):
        import numpy as np
        xs, ys = np.array([10, 50]), np.array([5, 30])
        x, y, w, h = _bbox_for_corner("top_left", xs, ys, 0, 0, 300, 100, 1920, 1080)
        assert x >= 0
        assert y >= 0
        assert x + w <= 1920
        assert y + h <= 1080

    def test_minimum_size_enforced(self):
        import numpy as np
        # Very small mask should be expanded to minimum size
        xs, ys = np.array([5, 6]), np.array([5, 6])
        x, y, w, h = _bbox_for_corner("top_left", xs, ys, 0, 0, 300, 100, 1920, 1080)
        min_w = int(1920 * 0.10)
        min_h = int(1080 * 0.07)
        assert w >= min_w
        assert h >= min_h
