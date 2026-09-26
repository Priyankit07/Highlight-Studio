"""
Clip cutting module.
Cuts video highlight clips with video/audio fades, modern encoding compatibility (yuv420p, faststart),
parallel multi-threading, safe single-quote escaping, and post-combination duration verification.
"""
from __future__ import annotations

import concurrent.futures
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

import imageio_ffmpeg
from tqdm import tqdm

from config import Config
from spike_window import Window
from media_tools import probe_media

logger = logging.getLogger(__name__)


def _cut_single_clip(
    idx: int,
    start: float,
    end: float,
    video_path: Path,
    output_file: Path,
    config: Config,
) -> Path:
    """Cut an individual highlight clip from the source video using FFmpeg."""
    clip_dur = max(0.01, end - start)
    fade_d = config.fade_duration_s

    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-y",
        "-loglevel", "error",
        "-ss", f"{start:.3f}",
        "-to", f"{end:.3f}",
        "-i", str(video_path),
    ]

    # Apply video and audio fades to eliminate pop/click artifacts
    if fade_d > 0 and clip_dur > 2 * fade_d:
        vf = f"fade=t=in:st=0:d={fade_d:.3f},fade=t=out:st={clip_dur - fade_d:.3f}:d={fade_d:.3f}"
        af = f"afade=t=in:st=0:d={fade_d:.3f},afade=t=out:st={clip_dur - fade_d:.3f}:d={fade_d:.3f}"
        cmd.extend(["-vf", vf, "-af", af])
    elif fade_d > 0 and clip_dur > 0.2:
        small_fade = clip_dur / 4.0
        vf = f"fade=t=in:st=0:d={small_fade:.3f},fade=t=out:st={clip_dur - small_fade:.3f}:d={small_fade:.3f}"
        af = f"afade=t=in:st=0:d={small_fade:.3f},afade=t=out:st={clip_dur - small_fade:.3f}:d={small_fade:.3f}"
        cmd.extend(["-vf", vf, "-af", af])

    cmd.extend([
        "-map", "0:v:0",
        "-map", "0:a:0?",
        "-c:v", "libx264",
        "-crf", str(config.crf),
        "-preset", config.preset,
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "aac",
        "-b:a", "192k",
        str(output_file),
    ])

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() if e.stderr else "Unknown error"
        raise RuntimeError(f"FFmpeg failed while cutting clip [{idx + 1}] ({start:.2f}s - {end:.2f}s): {err_msg}") from e

    return output_file


