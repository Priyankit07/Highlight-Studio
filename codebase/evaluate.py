"""
Evaluation and tuning sweep module.
Measures recall and precision against ground-truth event labels and performs hyperparameter sweeps.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path
from typing import Any

from config import Config
from spike_detection import compute_envelope, detect_spikes
from spike_window import merge_spikes_into_windows

logger = logging.getLogger("evaluate")


def parse_timestamp(val: str | float | int) -> float:
    """Parse timestamp from float, int, or MM:SS / HH:MM:SS string."""
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip()
    if ":" in val_str:
        parts = [float(p) for p in val_str.split(":")]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return float(val_str)


def load_ground_truth_labels(labels_file: str | Path | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """
    Load ground-truth event labels from CSV, JSON, or in-memory list of dicts.
    Gracefully returns empty list if file doesn't exist or is empty.
    """
    if not labels_file:
        return []

    if isinstance(labels_file, list):
        labels: list[dict[str, Any]] = []
        for item in labels_file:
            t = parse_timestamp(item.get("peak", item.get("start", item.get("time", 0.0))))
            ev_type = item.get("type", "event")
            if ev_type in {"jingle", "thump", "whistle", "distractor"}:
                continue
            labels.append({
                "time": t,
                "label": item.get("description", item.get("label", "Event")),
                "type": ev_type,
            })
        return labels

    p = Path(labels_file).resolve()
    if not p.exists() or p.stat().st_size == 0:
        logger.warning("Labels file '%s' not found or empty.", p)
        return []

    labels: list[dict[str, Any]] = []

    if p.suffix.lower() == ".json":
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data:
                t = parse_timestamp(item.get("peak", item.get("start", item.get("time", 0.0))))
                ev_type = item.get("type", "event")
                # Exclude explicit distractors if type is specified
                if ev_type in {"jingle", "thump", "whistle"}:
                    continue
                labels.append({
                    "time": t,
                    "label": item.get("description", item.get("label", "Event")),
                    "type": ev_type,
                })
        return labels

    # Read CSV
    with open(p, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            time_col = None
            for key in ("time", "timestamp", "start", "peak", "seconds"):
                if key in row and row[key]:
                    time_col = row[key]
                    break
            if time_col is None:
                continue

            t = parse_timestamp(time_col)
            ev_type = row.get("type", "event").strip().lower()
            desc = row.get("label", row.get("description", "Event"))

            # Filter out non-highlight distractor types
            if ev_type in {"jingle", "thump", "whistle", "distractor"}:
                continue

            labels.append({
                "time": t,
                "label": desc,
                "type": ev_type,
            })

    return labels


def load_manifest_windows(manifest_path: str | Path) -> list[dict[str, Any]]:
    """Load windows from windows.json or windows.csv."""
    p = Path(manifest_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Manifest file not found: {p}")

    if p.suffix.lower() == ".json":
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    # Read CSV
    windows = []
    with open(p, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            windows.append({
                "start": float(row["start"]),
                "end": float(row["end"]),
                "duration": float(row["duration"]),
                "score": float(row["score"]),
                "peak_time": float(row.get("peak_time", row["start"])),
                "selected": row.get("selected", "True").strip().lower() in {"true", "1", "yes"},
            })
    return windows


def evaluate_manifest(
    manifest_path: str | Path | list[dict[str, Any]],
    labels_path: str | Path | list[dict[str, Any]] | None,
    tolerance_s: float = 3.0,
) -> dict[str, Any]:
    """
    Evaluate detected highlight windows against ground truth labels.

    Returns dict with recall, precision, f1, reel_duration_s, covered_events, false_positives.
    """
    if isinstance(manifest_path, list):
        windows = manifest_path
    else:
        windows = load_manifest_windows(manifest_path)
    labels = load_ground_truth_labels(labels_path)

    selected_windows = [w for w in windows if w.get("selected", True)]
    reel_duration = sum(w.get("duration", w["end"] - w["start"]) for w in selected_windows)

    if not labels:
        return {
            "num_ground_truth": 0,
            "num_selected_windows": len(selected_windows),
            "reel_duration_s": round(reel_duration, 2),
            "recall": 0.0,
            "precision": 0.0,
            "f1": 0.0,
            "covered_events": [],
            "missed_events": [],
        }

    # Measure recall: labelled events covered by at least one selected window
    covered = []
    missed = []
    for lbl in labels:
        t = lbl["time"]
        matched_window = None
        for w in selected_windows:
            if (w["start"] - tolerance_s) <= t <= (w["end"] + tolerance_s):
                matched_window = w
                break
        if matched_window is not None:
            covered.append({"label": lbl, "window": matched_window})
        else:
            missed.append(lbl)

    recall = len(covered) / len(labels) if labels else 0.0

    # Measure precision: selected windows that contain at least one labelled event
    true_positive_windows = 0
    for w in selected_windows:
        has_match = any((w["start"] - tolerance_s) <= lbl["time"] <= (w["end"] + tolerance_s) for lbl in labels)
        if has_match:
            true_positive_windows += 1

    precision = true_positive_windows / len(selected_windows) if selected_windows else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "num_ground_truth": len(labels),
        "num_selected_windows": len(selected_windows),
        "num_covered": len(covered),
        "num_missed": len(missed),
        "reel_duration_s": round(reel_duration, 2),
        "recall": round(recall, 4),
        "precision": round(precision, 4),
        "f1": round(f1, 4),
        "covered_events": covered,
        "missed_events": missed,
    }


def run_parameter_sweep(
    audio_path: str | Path,
    labels_path: str | Path | list[dict[str, Any]],
    rise_db_values: list[float] | None = None,
    sustain_values: list[float] | None = None,
    pre_roll_values: list[float] | None = None,
) -> list[dict[str, Any]]:
    """
    Grid search over detection hyperparameters and return ranked results.
    """
    rise_grid = rise_db_values or [3.0, 4.0, 5.0, 6.0]
    sustain_grid = sustain_values or [2.0, 3.0, 4.0]
    pre_roll_grid = pre_roll_values or [8.0, 12.0, 16.0]

    labels = load_ground_truth_labels(labels_path)
    if not labels:
        raise ValueError("Cannot perform parameter sweep without valid ground-truth labels.")

    results = []
    base_cfg = Config()
    env_tuple = compute_envelope(audio_path, base_cfg)
    audio_duration = env_tuple[4]

    print(f"\n🔍 Running parameter sweep ({len(rise_grid) * len(sustain_grid) * len(pre_roll_grid)} combinations)...")

    for rise in rise_grid:
        for sustain in sustain_grid:
            for pre in pre_roll_grid:
                cfg = Config(min_rise_db=rise, min_sustain_s=sustain, pre_roll=pre)
                spikes = detect_spikes(audio_path, config=cfg, envelope=env_tuple)
                windows = merge_spikes_into_windows(spikes, audio_duration=audio_duration, config=cfg)

                selected = [w for w in windows if w.selected]
                reel_dur = sum(w.duration for w in selected)

                covered_count = 0
                for lbl in labels:
                    if any((w.start - 3.0) <= lbl["time"] <= (w.end + 3.0) for w in selected):
                        covered_count += 1
                rec = covered_count / len(labels) if labels else 0.0

                tp_wins = sum(1 for w in selected if any((w.start - 3.0) <= lbl["time"] <= (w.end + 3.0) for lbl in labels))
                prec = tp_wins / len(selected) if selected else 0.0
                f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0

                results.append({
                    "min_rise_db": rise,
                    "min_sustain_s": sustain,
                    "pre_roll": pre,
                    "windows": len(selected),
                    "reel_duration_s": round(reel_dur, 1),
                    "recall": round(rec, 3),
                    "precision": round(prec, 3),
                    "f1": round(f1, 3),
                })

    # Sort results by F1 descending, then recall descending, then reel_duration ascending
    results.sort(key=lambda r: (r["f1"], r["recall"], -abs(r["reel_duration_s"] - 120.0)), reverse=True)
    return results


def print_evaluation_summary(metrics: dict[str, Any]) -> None:
    """Print clean formatted evaluation report."""
    print("\n" + "=" * 60)
    print("📊 HIGHLIGHT GENERATOR EVALUATION REPORT")
    print("=" * 60)
    print(f"Ground-Truth Events:     {metrics['num_ground_truth']}")
    print(f"Selected Windows:        {metrics['num_selected_windows']}")
    print(f"Covered Events (Recall): {metrics['num_covered']} / {metrics['num_ground_truth']} ({metrics['recall'] * 100:.1f}%)")
    print(f"Window Precision:        {metrics['precision'] * 100:.1f}%")
    print(f"F1 Score:                {metrics['f1']:.3f}")
    print(f"Reel Duration:           {metrics['reel_duration_s']:.1f} seconds")
    if metrics["missed_events"]:
        print("\n⚠️ Missed Events:")
        for m in metrics["missed_events"]:
            print(f"  - {m['label']} at {m['time']:.1f}s")
    print("=" * 60 + "\n")


def print_sweep_table(sweep_results: list[dict[str, Any]]) -> None:
    """Print ranked markdown table for parameter sweep."""
    print("\n" + "=" * 80)
    print("🏆 PARAMETER SWEEP RANKINGS (Top 10)")
    print("=" * 80)
    header = f"{'Rank':<5} | {'Rise (dB)':<10} | {'Sustain (s)':<11} | {'Pre-roll (s)':<12} | {'Clips':<6} | {'Reel (s)':<9} | {'Recall':<7} | {'Precision':<10} | {'F1':<6}"
    print(header)
    print("-" * len(header))
    for i, r in enumerate(sweep_results[:10]):
        row = f"{i+1:<5} | {r['min_rise_db']:<10.1f} | {r['min_sustain_s']:<11.1f} | {r['pre_roll']:<12.1f} | {r['windows']:<6} | {r['reel_duration_s']:<9.1f} | {r['recall']*100:<6.1f}% | {r['precision']*100:<9.1f}% | {r['f1']:<6.3f}"
        print(row)
    print("=" * 80 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate highlight generator manifest against ground truth labels.")
    parser.add_argument("--manifest", type=str, default="output video/synthetic_match/windows.json", help="Path to windows.json/csv")
    parser.add_argument("--labels", type=str, default="tools/synthetic_events.csv", help="Path to ground truth labels CSV/JSON")
    parser.add_argument("--sweep", action="store_true", help="Perform hyperparameter grid search")
    parser.add_argument("--audio", type=str, default="audio output/synthetic_match.wav", help="Audio file for sweep")
    args = parser.parse_args()

    if args.sweep:
        audio_p = Path(args.audio)
        if not audio_p.exists():
            audio_p = Path("tools/synthetic_match.wav")
        results = run_parameter_sweep(audio_p, args.labels)
        print_sweep_table(results)
    else:
        manifest_p = Path(args.manifest)
        if not manifest_p.exists():
            print(f"Manifest not found: {manifest_p}. Run the pipeline first or provide --manifest.")
            return
        metrics = evaluate_manifest(manifest_p, args.labels)
        print_evaluation_summary(metrics)


if __name__ == "__main__":
    main()
