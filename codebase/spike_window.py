"""
Spike window creation, merging, selection, and manifest export.
Expands candidate spikes by pre_roll/post_roll, merges nearby windows, enforces min/max clip constraints,
greedily selects highlight windows according to budget, and writes manifests (JSON + CSV).
"""
from __future__ import annotations

import csv
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from config import Config
from spike_detection import Spike

logger = logging.getLogger(__name__)


def _format_hms(seconds: float) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    secs = max(0.0, seconds)
    hrs = int(secs // 3600)
    mins = int((secs % 3600) // 60)
    s = secs % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{s:05.2f}"
    return f"{mins:02d}:{s:05.2f}"


@dataclass
class Window:
    """Represents a video highlight window."""
    start: float          # Start timestamp in seconds
    end: float            # End timestamp in seconds
    score: float          # Highlight excitement score
    peak_time: float      # Peak audio timestamp within window
    spike_count: int = 1  # Number of candidate spikes merged into this window
    selected: bool = False  # Whether selected in the highlights reel
    source: str = "auto"  # "auto" | "manual" | "suggestion"
    drop_reason: str | None = None  # "over_length_cap" | "top_k" | "below_min_score" | None
    peak_rise_db: float = 0.0  # Maximum rise above baseline in window (dB)
    original_start: float | None = None  # Full uncropped start if merged/cropped
    original_end: float | None = None    # Full uncropped end if merged/cropped
    is_cropped: bool = False  # True if window was cropped to max_clip_s

    @property
    def duration(self) -> float:
        return round(max(0.0, self.end - self.start), 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": round(self.start, 2),
            "end": round(self.end, 2),
            "duration": self.duration,
            "start_hms": _format_hms(self.start),
            "end_hms": _format_hms(self.end),
            "score": round(self.score, 2),
            "peak_time": round(self.peak_time, 2),
            "peak_time_hms": _format_hms(self.peak_time),
            "spike_count": self.spike_count,
            "selected": self.selected,
            "source": self.source,
            "drop_reason": self.drop_reason,
            "peak_rise_db": round(self.peak_rise_db, 2),
            "original_start": round(self.original_start, 2) if self.original_start is not None else None,
            "original_end": round(self.original_end, 2) if self.original_end is not None else None,
            "is_cropped": self.is_cropped,
        }


def merge_spikes_into_windows(
    spikes: list[Spike] | list[float],
    audio_duration: float = 0.0,
    config: Config | None = None,
    window_gap: float | None = None,
) -> list[Window]:
    """
    Convert candidate spikes into merged, ranked, and selected highlight windows.

    Args:
        spikes: List of Spike objects (or legacy list of float timestamps).
        audio_duration: Total audio length in seconds (for boundary clamping).
        config: Configuration instance.
        window_gap: Legacy parameter override for merge_gap.

    Returns:
        List of Window instances sorted chronologically.
    """
    cfg = config or Config()
    merge_gap = window_gap if window_gap is not None else cfg.merge_gap

    if not spikes:
        logger.info("No spikes provided to window generator.")
        return []

    # 1. Normalize input spikes (handle legacy list of floats)
    normalized_spikes: list[Spike] = []
    for item in spikes:
        if isinstance(item, Spike):
            normalized_spikes.append(item)
        elif isinstance(item, (int, float)):
            t = float(item)
            normalized_spikes.append(Spike(onset=t, offset=t, peak_time=t, peak_rise_db=0.0, score=1.0))

    # 2. Expand FIRST: [onset - pre_roll, offset + post_roll], clamped to bounds
    expanded_windows: list[Window] = []
    for spk in normalized_spikes:
        w_start = max(0.0, spk.onset - cfg.pre_roll)
        w_end = spk.offset + cfg.post_roll
        if audio_duration > 0:
            w_end = min(audio_duration, w_end)

        expanded_windows.append(Window(
            start=round(w_start, 2),
            end=round(w_end, 2),
            score=spk.score,
            peak_time=spk.peak_time,
            spike_count=1,
            selected=False,
            source="auto",
            drop_reason=None,
            peak_rise_db=spk.peak_rise_db,
            original_start=round(w_start, 2),
            original_end=round(w_end, 2),
            is_cropped=False,
        ))

    # Sort expanded windows by start time
    expanded_windows.sort(key=lambda w: w.start)

    # 3. Merge AFTER expanding: windows that overlap or sit within merge_gap become one
    merged_windows: list[Window] = []
    for w in expanded_windows:
        if not merged_windows:
            merged_windows.append(w)
            continue

        prev = merged_windows[-1]
        if w.start - prev.end <= merge_gap:
            # Merge windows: extend end boundary, accumulate count, take max score
            prev.end = max(prev.end, w.end)
            prev.original_end = max(prev.original_end if prev.original_end is not None else prev.end, w.original_end if w.original_end is not None else w.end)
            prev.original_start = min(prev.original_start if prev.original_start is not None else prev.start, w.original_start if w.original_start is not None else w.start)
            if w.score > prev.score:
                prev.peak_time = w.peak_time
            prev.score = max(prev.score, w.score)
            prev.peak_rise_db = max(prev.peak_rise_db, w.peak_rise_db)
            prev.spike_count += w.spike_count
        else:
            merged_windows.append(w)

    # 4. Enforce min_clip_s and max_clip_s constraints
    for w in merged_windows:
        cur_dur = w.duration
        if cur_dur < cfg.min_clip_s:
            # Expand symmetrically around center
            needed = cfg.min_clip_s - cur_dur
            pad = needed / 2.0
            new_start = max(0.0, w.start - pad)
            new_end = new_start + cfg.min_clip_s
            if audio_duration > 0 and new_end > audio_duration:
                new_end = audio_duration
                new_start = max(0.0, new_end - cfg.min_clip_s)
            w.start = round(new_start, 2)
            w.end = round(new_end, 2)

        elif cur_dur > cfg.max_clip_s:
            # Record pre-cropped span before trimming to max_clip_s
            w.original_start = w.start
            w.original_end = w.end
            w.is_cropped = True

            # Keep the portion around peak_time
            half_win = cfg.max_clip_s / 2.0
            tentative_start = w.peak_time - half_win
            tentative_end = w.peak_time + half_win

            if tentative_start < w.start:
                tentative_start = w.start
                tentative_end = min(w.end, tentative_start + cfg.max_clip_s)
            elif tentative_end > w.end:
                tentative_end = w.end
                tentative_start = max(w.start, tentative_end - cfg.max_clip_s)

            w.start = round(max(0.0, tentative_start), 2)
            w.end = round(tentative_end if audio_duration <= 0 else min(audio_duration, tentative_end), 2)

    # Re-verify and resolve any overlapping windows after min_clip expansion
    resolved_windows: list[Window] = []
    for w in merged_windows:
        if not resolved_windows:
            resolved_windows.append(w)
            continue
        prev = resolved_windows[-1]
        if w.start < prev.end:
            # Clamp or merge overlap
            prev.end = max(prev.end, w.end)
            prev.original_end = max(prev.original_end if prev.original_end is not None else prev.end, w.original_end if w.original_end is not None else w.end)
            prev.original_start = min(prev.original_start if prev.original_start is not None else prev.start, w.original_start if w.original_start is not None else w.start)
            if w.score > prev.score:
                prev.peak_time = w.peak_time
            prev.score = max(prev.score, w.score)
            prev.peak_rise_db = max(prev.peak_rise_db, w.peak_rise_db)
            prev.spike_count += w.spike_count
        else:
            resolved_windows.append(w)

    # Apply score_mode ranking
    if cfg.score_mode == "peak":
        for w in resolved_windows:
            w.score = round(w.peak_rise_db, 2)
    elif cfg.score_mode == "blend":
        max_area = max((w.score for w in resolved_windows), default=1.0)
        max_peak = max((w.peak_rise_db for w in resolved_windows), default=1.0)
        for w in resolved_windows:
            norm_area = (w.score / max_area) if max_area > 0 else 0.0
            norm_peak = (w.peak_rise_db / max_peak) if max_peak > 0 else 0.0
            w.score = round((0.5 * norm_area + 0.5 * norm_peak) * 100.0, 2)

    # 5. Greedy Selection by score with drop_reason tracking
    # Filter candidates by min_score if set
    eligible: list[Window] = []
    for w in resolved_windows:
        if cfg.min_score is not None and w.score < cfg.min_score:
            w.selected = False
            w.drop_reason = "below_min_score"
        else:
            eligible.append(w)

    ranked = sorted(eligible, key=lambda w: w.score, reverse=True)

    accumulated_dur = 0.0
    selected_count = 0

    for w in ranked:
        if cfg.top_k is not None and selected_count >= cfg.top_k:
            w.selected = False
            w.drop_reason = "top_k"
            continue

        if cfg.target_duration <= 0:
            # Keep all
            w.selected = True
            w.drop_reason = None
            accumulated_dur += w.duration
            selected_count += 1
        elif (accumulated_dur + w.duration <= cfg.target_duration) or selected_count == 0:
            w.selected = True
            w.drop_reason = None
            accumulated_dur += w.duration
            selected_count += 1
        else:
            w.selected = False
            w.drop_reason = "over_length_cap"

    # Return all windows sorted chronologically
    resolved_windows.sort(key=lambda w: w.start)

    selected_windows = [w for w in resolved_windows if w.selected]
    logger.info("Generated %d candidate windows; selected %d windows (total duration: %.1fs / target: %.1fs)",
                len(resolved_windows), len(selected_windows), accumulated_dur, cfg.target_duration)

    return resolved_windows


def save_manifest(windows: list[Window], output_path: str | Path) -> tuple[Path, Path]:
    """
    Save the candidate windows manifest to both JSON and CSV files.

    Args:
        windows: List of Window instances.
        output_path: Path to target file (e.g. windows.json or directory).

    Returns:
        (json_path, csv_path)
    """
    out = Path(output_path).resolve()
    if out.is_dir() or out.suffix == "":
        out.mkdir(parents=True, exist_ok=True)
        json_path = out / "windows.json"
        csv_path = out / "windows.csv"
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        json_path = out.with_suffix(".json")
        csv_path = out.with_suffix(".csv")

    # 1. Save JSON
    data = [w.to_dict() for w in windows]
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.info("Saved windows JSON manifest: %s", json_path)

    # 2. Save CSV
    fieldnames = [
        "start", "end", "duration", "start_hms", "end_hms",
        "score", "peak_time", "peak_time_hms", "spike_count", "selected",
        "source", "drop_reason", "peak_rise_db", "original_start", "original_end", "is_cropped"
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for w in windows:
            writer.writerow(w.to_dict())
    logger.info("Saved windows CSV manifest: %s", csv_path)

    return json_path, csv_path
