"""
Media tools module.
Provides fast media probing, thumbnail extraction, and web proxy generation using direct FFmpeg commands.
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

import imageio_ffmpeg

logger = logging.getLogger(__name__)


def probe_media(video_path: str | Path) -> dict[str, Any]:
    """
    Fast media probe using ffmpeg -i stderr parsing.
    Extracts duration_s, has_video, has_audio, width, height, and codec.

    Args:
        video_path: Path to the media file.

    Returns:
        Dict with keys: duration_s, has_video, has_audio, width, height, codec.

    Raises:
        FileNotFoundError: If the media file does not exist.
    """
    path = Path(video_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Media file not found: {path}")

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ffmpeg_exe, "-i", str(path)]

    # FFmpeg exits with non-zero when given just -i, but stderr contains metadata
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stderr = res.stderr or ""

    duration_s = 0.0
    has_video = False
    has_audio = False
    width: int | None = None
    height: int | None = None
    video_codec: str | None = None

    # Parse duration: "Duration: 00:01:23.45"
    dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
    if dur_match:
        hrs = int(dur_match.group(1))
        mins = int(dur_match.group(2))
        secs = float(dur_match.group(3))
        duration_s = round(hrs * 3600 + mins * 60 + secs, 3)

    # Parse streams line by line
    for line in stderr.splitlines():
        if "Stream #" in line:
            if "Video:" in line:
                has_video = True
                # Match codec: e.g. "Video: h264"
                codec_match = re.search(r"Video:\s*([a-zA-Z0-9_-]+)", line)
                if codec_match and not video_codec:
                    video_codec = codec_match.group(1)
                # Match dimensions: e.g. "1280x720" or "640x360 [SAR..."
                dim_match = re.search(r"(\d{2,5})x(\d{2,5})", line)
                if dim_match and width is None:
                    width = int(dim_match.group(1))
                    height = int(dim_match.group(2))
            elif "Audio:" in line:
                has_audio = True

    return {
        "duration_s": duration_s,
        "has_video": has_video,
        "has_audio": has_audio,
        "width": width,
        "height": height,
        "codec": video_codec,
    }


def extract_thumbnail(
    video_path: str | Path,
    timestamp: float,
    output_path: str | Path,
    width: int = 480,
) -> Path:
    """
    Extract a single frame thumbnail at the specified timestamp.

    Args:
        video_path: Path to the input video.
        timestamp: Timestamp in seconds.
        output_path: Path where the output JPEG should be saved.
        width: Target width (height scales proportionally to preserve aspect ratio).

    Returns:
        Path to the generated JPEG thumbnail.
    """
    v_path = Path(video_path).resolve()
    out_path = Path(output_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not v_path.exists():
        raise FileNotFoundError(f"Video file not found: {v_path}")

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    ts = max(0.0, timestamp)

    # -ss before -i is fast seek; -frames:v 1 extracts 1 frame
    cmd = [
        ffmpeg_exe,
        "-y",
        "-loglevel", "error",
        "-ss", f"{ts:.3f}",
        "-i", str(v_path),
        "-frames:v", "1",
        "-vf", f"scale='min({width},iw)':-2",
        "-q:v", "3",
        str(out_path),
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() if e.stderr else "Unknown error"
        raise RuntimeError(f"FFmpeg thumbnail extraction failed at {ts:.2f}s: {err_msg}") from e

    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError(f"Thumbnail extraction produced empty or missing file: {out_path}")

    return out_path


def make_proxy(
    video_path: str | Path,
    output_path: str | Path,
) -> Path:
    """
    Generate a low-resolution scrubbable proxy MP4 (480p, H.264 ultrafast CRF 28, AAC 96k, +faststart).

    Args:
        video_path: Path to source video.
        output_path: Destination path for proxy MP4.

    Returns:
        Path to the generated proxy MP4.
    """
    v_path = Path(video_path).resolve()
    out_path = Path(output_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not v_path.exists():
        raise FileNotFoundError(f"Video file not found: {v_path}")

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    cmd = [
        ffmpeg_exe,
        "-y",
        "-loglevel", "error",
        "-i", str(v_path),
        "-vf", "scale='min(480,iw)':-2",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "28",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "96k",
        "-movflags", "+faststart",
        str(out_path),
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() if e.stderr else "Unknown error"
        raise RuntimeError(f"FFmpeg proxy generation failed: {err_msg}") from e

    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError(f"Proxy generation produced empty or missing file: {out_path}")

    return out_path
