"""
Tests for YouTube bot check error mapping, yt-dlp cookie options, and JS runtime diagnostics.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Ensure codebase and api are on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CODEBASE_DIR = PROJECT_ROOT / "codebase"
for p in (str(PROJECT_ROOT), str(CODEBASE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from api.runner import classify_download_error, is_bot_check_error
from api.runtime import check_js_runtime, ensure_js_runtime_on_path
from api.main import app
from pipeline import download_video_from_url, _parse_browser_cookies_spec


class DummyDownloadError(Exception):
    pass


def test_is_bot_check_error_detection():
    """Verify various bot-check phrases are correctly detected."""
    assert is_bot_check_error("ERROR: Sign in to confirm you're not a bot. This helps protect our community.")
    assert is_bot_check_error("YouTube returned: confirm you're not a bot")
    assert is_bot_check_error("Sign in to confirm your age or account")
    assert is_bot_check_error("Our systems have detected unusual traffic from your computer network: automated queries")
    assert is_bot_check_error("Blocked by robot detection")
    assert not is_bot_check_error("ERROR: Video unavailable")
    assert not is_bot_check_error("HTTP Error 404: Not Found")


def test_classify_download_error_source_blocked():
    """Bot check messages should map to SOURCE_BLOCKED with a clean friendly message."""
    exc = DummyDownloadError("ERROR: [youtube] dQw4w9WgXcQ: Sign in to confirm you're not a bot. This helps protect our community.")
    code, msg = classify_download_error(exc)
    assert code == "SOURCE_BLOCKED"
    assert "YouTube blocked this download" in msg
    assert "Traceback" not in msg


def test_classify_download_error_download_failed():
    """General download errors should map to DOWNLOAD_FAILED without exposing tracebacks."""
    exc = DummyDownloadError(
        "Traceback (most recent call last):\n"
        "  File 'extractor.py', line 123, in extract\n"
        "ERROR: [youtube] dQw4w9WgXcQ: Video unavailable\n"
    )
    code, msg = classify_download_error(exc)
    assert code == "DOWNLOAD_FAILED"
    assert "Video unavailable" in msg
    assert "Traceback" not in msg
    assert "File" not in msg


def test_parse_browser_cookies_spec():
    """Verify browser cookie string parsing matches yt-dlp specification."""
    # Simple browser
    spec = _parse_browser_cookies_spec("chrome")
    assert spec[0] == "chrome"

    # Browser with profile
    spec = _parse_browser_cookies_spec("firefox:Default")
    assert spec[0] == "firefox"
    assert spec[1] == "Default"

    # Already a tuple
    spec = _parse_browser_cookies_spec(("safari", None, None, None))
    assert spec == ("safari", None, None, None)


def test_download_video_from_url_options(tmp_path: Path):
    """Verify download_video_from_url configures cookies and does not pass player_client extractor_args."""
    captured_opts = {}

    class MockYoutubeDL:
        def __init__(self, opts):
            nonlocal captured_opts
            captured_opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download=True):
            return {"title": "Test Video", "ext": "mp4"}

        def prepare_filename(self, info):
            p = tmp_path / "test.mp4"
            p.write_bytes(b"dummy video content")
            return str(p)

    with patch("yt_dlp.YoutubeDL", MockYoutubeDL):
        result = download_video_from_url(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            output_dir=tmp_path,
            cookies_from_browser="chrome",
            cookies_file=tmp_path / "cookies.txt",
        )

        assert result.exists()
        # Verify player_client extractor_args override was removed
        assert "extractor_args" not in captured_opts
        # Verify cookies parameters are wired
        assert "cookiesfrombrowser" in captured_opts
        assert captured_opts["cookiesfrombrowser"][0] == "chrome"
        assert captured_opts["cookiefile"] == str(tmp_path / "cookies.txt")


def test_health_endpoint_includes_js_runtime():
    """Verify /api/health returns js_runtime status."""
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert "js_runtime" in data
    assert "available" in data["js_runtime"]
    if data["js_runtime"]["available"]:
        assert data["js_runtime"]["runtime"] in ("node", "deno")
        assert data["js_runtime"]["path"] is not None


def test_health_endpoint_warns_when_no_js_runtime(monkeypatch):
    """Verify /api/health returns available: False and warning when no JS runtime is on PATH."""
    monkeypatch.setattr("api.runtime.ensure_js_runtime_on_path", lambda: (None, None))
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["js_runtime"]["available"] is False
    assert "warning" in data["js_runtime"]
    assert "No JavaScript runtime" in data["js_runtime"]["warning"]
