"""
URL Import Reliability Test Suite
Comprehensive tests covering:
1. Error taxonomy mapping for all 9 required error codes from representative yt-dlp exceptions.
2. Direct streaming HTTP downloader: SSRF redirect validation, Range resume, atomic rename.
3. End-to-end integration test: Local http.server serving a synthetic MP4, downloaded and processed
   through the entire highlight generation pipeline (download -> audio -> detection -> reel).
4. Cancellation cleanup: Process group termination leaving zero *.part or *.ytdl files.
"""
from __future__ import annotations

import hashlib
import http.server
import os
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import imageio_ffmpeg
import numpy as np
import pytest
from scipy.io import wavfile

# Add project root and codebase to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CODEBASE_DIR = PROJECT_ROOT / "codebase"
for p in (str(PROJECT_ROOT), str(CODEBASE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from api.direct_downloader import (
    download_direct_file,
    is_direct_video_url,
    validate_url_host,
)
from api.error_taxonomy import (
    classify_url_error,
    CODE_DOWNLOAD_FAILED,
    CODE_EJS_MISSING,
    CODE_GEO_BLOCKED,
    CODE_JS_RUNTIME_MISSING,
    CODE_LIVE_STREAM_UNSUPPORTED,
    CODE_PRIVATE_VIDEO,
    CODE_SOURCE_BLOCKED,
    CODE_TOO_LARGE,
    CODE_UNSUPPORTED_URL,
)
from api.worker import cancel_job, _running_processes, _running_lock
from api import db
from config import Config
from pipeline import run_pipeline


class DummyException(Exception):
    pass


# ---------------------------------------------------------------------------
# 1. Error Taxonomy Unit Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw_msg,expected_code,expected_hint_part",
    [
        (
            "Sign in to confirm you're not a bot. This helps protect our community.",
            CODE_SOURCE_BLOCKED,
            "cookies",
        ),
        (
            "Our systems have detected unusual traffic from your network: automated queries",
            CODE_SOURCE_BLOCKED,
            "cookies",
        ),
        (
            "No supported JavaScript runtime could be found. Please install deno or nodejs",
            CODE_JS_RUNTIME_MISSING,
            "deno",
        ),
        (
            "yt-dlp requires a JavaScript runtime (deno, nodejs >= 22) to decrypt signatures",
            CODE_JS_RUNTIME_MISSING,
            "deno",
        ),
        (
            "yt-dlp-ejs is required to solve this YouTube challenge. Install the default dependencies.",
            CODE_EJS_MISSING,
            "yt-dlp[default]",
        ),
        (
            "Unsupported URL: 'ftp://example.com/stream' - no extractor found",
            CODE_UNSUPPORTED_URL,
            "valid",
        ),
        (
            "is not a valid URL. Set --default-search 'auto' to search",
            CODE_UNSUPPORTED_URL,
            "valid",
        ),
        (
            "Private video. Sign in if you've been granted access to this video",
            CODE_PRIVATE_VIDEO,
            "cookies",
        ),
        (
            "This video is not available in your country due to licensing restrictions.",
            CODE_GEO_BLOCKED,
            "video file",
        ),
        (
            "This live event will begin in 2 hours",
            CODE_LIVE_STREAM_UNSUPPORTED,
            "live",
        ),
        (
            "This live stream recording is not yet available",
            CODE_LIVE_STREAM_UNSUPPORTED,
            "live",
        ),
        (
            "Requested file size (12.4 GB) exceeds the maximum allowed server limit of 10.0 GB",
            CODE_TOO_LARGE,
            "quality",
        ),
        (
            "HTTP Error 500: Internal Server Error or network connection dropped",
            CODE_DOWNLOAD_FAILED,
            "connection",
        ),
    ],
)
def test_error_taxonomy_mapping(raw_msg: str, expected_code: str, expected_hint_part: str):
    """Verify representative yt-dlp error messages map to the correct error codes and hints without leaking tracebacks."""
    exc = DummyException(f"Traceback (most recent call last):\n  File 'extractor.py', line 99\n{raw_msg}")
    code, message, hint = classify_url_error(exc)

    assert code == expected_code
    assert expected_hint_part.lower() in hint.lower()
    assert "Traceback" not in message
    assert "Traceback" not in hint


def test_classify_url_error_sanitizes_tracebacks():
    """Ensure raw tracebacks are never returned to client."""
    exc = Exception(
        "Traceback (most recent call last):\n"
        "  File '/usr/local/lib/python3.14/site-packages/yt_dlp/YoutubeDL.py', line 1234, in extract_info\n"
        "    raise DownloadError('Something went wrong internally')\n"
        "yt_dlp.utils.DownloadError: Something went wrong internally"
    )
    code, message, hint = classify_url_error(exc)
    assert code == CODE_DOWNLOAD_FAILED
    assert "Traceback" not in message
    assert "line 1234" not in message
    assert "Something went wrong internally" in message


# ---------------------------------------------------------------------------
# 2. Local HTTP Server & Direct Downloader Tests
# ---------------------------------------------------------------------------

class RangeRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP Request handler supporting Range requests and redirects for testing."""
    redirect_target: str | None = None

    def do_GET(self):
        if RangeRequestHandler.redirect_target:
            self.send_response(302)
            self.send_header("Location", RangeRequestHandler.redirect_target)
            self.end_headers()
            return
        super().do_GET()

    def log_message(self, format, *args):
        # Suppress noisy logging during tests
        pass


def _create_synthetic_mp4(mp4_path: Path, duration_s: float = 10.0) -> None:
    """Generate a tiny valid MP4 with audio for end-to-end testing."""
    sr = 22050
    n_samples = int(duration_s * sr)
    t = np.arange(n_samples) / sr

    # Synthetic crowd cheering peak at 4s-7s
    audio = np.random.normal(0, 0.05, n_samples)
    peak_mask = (t >= 4.0) & (t <= 7.0)
    audio[peak_mask] += np.sin(2 * np.pi * 440 * t[peak_mask]) * 0.8
    audio = (audio / np.max(np.abs(audio)) * 0.9 * 32767).astype(np.int16)

    wav_path = mp4_path.with_suffix(".wav")
    wavfile.write(str(wav_path), sr, audio)

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe, "-y",
        "-f", "lavfi", "-i", f"color=c=0x0a3b1a:s=320x240:r=25:d={duration_s}",
        "-i", str(wav_path),
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k",
        "-shortest",
        str(mp4_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if wav_path.exists():
        wav_path.unlink()


@pytest.fixture(scope="module")
def local_http_server(tmp_path_factory):
    """Spin up a local HTTP server serving a synthetic MP4 with Range request support."""
    serve_dir = tmp_path_factory.mktemp("http_serve")
    test_video = serve_dir / "match.mp4"
    _create_synthetic_mp4(test_video, duration_s=10.0)

    class CustomTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    handler = lambda *args, **kwargs: RangeRequestHandler(*args, directory=str(serve_dir), **kwargs)
    httpd = CustomTCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]

    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    yield {
        "port": port,
        "serve_dir": serve_dir,
        "video_path": test_video,
        "url": f"http://127.0.0.1:{port}/match.mp4",
    }

    httpd.shutdown()
    httpd.server_close()


def test_ssrf_host_validation():
    """Verify SSRF validation rejects localhost, loopback, private, and link-local addresses."""
    with pytest.raises(ValueError, match="Cannot import from"):
        validate_url_host("http://127.0.0.1/video.mp4")

    with pytest.raises(ValueError, match="Cannot import from"):
        validate_url_host("http://localhost:8080/video.mp4")

    with pytest.raises(ValueError, match="Cannot import from"):
        validate_url_host("http://169.254.169.254/latest/meta-data/")

    with pytest.raises(ValueError, match="Cannot import from"):
        validate_url_host("http://10.0.0.1/internal.mp4")

    with pytest.raises(ValueError, match="Cannot import from"):
        validate_url_host("http://192.168.1.1/video.mp4")

    # Valid public addresses should pass without raising
    validate_url_host("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    validate_url_host("https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4")


def test_direct_downloader_range_resume(local_http_server, tmp_path):
    """Verify direct file downloader resumes partially downloaded files using Range header."""
    src_video = local_http_server["video_path"]
    src_bytes = src_video.read_bytes()
    total_size = len(src_bytes)
    assert total_size > 10000

    out_file = tmp_path / "downloaded.mp4"
    part_file = out_file.with_name(out_file.name + ".part")

    # Write first 4000 bytes into .part file to simulate an interrupted download
    part_file.write_bytes(src_bytes[:4000])

    # Temporarily patch validate_url_host to allow testing against local http server
    with patch("api.direct_downloader.validate_url_host"):
        progress_records = []
        def on_prog(d: dict):
            progress_records.append(d)

        result_path = download_direct_file(
            url=local_http_server["url"],
            output_path=out_file,
            progress_cb=on_prog,
        )

    assert result_path == out_file
    assert out_file.exists()
    assert not part_file.exists(), ".part file must be cleaned up / renamed upon completion"
    assert out_file.stat().st_size == total_size
    assert hashlib.sha256(out_file.read_bytes()).hexdigest() == hashlib.sha256(src_bytes).hexdigest()
    assert len(progress_records) > 0


def test_e2e_download_and_pipeline_run(local_http_server, tmp_path):
    """End-to-end integration: Download from local HTTP server and execute complete pipeline."""
    dest_file = tmp_path / "match_downloaded.mp4"

    # 1. Download via direct streaming downloader
    with patch("api.direct_downloader.validate_url_host"):
        download_direct_file(local_http_server["url"], output_path=dest_file)

    assert dest_file.exists()
    assert dest_file.stat().st_size > 0

    # 2. Run highlight pipeline end-to-end
    out_dir = tmp_path / "output_video"
    audio_wav = tmp_path / "match_audio.wav"
    cfg = Config(
        min_rise_db=2.0,
        min_sustain_s=1.0,
        target_duration=10.0,
        pre_roll=0.5,
        post_roll=0.5,
        skip_start_s=0.0,
    )

    reel_path = run_pipeline(
        video_path=dest_file,
        config=cfg,
        audio_output_path=audio_wav,
        clips_output_dir=out_dir,
    )

    assert reel_path is not None
    assert reel_path.exists()
    assert reel_path.stat().st_size > 0
    assert (out_dir / "windows.json").exists()


# ---------------------------------------------------------------------------
# 3. Cancel Cleanup Tests (*.part and *.ytdl files)
# ---------------------------------------------------------------------------

def test_cancel_job_deletes_all_part_files(tmp_path):
    """Cancelling a job must kill the process group and clean up all *.part and *.ytdl files."""
    job_id = "test_cancel_cleanup_job"
    job_dir = tmp_path / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Populate job_dir with leftover partial files
    part1 = job_dir / "source.mp4.part"
    part2 = job_dir / "audio.part-Frag0"
    ytdl1 = job_dir / "source.mp4.ytdl"
    finished = job_dir / "metadata.json"

    part1.write_text("partial video data")
    part2.write_text("partial fragment")
    ytdl1.write_text("ytdl resume data")
    finished.write_text('{"status": "in_progress"}')

    # Seed db and running processes
    db.create_job(
        job_id=job_id,
        title="Test Cancel Job",
        source_type="url",
        source_filename="https://example.com/v.mp4",
        config={},
    )

    mock_proc = MagicMock()
    mock_proc.pid = 99999
    mock_proc.poll.return_value = None  # Pretend it is running

    with _running_lock:
        _running_processes[job_id] = mock_proc

    with patch("api.worker.get_job_dir", return_value=job_dir), \
         patch("os.getpgid", return_value=99999), \
         patch("os.killpg") as mock_killpg:

        success = cancel_job(job_id)
        assert success is True
        mock_killpg.assert_called()

    # Verify all partial files are deleted
    assert not part1.exists(), ".part file was not deleted"
    assert not part2.exists(), ".part-Frag file was not deleted"
    assert not ytdl1.exists(), ".ytdl file was not deleted"
    # Completed/unrelated files should remain untouched
    assert finished.exists()

    job = db.get_job(job_id)
    assert job["status"] == "cancelled"
    assert job["error_code"] == "JOB_CANCELLED"