def cut_highlight_clips(
    video_path: str | Path,
    windows: list[Window] | list[tuple[float, float]] | list[list[float]],
    output_folder: str | Path,
    config: Config | None = None,
    pre_buffer: float = 0.0,
    post_buffer: float = 0.0,
    combine: bool = True,
    progress_cb: Callable[[str, float | None, str], None] | None = None,
) -> Path | list[Path] | None:
    """
    Cut clips from video based on selected windows and combine into highlights reel.

    Args:
        video_path: Path to source video.
        windows: List of Window objects or (start, end) tuples.
        output_folder: Target output directory.
        config: Configuration instance.
        pre_buffer: Buffer added before window start (default 0).
        post_buffer: Buffer added after window end (default 0).
        combine: Whether to combine individual clips into highlights.mp4.
        progress_cb: Optional progress callback (stage, fraction 0..1, message).

    Returns:
        Path to combined highlights MP4, list of clip Paths if not combined, or None if no clips.
    """
    cfg = config or Config()
    v_path = Path(video_path).resolve()
    out_dir = Path(output_folder).resolve()

    if not v_path.exists():
        raise FileNotFoundError(f"Video file not found: {v_path}")

    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Filter to selected windows
    target_clips: list[tuple[float, float]] = []
    for w in windows:
        if isinstance(w, Window):
            if w.selected:
                target_clips.append((w.start, w.end))
        elif isinstance(w, (tuple, list)) and len(w) >= 2:
            target_clips.append((float(w[0]), float(w[1])))

    if not target_clips:
        logger.warning(
            "No windows selected for cutting. Try lowering min_rise_db (currently %.1f dB), "
            "shortening min_sustain_s (currently %.1fs), or lowering skip_start_s (currently %.1fs).",
            cfg.min_rise_db, cfg.min_sustain_s, cfg.skip_start_s
        )
        return None

    # Get video duration to prevent over-reading (fast probe)
    total_video_dur: float = 0.0
    try:
        meta = probe_media(v_path)
        total_video_dur = float(meta.get("duration_s", 0.0))
    except Exception as e:
        logger.debug("Fast probe failed, falling back: %s", e)
        try:
            _, probed_dur = imageio_ffmpeg.count_frames_and_secs(str(v_path))
            total_video_dur = float(probed_dur) if probed_dur is not None else 0.0
        except Exception:
            total_video_dur = 0.0

    # 2. Prepare clip boundaries
    clamped_clips: list[tuple[float, float]] = []
    for s, e in target_clips:
        c_start = max(0.0, s - pre_buffer)
        c_end = e + post_buffer
        if total_video_dur > 0:
            c_end = min(total_video_dur, c_end)
        if c_end > c_start:
            clamped_clips.append((c_start, c_end))

    if not clamped_clips:
        logger.warning("All clips were clamped to zero duration.")
        return None

    logger.info("Cutting %d highlight clips from %s (parallel workers: %d)...",
                len(clamped_clips), v_path.name, cfg.max_workers)

    expected_total_duration = sum(e - s for s, e in clamped_clips)

    # 3. Cut clips in parallel or sequentially with tqdm
    clip_files: list[Path] = [out_dir / f"clip_{i+1:03d}.mp4" for i in range(len(clamped_clips))]

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, cfg.max_workers)) as executor:
        futures = {}
        for i, (c_start, c_end) in enumerate(clamped_clips):
            fut = executor.submit(
                _cut_single_clip,
                idx=i,
                start=c_start,
                end=c_end,
                video_path=v_path,
                output_file=clip_files[i],
                config=cfg,
            )
            futures[fut] = (i, c_start, c_end)

        completed_clips = 0
        with tqdm(total=len(futures), desc="Cutting clips", unit="clip") as pbar:
            for fut in concurrent.futures.as_completed(futures):
                i, c_start, c_end = futures[fut]
                try:
                    fut.result()
                    completed_clips += 1
                    if progress_cb:
                        progress_cb("rendering", round((completed_clips / len(clamped_clips)) * 0.9, 3), f"clip {completed_clips}/{len(clamped_clips)}")
                    pbar.set_postfix({"clip": f"{completed_clips}/{len(clamped_clips)}", "span": f"{c_start:.1f}-{c_end:.1f}s"})
                except Exception as exc:
                    logger.error("Error cutting clip %d: %s", i + 1, exc)
                    raise
                pbar.update(1)

    if not combine:
        logger.info("Generated %d individual highlight clips in %s", len(clip_files), out_dir)
        return clip_files

    # 4. Combine clips via FFmpeg concat demuxer
    if progress_cb:
        progress_cb("rendering", 0.92, "Assembling highlight reel...")
    concat_file = out_dir / "concat.txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for clip_file in clip_files:
            # Escape single quotes and spaces for safe concat demuxer parsing
            escaped = str(clip_file.resolve()).replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    combined_output = out_dir / "highlights.mp4"
    logger.info("Combining %d clips into highlights reel: %s...", len(clip_files), combined_output.name)

    concat_cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-y",
        "-loglevel", "error",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-map", "0:v:0",
        "-map", "0:a:0?",
        "-c", "copy",
        "-movflags", "+faststart",
        str(combined_output),
    ]

    try:
        subprocess.run(concat_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() if e.stderr else "Unknown concat error"
        raise RuntimeError(f"FFmpeg concat failed: {err_msg}") from e

    # 5. Duration verification check
    try:
        meta_out = probe_media(combined_output)
        actual_secs = float(meta_out.get("duration_s", 0.0))
        if actual_secs == 0.0:
            _, probed_secs = imageio_ffmpeg.count_frames_and_secs(str(combined_output))
            if probed_secs is not None:
                actual_secs = float(probed_secs)
        delta = abs(actual_secs - expected_total_duration)
        logger.info("Reel duration: %.2fs (expected: %.2fs, delta: %.2fs)", actual_secs, expected_total_duration, delta)
        if delta > 0.5:
            logger.warning("Combined reel duration delta (%.2fs) exceeds 0.5s tolerance.", delta)
    except Exception as e:
        logger.debug("Could not verify combined reel duration: %s", e)

    if progress_cb:
        progress_cb("rendering", 1.0, "Highlights reel complete")

    # 6. Cleanup individual clips unless keep_clips is requested
    if not cfg.keep_clips:
        for clip_file in clip_files:
            try:
                if clip_file.exists():
                    clip_file.unlink()
            except OSError:
                pass
        try:
            if concat_file.exists():
                concat_file.unlink()
        except OSError:
            pass

    logger.info("Highlights reel created successfully: %s (%.2f MB)",
                combined_output.name, combined_output.stat().st_size / (1024 * 1024))
    return combined_output