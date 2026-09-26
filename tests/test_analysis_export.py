"""
Tests for analysis_export: downsampling and JSON export.
"""
from pathlib import Path
import json
import numpy as np
import pytest

from analysis_export import downsample_envelope, export_analysis
from config import Config
from spike_detection import Spike
from spike_window import Window


def test_downsample_envelope_under_threshold():
    times = np.linspace(0, 100, 500)
    db = np.random.uniform(-60, -10, 500)
    baseline = np.random.uniform(-60, -20, 500)
    rise = db - baseline

    res = downsample_envelope(times, db, baseline, rise, max_points=3000)
    assert len(res["t"]) == 500
    assert len(res["db"]) == 500
    assert len(res["baseline"]) == 500
    assert len(res["rise"]) == 500


def test_downsample_envelope_max_pooling_preserves_peaks():
    n = 10000
    times = np.linspace(0, 1000, n)
    db = np.zeros(n)
    baseline = np.zeros(n)
    rise = np.zeros(n)

    # Insert a major excitement peak at index 5000
    rise[5000] = 25.5
    db[5000] = -5.0

    res = downsample_envelope(times, db, baseline, rise, max_points=1000)
    assert len(res["t"]) <= 1000
    # Peak must be preserved
    assert max(res["rise"]) == pytest.approx(25.5, abs=0.1)


def test_export_analysis(tmp_path: Path):
    times = np.arange(10, dtype=float)
    db = np.ones(10) * -20.0
    baseline = np.ones(10) * -30.0
    rise = db - baseline
    spikes = [Spike(onset=2.0, offset=5.0, peak_time=3.5, peak_rise_db=10.0, score=25.0)]
    windows = [Window(start=1.0, end=6.0, score=25.0, peak_time=3.5, selected=True)]

    env_path, ana_path = export_analysis(
        output_dir=tmp_path,
        times=times,
        smoothed_db=db,
        baseline_db=baseline,
        rise_db=rise,
        total_duration_s=10.0,
        spikes=spikes,
        windows=windows,
        config=Config(),
    )

    assert env_path.exists()
    assert ana_path.exists()

    with open(env_path) as f:
        env_data = json.load(f)
    assert "t" in env_data
    assert "db" in env_data
    assert "baseline" in env_data
    assert "rise" in env_data

    with open(ana_path) as f:
        ana_data = json.load(f)
    assert ana_data["duration_s"] == 10.0
    assert len(ana_data["spikes"]) == 1
    assert len(ana_data["windows"]) == 1
    assert ana_data["windows"][0]["selected"] is True
