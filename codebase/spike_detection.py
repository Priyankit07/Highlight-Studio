"""
Spike detection module.
Performs audio excitement candidate detection using an adaptive rolling baseline in dB,
rejecting short transients (clicks, thumps, whistles) and intro jingles.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import wavfile
import scipy.ndimage
from scipy.signal import butter, sosfilt

from config import Config

logger = logging.getLogger(__name__)


@dataclass
class Spike:
    """Represents a detected audio excitement spike/candidate."""
    onset: float          # Start time in seconds
    offset: float         # End time in seconds
    peak_time: float      # Time of maximum rise above baseline
    peak_rise_db: float   # Peak rise above baseline in dB
    score: float          # Area above the min_rise_db threshold (dB * seconds)

    @property
    def duration(self) -> float:
        return self.offset - self.onset


def _butter_bandpass(data: np.ndarray, lowcut: float, highcut: float, fs: int, order: int = 4) -> np.ndarray:
    """Apply a Butterworth bandpass filter."""
    sos = butter(order, [lowcut, highcut], btype="band", fs=fs, output="sos")
    return sosfilt(sos, data).astype(np.float32)


def load_audio(audio_path: str | Path) -> tuple[int, np.ndarray]:
    """
    Load a WAV audio file into float32 samples in [-1.0, 1.0].
    Handles mono and multi-channel audio safely without integer overflow.
    """
    path = Path(audio_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    sr, data = wavfile.read(str(path))

    # Convert to float32 in [-1.0, 1.0] depending on input dtype
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        data = data.astype(np.float32) / 2147483648.0
    elif data.dtype == np.uint8:
        data = (data.astype(np.float32) - 128.0) / 128.0
    elif np.issubdtype(data.dtype, np.floating):
        data = data.astype(np.float32)
    else:
        data = data.astype(np.float32)
        max_val = np.max(np.abs(data))
        if max_val > 0:
            data = data / max_val

    # Convert stereo/multichannel to mono by averaging channels
    if data.ndim > 1:
        data = np.mean(data, axis=1)

    return sr, data


def compute_envelope(
    audio_path: str | Path,
    config: Config | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float]:
    """
    Compute time-aligned smoothed dB envelope, adaptive rolling baseline, and rise_db.

    Returns:
        (times, smoothed_db, baseline_db, rise_db, total_duration_s)
    """
    cfg = config or Config()
    sr, y = load_audio(audio_path)

    total_duration_s = float(len(y)) / sr if sr > 0 else 0.0

    if len(y) == 0 or total_duration_s == 0.0:
        empty = np.array([], dtype=np.float32)
        return empty, empty, empty, empty, 0.0

    # Optional bandpass filter
    if cfg.bandpass_enabled and cfg.bandpass_low > 0 and cfg.bandpass_high < sr / 2:
        y = _butter_bandpass(y, cfg.bandpass_low, cfg.bandpass_high, sr)

    # 10 Hz sampling: frame_length (0.5s) and hop_length (0.1s)
    win_samples = max(1, int(round(cfg.frame_length_s * sr)))
    hop_samples = max(1, int(round(cfg.hop_length_s * sr)))

    # Vectorized moving mean of energy using uniform_filter1d
    y_sq = y.astype(np.float32) ** 2
    # Moving average across window
    mean_sq = scipy.ndimage.uniform_filter1d(y_sq, size=win_samples, mode="reflect")[::hop_samples]

    # Convert to RMS and then to dB
    rms = np.sqrt(np.maximum(mean_sq, 1e-12))
    envelope_db = np.maximum(20.0 * np.log10(rms), -100.0)

    # Smooth envelope over smooth_window_s (default 1.0s = 10 frames at 10 Hz)
    smooth_frames = max(1, int(round(cfg.smooth_window_s / cfg.hop_length_s)))
    smoothed_db = scipy.ndimage.uniform_filter1d(envelope_db, size=smooth_frames, mode="reflect")

    # Adaptive baseline: rolling median over baseline_window_s (default 90s)
    baseline_frames = int(round(cfg.baseline_window_s / cfg.hop_length_s))
    if len(smoothed_db) < baseline_frames:
        # For short audio (shorter than baseline window), adjust filter size gracefully
        baseline_frames = max(3, (len(smoothed_db) // 2) * 2 + 1)
    elif baseline_frames % 2 == 0:
        baseline_frames += 1

    baseline_db = scipy.ndimage.median_filter(smoothed_db, size=baseline_frames, mode="reflect")
    rise_db = smoothed_db - baseline_db

    times = np.arange(len(rise_db), dtype=np.float32) * cfg.hop_length_s
    return times, smoothed_db, baseline_db, rise_db, total_duration_s


def detect_spikes(
    audio_path: str | Path,
    config: Config | None = None,
    envelope: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float] | None = None,
) -> list[Spike]:
    """
    Detect candidate audio excitement spikes using an adaptive rolling baseline.

    Args:
        audio_path: Path to the WAV audio file.
        config: Configuration instance with hyperparameters.
        envelope: Optional precomputed (times, smoothed_db, baseline_db, rise_db, total_duration_s) tuple.

    Returns:
        List of Spike instances sorted chronologically by peak_time.
    """
    cfg = config or Config()
    logger.info("Detecting audio spikes in %s (min_rise=%.1fdB, min_sustain=%.1fs, skip_start=%.1fs)",
                Path(audio_path).name, cfg.min_rise_db, cfg.min_sustain_s, cfg.skip_start_s)

    if envelope is not None:
        times, smoothed_db, baseline_db, rise_db, total_duration_s = envelope
    else:
        times, smoothed_db, baseline_db, rise_db, total_duration_s = compute_envelope(audio_path, cfg)

    if len(times) == 0:
        logger.warning("Empty audio or zero duration: no spikes detected.")
        return []

    # Check for silent audio (signal never rises noticeably above floor)
    if np.max(smoothed_db) <= -90.0:
        logger.info("Audio appears to be completely silent. No spikes detected.")
        return []

    # Contiguous segments where rise_db >= min_rise_db
    above_threshold = rise_db >= cfg.min_rise_db
    labeled_segments, num_segments = scipy.ndimage.label(above_threshold)

    spikes: list[Spike] = []

    if num_segments == 0:
        logger.info("No segments found above %.1f dB rise.", cfg.min_rise_db)
        return spikes

    slices = scipy.ndimage.find_objects(labeled_segments)
    for sl in slices:
        if sl is None:
            continue
        idx = sl[0]
        segment_len_frames = idx.stop - idx.start
        duration_s = segment_len_frames * cfg.hop_length_s

        # Enforce minimum sustain duration
        if duration_s < cfg.min_sustain_s:
            continue

        onset = float(times[idx.start])
        offset = float(times[idx.stop - 1])
        segment_rise = rise_db[idx]

        peak_rel_idx = int(np.argmax(segment_rise))
        peak_time = float(times[idx.start + peak_rel_idx])
        peak_rise_db = float(segment_rise[peak_rel_idx])

        # Ignore segments during skip_start_s and skip_end_s
        if peak_time < cfg.skip_start_s:
            continue
        if cfg.skip_end_s > 0 and peak_time > (total_duration_s - cfg.skip_end_s):
            continue

        # Score = area above the floor threshold (dB * seconds)
        score = float(np.sum(segment_rise - cfg.min_rise_db) * cfg.hop_length_s)

        spikes.append(Spike(
            onset=round(onset, 2),
            offset=round(offset, 2),
            peak_time=round(peak_time, 2),
            peak_rise_db=round(peak_rise_db, 2),
            score=round(score, 2),
        ))

    # Sort spikes chronologically by peak_time
    spikes.sort(key=lambda s: s.peak_time)

    logger.info("Detected %d candidate spikes.", len(spikes))
    for i, spk in enumerate(spikes):
        logger.debug("[%d] Peak at %.2fs (%.2fs - %.2fs, dur=%.2fs): rise=%.1fdB, score=%.1f",
                     i + 1, spk.peak_time, spk.onset, spk.offset, spk.duration, spk.peak_rise_db, spk.score)

    return spikes


def detect_subthreshold_suggestions(
    audio_path: str | Path,
    config: Config | None = None,
    envelope: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float] | None = None,
    primary_windows: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Detect sub-threshold candidate excitement moments with min_rise_db - 1.5 and min_sustain_s - 1.0.
    Filters out candidates already covered by primary highlight windows.
    Returns sub-threshold candidates as suggestions.
    """
    from dataclasses import replace
    from spike_window import merge_spikes_into_windows, _format_hms

    cfg = config or Config()
    sens_rise = max(0.5, cfg.min_rise_db - 1.5)
    sens_sustain = max(0.5, cfg.min_sustain_s - 1.0)
    sens_cfg = replace(cfg, min_rise_db=sens_rise, min_sustain_s=sens_sustain, top_k=None, target_duration=0.0)

    if envelope is not None:
        times, smoothed_db, baseline_db, rise_db, total_duration_s = envelope
    else:
        times, smoothed_db, baseline_db, rise_db, total_duration_s = compute_envelope(audio_path, sens_cfg)

    sub_spikes = detect_spikes(audio_path, config=sens_cfg, envelope=(times, smoothed_db, baseline_db, rise_db, total_duration_s))
    if not sub_spikes:
        return []

    candidate_windows = merge_spikes_into_windows(sub_spikes, audio_duration=total_duration_s, config=sens_cfg)

    covered_windows = primary_windows or []
    suggestions: list[dict[str, Any]] = []

    for cand in candidate_windows:
        is_covered = False
        for pw in covered_windows:
            pw_start = pw.start if hasattr(pw, "start") else pw.get("start", 0.0)
            pw_end = pw.end if hasattr(pw, "end") else pw.get("end", 0.0)
            if max(cand.start, pw_start) < min(cand.end, pw_end):
                is_covered = True
                break

        if not is_covered:
            suggestions.append({
                "start": round(cand.start, 2),
                "end": round(cand.end, 2),
                "duration": cand.duration,
                "start_hms": _format_hms(cand.start),
                "end_hms": _format_hms(cand.end),
                "score": round(cand.score, 2),
                "peak_time": round(cand.peak_time, 2),
                "peak_time_hms": _format_hms(cand.peak_time),
                "peak_rise_db": round(cand.peak_rise_db, 2),
                "source": "suggestion",
                "spike_count": cand.spike_count,
            })

    suggestions.sort(key=lambda s: s["start"])
    return suggestions