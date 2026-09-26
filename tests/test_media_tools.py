"""
Tests for media_tools: probe_media, extract_thumbnail, make_proxy.
"""
from pathlib import Path
import subprocess
import imageio_ffmpeg
import pytest

from media_tools import probe_media, extract_thumbnail, make_proxy


@pytest.fixture
def sample_video(tmp_path: Path) -> Path:
    """Create a 3-second 320x240 synthetic video with audio."""
    v_path = tmp_path / "sample.mp4"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi", "-i", "color=c=green:s=320x240:r=25:d=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(v_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return v_path


def test_probe_media(sample_video: Path):
    meta = probe_media(sample_video)
    assert meta["has_video"] is True
    assert meta["has_audio"] is True
    assert 2.8 <= meta["duration_s"] <= 3.2
    assert meta["width"] == 320
    assert meta["height"] == 240
    assert meta["codec"] in ("h264", "libx264", "avc1")


def test_probe_media_not_found(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        probe_media(tmp_path / "nonexistent.mp4")


def test_probe_media_video_only(tmp_path: Path):
    v_path = tmp_path / "video_only.mp4"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi", "-i", "color=c=red:s=160x120:r=25:d=2",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        str(v_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    meta = probe_media(v_path)
    assert meta["has_video"] is True
    assert meta["has_audio"] is False


def test_extract_thumbnail(sample_video: Path, tmp_path: Path):
    thumb_path = tmp_path / "thumb.jpg"
    out = extract_thumbnail(sample_video, timestamp=1.0, output_path=thumb_path, width=160)
    assert out.exists()
    assert out.stat().st_size > 0


def test_make_proxy(sample_video: Path, tmp_path: Path):
    proxy_path = tmp_path / "proxy.mp4"
    out = make_proxy(sample_video, proxy_path)
    assert out.exists()
    assert out.stat().st_size > 0
    meta = probe_media(out)
    assert meta["has_video"] is True
    assert meta["has_audio"] is True
