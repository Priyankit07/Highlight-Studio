"""
Analysis export module.
Serializes envelope data (downsampled via max-pooling) and analysis metadata into JSON for web consumption.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

from config import Config
from spike_detection import Spike
from spike_window import Window

logger = logging.getLogger(__name__)


def downsample_envelope(
    times: np.ndarray,
    smoothed_db: np.ndarray,
    baseline_db: np.ndarray,
    rise_db: np.ndarray,
    max_points: int = 3000,
) -> dict[str, list[float]]:
    """
    Downsample envelope arrays to <= max_points using max-pooling per bin
    on rise_db so that excitement peaks are strictly preserved.

    Returns:
        Dict with keys: "t", "db", "baseline", "rise"
    """
    n = len(times)
    if n == 0:
        return {"t": [], "db": [], "baseline": [], "rise": []}

    if n <= max_points:
        return {
            "t": [round(float(v), 2) for v in times],
            "db": [round(float(v), 2) for v in smoothed_db],
            "baseline": [round(float(v), 2) for v in baseline_db],
            "rise": [round(float(v), 2) for v in rise_db],
        }

    # Binning to max_points bins
    num_bins = max_points
    bin_size = n / float(num_bins)

    sampled_t: list[float] = []
    sampled_db: list[float] = []
    sampled_baseline: list[float] = []
    sampled_rise: list[float] = []

    for i in range(num_bins):
        start_idx = int(round(i * bin_size))
        end_idx = int(round((i + 1) * bin_size))
        if start_idx >= n:
            break
        end_idx = max(start_idx + 1, min(n, end_idx))

        slice_rise = rise_db[start_idx:end_idx]
        peak_rel = int(np.argmax(slice_rise))
        best_idx = start_idx + peak_rel

        sampled_t.append(round(float(times[best_idx]), 2))
        sampled_db.append(round(float(smoothed_db[best_idx]), 2))
        sampled_baseline.append(round(float(baseline_db[best_idx]), 2))
        sampled_rise.append(round(float(rise_db[best_idx]), 2))

    return {
        "t": sampled_t,
        "db": sampled_db,
        "baseline": sampled_baseline,
        "rise": sampled_rise,
    }


def export_analysis(
    output_dir: str | Path,
    times: np.ndarray,
    smoothed_db: np.ndarray,
    baseline_db: np.ndarray,
    rise_db: np.ndarray,
    total_duration_s: float,
    spikes: list[Spike],
    windows: list[Window],
    config: Config | None = None,
    max_envelope_points: int = 3000,
    suggestions: list[dict[str, Any]] | None = None,
) -> tuple[Path, Path]:
    """
    Write envelope.json and analysis.json to output_dir.

    Args:
        output_dir: Target directory for JSON files.
        times: Time array in seconds.
        smoothed_db: Smoothed dB envelope.
        baseline_db: Baseline dB.
        rise_db: Rise above baseline dB.
        total_duration_s: Total audio duration in seconds.
        spikes: Detected Spike candidates.
        windows: Generated highlight Window instances.
        config: Configuration instance.
        max_envelope_points: Maximum points in exported envelope (default 3000).
        suggestions: Optional sub-threshold candidate suggestions list.

    Returns:
        (envelope_json_path, analysis_json_path)
    """
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    cfg = config or Config()

    envelope_path = out / "envelope.json"
    analysis_path = out / "analysis.json"

    # 1. Downsampled envelope
    envelope_data = downsample_envelope(
        times=times,
        smoothed_db=smoothed_db,
        baseline_db=baseline_db,
        rise_db=rise_db,
        max_points=max_envelope_points,
    )

    with open(envelope_path, "w", encoding="utf-8") as f:
        json.dump(envelope_data, f)

    # 2. Complete analysis metadata
    spikes_data = [
        {
            "onset": round(s.onset, 2),
            "offset": round(s.offset, 2),
            "peak_time": round(s.peak_time, 2),
            "peak_rise_db": round(s.peak_rise_db, 2),
            "score": round(s.score, 2),
            "duration": round(s.duration, 2),
        }
        for s in spikes
    ]

    windows_data = [w.to_dict() for w in windows]
    config_data = cfg.to_dict() if hasattr(cfg, "to_dict") else {}

    analysis_data = {
        "duration_s": round(total_duration_s, 2),
        "spikes": spikes_data,
        "windows": windows_data,
        "suggestions": suggestions or [],
        "config": config_data,
    }

    with open(analysis_path, "w", encoding="utf-8") as f:
        json.dump(analysis_data, f, indent=2)

    logger.info("Exported analysis JSONs: %s, %s", envelope_path.name, analysis_path.name)
    return envelope_path, analysis_path
