"""
Test clip cutting and concat demuxer escaping with filenames containing quotes, spaces, and special characters.
"""
from pathlib import Path
import subprocess
import imageio_ffmpeg
import pytest

from clip_cutter import cut_highlight_clips
from spike_window import Window
from config import Config


def test_concat_escaping_with_quotes_and_spaces(tmp_path: Path):
    """Ensure concat file properly escapes single quotes, spaces, and punctuation."""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    # Create dummy source video with tricky name
    test_dir = tmp_path / "match '2026' special & cool"
    test_dir.mkdir(parents=True, exist_ok=True)
    src_video = test_dir / "clip 'one' test.mp4"

    cmd = [
        ffmpeg_exe, "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=25:d=5",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=5",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(src_video)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    assert src_video.exists()

    windows = [
        Window(start=1.0, end=2.5, score=50.0, peak_time=1.5, selected=True),
        Window(start=3.0, end=4.5, score=40.0, peak_time=3.5, selected=True),
    ]

    out_folder = test_dir / "highlights output 'dir'"
    cfg = Config(preset="ultrafast", max_workers=1)

    combined_file = cut_highlight_clips(
        video_path=src_video,
        windows=windows,
        output_folder=out_folder,
        config=cfg,
    )

    assert combined_file is not None
    assert combined_file.exists()
    assert combined_file.stat().st_size > 0


def test_no_windows_selected_returns_none(tmp_path: Path):
    """When no windows are selected, cut_highlight_clips exits cleanly and returns None."""
    windows = [
        Window(start=1.0, end=3.0, score=10.0, peak_time=2.0, selected=False),
    ]
    src_video = tmp_path / "dummy.mp4"
    src_video.touch()

    res = cut_highlight_clips(src_video, windows, tmp_path / "out")
    assert res is None
