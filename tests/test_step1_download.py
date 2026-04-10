"""Unit tests for pipeline.step1_download.main"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from pipeline.step1_download.main import download


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def output_base(tmp_path):
    return tmp_path / "output"


def _mock_info(video_id="BV1xx411"):
    return {
        "id": video_id,
        "title": "Test Video Title",
        "duration": 120,
        "url": "https://www.bilibili.com/video/BV1xx411",
        "uploader": "TestUploader",
        "webpage_url": "https://www.bilibili.com/video/BV1xx411",
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestDownloadSentinel:
    def test_skips_download_when_sentinel_exists(self, output_base):
        info = _mock_info()
        output_dir = output_base / info["id"]
        output_dir.mkdir(parents=True)
        (output_dir / ".step1.done").touch()

        with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.extract_info.return_value = info
            mock_ydl_cls.return_value = ctx

            result = download("https://bilibili.com/video/BV1xx411", output_base)

        assert result == output_dir
        # download() should not be called when sentinel exists
        ctx.download.assert_not_called()

    def test_sentinel_created_after_download(self, output_base):
        info = _mock_info()

        with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.extract_info.return_value = info
            ctx.download.return_value = None
            mock_ydl_cls.return_value = ctx

            result = download("https://bilibili.com/video/BV1xx411", output_base)

        assert (result / ".step1.done").exists()

    def test_returns_output_dir_path(self, output_base):
        info = _mock_info("BV_abc123")

        with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.extract_info.return_value = info
            ctx.download.return_value = None
            mock_ydl_cls.return_value = ctx

            result = download("https://bilibili.com/video/BV_abc123", output_base)

        assert result == output_base / "BV_abc123"


class TestDownloadMetadata:
    def test_writes_metadata_json(self, output_base):
        info = _mock_info()

        with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.extract_info.return_value = info
            ctx.download.return_value = None
            mock_ydl_cls.return_value = ctx

            result = download("https://bilibili.com/video/BV1xx411", output_base)

        metadata = json.loads((result / "metadata.json").read_text(encoding="utf-8"))
        assert metadata["id"] == info["id"]
        assert metadata["title"] == info["title"]

    def test_metadata_contains_all_fields(self, output_base):
        info = _mock_info()

        with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.extract_info.return_value = info
            ctx.download.return_value = None
            mock_ydl_cls.return_value = ctx

            result = download("https://bilibili.com/video/BV1xx411", output_base)

        metadata = json.loads((result / "metadata.json").read_text(encoding="utf-8"))
        for key in ("id", "title", "duration", "url", "uploader", "webpage_url"):
            assert key in metadata

    def test_metadata_duration(self, output_base):
        info = _mock_info()
        info["duration"] = 300

        with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.extract_info.return_value = info
            ctx.download.return_value = None
            mock_ydl_cls.return_value = ctx

            result = download("https://bilibili.com/video/BV1xx411", output_base)

        metadata = json.loads((result / "metadata.json").read_text(encoding="utf-8"))
        assert metadata["duration"] == 300

    def test_metadata_missing_optional_fields_graceful(self, output_base):
        # info without uploader or webpage_url
        info = {"id": "BV1xx411", "title": "T", "duration": 10, "url": "http://x"}

        with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.extract_info.return_value = info
            ctx.download.return_value = None
            mock_ydl_cls.return_value = ctx

            result = download("http://x", output_base)

        metadata = json.loads((result / "metadata.json").read_text(encoding="utf-8"))
        assert metadata["uploader"] == ""
        assert metadata["webpage_url"] == "http://x"


class TestDownloadCookies:
    def test_cookies_file_passed_to_probe(self, output_base):
        info = _mock_info()
        cookies = "/tmp/cookies.txt"

        with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.extract_info.return_value = info
            ctx.download.return_value = None
            mock_ydl_cls.return_value = ctx

            download("https://bilibili.com/video/BV1xx411", output_base, cookies_file=cookies)

        # First call is probe opts
        first_call_opts = mock_ydl_cls.call_args_list[0][0][0]
        assert first_call_opts.get("cookiefile") == cookies

    def test_no_cookies_by_default(self, output_base):
        info = _mock_info()

        with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.extract_info.return_value = info
            ctx.download.return_value = None
            mock_ydl_cls.return_value = ctx

            download("https://bilibili.com/video/BV1xx411", output_base)

        first_call_opts = mock_ydl_cls.call_args_list[0][0][0]
        assert "cookiefile" not in first_call_opts


class TestDownloadOutputDir:
    def test_creates_output_dir(self, output_base):
        info = _mock_info("BV_newdir")

        with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.extract_info.return_value = info
            ctx.download.return_value = None
            mock_ydl_cls.return_value = ctx

            result = download("https://bilibili.com/video/BV_newdir", output_base)

        assert result.is_dir()

    def test_output_dir_is_video_id_subfolder(self, output_base):
        info = _mock_info("BV_unique99")

        with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.extract_info.return_value = info
            ctx.download.return_value = None
            mock_ydl_cls.return_value = ctx

            result = download("https://bilibili.com/video/BV_unique99", output_base)

        assert result.name == "BV_unique99"
        assert result.parent == output_base
