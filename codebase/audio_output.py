"""
Audio extraction module.
Directly invokes FFmpeg via imageio_ffmpeg to extract high-quality PCM WAV audio from video files.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import imageio_ffmpeg

from config import Config

logger = logging.getLogger(__name__)


def extract_audio_from_video(
    video_path: str | Path,
    output_audio_path: str | Path,
    config: Config | None = None,
) -> Path:
    """
    Extract mono 16-bit PCM WAV audio from a video file using FFmpeg.

    Args:
        video_path: Path to the input video file.
        output_audio_path: Path where the extracted WAV audio should be saved.
        config: Optional Config instance for sample rate and channel settings.

    Returns:
        Path to the extracted audio file.

    Raises:
        FileNotFoundError: If video_path does not exist.
        RuntimeError: If FFmpeg fails or if no audio stream exists in the video.
    """
    cfg = config or Config()
    v_path = Path(video_path).resolve()
    out_path = Path(output_audio_path).resolve()

    if not v_path.exists():
        raise FileNotFoundError(f"Video file not found: {v_path}")

    if not v_path.is_file():
        raise ValueError(f"Video path is not a file: {v_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    channels = 1 if cfg.mono else 2
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    cmd = [
        ffmpeg_exe,
        "-y",
        "-loglevel", "error",
        "-i", str(v_path),
        "-vn",
        "-ac", str(channels),
        "-ar", str(cfg.sample_rate),
        "-c:a", "pcm_s16le",
        str(out_path),
    ]

    logger.info("Extracting audio from %s -> %s (sr=%d, ch=%d)", v_path.name, out_path.name, cfg.sample_rate, channels)

    try:
        proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() if e.stderr else "Unknown FFmpeg error"
        if "does not contain any stream" in err_msg or "Output file does not contain any stream" in err_msg or "matches no streams" in err_msg:
            raise RuntimeError(f"No audio stream found in video '{v_path.name}': {err_msg}") from e
        raise RuntimeError(f"FFmpeg audio extraction failed for '{v_path.name}': {err_msg}") from e

    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError(f"Audio extraction produced empty or missing file: {out_path}")

    logger.info("Audio extracted successfully: %s (%.2f MB)", out_path.name, out_path.stat().st_size / (1024 * 1024))
    return out_path
