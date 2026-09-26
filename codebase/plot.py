"""
Debug plotting module.
Generates comprehensive visualization of audio envelope, adaptive baseline, rise_db,
candidate spikes, and selected highlight windows using matplotlib's Agg backend.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from config import Config
from spike_detection import Spike
from spike_window import Window

logger = logging.getLogger(__name__)


def generate_debug_plot(
    plot_path: str | Path,
    times: np.ndarray,
    smoothed_db: np.ndarray,
    baseline_db: np.ndarray,
    rise_db: np.ndarray,
    spikes: list[Spike],
    windows: list[Window],
    config: Config | None = None,
    title: str = "Football Match Audio Excitement Analysis",
) -> Path:
    """
    Generate and save a 2-panel debug visualization plot of the audio analysis.

    Args:
        plot_path: Destination path for the generated PNG.
        times: Time array in seconds.
        smoothed_db: Smoothed dB envelope array.
        baseline_db: Rolling median baseline dB array.
        rise_db: Envelope rise above baseline dB.
        spikes: Detected Spike candidates.
        windows: Generated highlight Window objects.
        config: Configuration instance.
        title: Plot title.

    Returns:
        Path to saved PNG file.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cfg = config or Config()
    out_file = Path(plot_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    fig.patch.set_facecolor("#121417")

    for ax in (ax1, ax2):
        ax.set_facecolor("#1a1d23")
        ax.tick_params(colors="#e0e0e0", which="both")
        for spine in ax.spines.values():
            spine.set_color("#333945")
        ax.grid(True, color="#2b313d", linestyle="--", alpha=0.7)

    # ---------------- Top Panel: dB Envelope & Baseline ---------------- #
    ax1.set_title(title, color="#ffffff", fontsize=14, fontweight="bold", pad=12)
    ax1.plot(times, smoothed_db, color="#38bdf8", linewidth=1.2, label="dB Envelope (smoothed 1s)", alpha=0.85)
    ax1.plot(times, baseline_db, color="#f59e0b", linewidth=1.5, linestyle="--", label=f"Adaptive Baseline ({cfg.baseline_window_s:.0f}s median)")

    # Skip start region
    if cfg.skip_start_s > 0:
        ax1.axvspan(0, cfg.skip_start_s, color="#ef4444", alpha=0.15, label=f"Skip Start ({cfg.skip_start_s:.0f}s)")
        ax2.axvspan(0, cfg.skip_start_s, color="#ef4444", alpha=0.15)

    # Shaded windows
    for w in windows:
        if w.selected:
            ax1.axvspan(w.start, w.end, color="#10b981", alpha=0.25, label="Selected Window" if "Selected Window" not in ax1.get_legend_handles_labels()[1] else "")
            ax2.axvspan(w.start, w.end, color="#10b981", alpha=0.25)
        else:
            ax1.axvspan(w.start, w.end, color="#64748b", alpha=0.20, label="Unselected Candidate" if "Unselected Candidate" not in ax1.get_legend_handles_labels()[1] else "")
            ax2.axvspan(w.start, w.end, color="#64748b", alpha=0.20)

    # Mark detected spikes
    for s in spikes:
        ax1.scatter([s.peak_time], [s.peak_rise_db + baseline_db[int(s.peak_time / cfg.hop_length_s)] if int(s.peak_time / cfg.hop_length_s) < len(baseline_db) else 0],
                    color="#f43f5e", s=40, zorder=5)

    ax1.set_ylabel("Audio Level (dB)", color="#e0e0e0", fontsize=11)
    ax1.legend(loc="upper right", facecolor="#1e222b", edgecolor="#333945", labelcolor="#e0e0e0", fontsize=9)

    # ---------------- Bottom Panel: Rise Above Baseline & Candidates ---------------- #
    ax2.plot(times, rise_db, color="#a855f7", linewidth=1.2, label="Rise = Envelope - Baseline (dB)")
    ax2.axhline(cfg.min_rise_db, color="#f43f5e", linestyle=":", linewidth=1.5, label=f"Threshold (min_rise = {cfg.min_rise_db:.1f} dB)")

    # Mark peaks on bottom panel
    for i, s in enumerate(spikes):
        ax2.scatter([s.peak_time], [s.peak_rise_db], color="#f43f5e", s=50, zorder=5)
        ax2.annotate(
            f"#{i+1}: {s.peak_rise_db:.1f}dB\n(score={s.score:.1f})",
            (s.peak_time, s.peak_rise_db),
            textcoords="offset points",
            xytext=(0, 10),
            ha="center",
            fontsize=8,
            color="#f1f5f9",
            bbox=dict(boxstyle="round,pad=0.2", fc="#0f172a", ec="#38bdf8", alpha=0.85),
        )

    ax2.set_xlabel("Time (seconds)", color="#e0e0e0", fontsize=11)
    ax2.set_ylabel("Rise Above Baseline (dB)", color="#e0e0e0", fontsize=11)
    ax2.legend(loc="upper right", facecolor="#1e222b", edgecolor="#333945", labelcolor="#e0e0e0", fontsize=9)

    plt.tight_layout()
    plt.savefig(str(out_file), dpi=150, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)

    logger.info("Saved debug plot: %s", out_file)
    return out_file
