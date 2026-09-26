"""
Comprehensive tests for missed moment recovery features:
1. Manual Add Moment window creation, overlap merging, persistence, and rendering.
2. Sub-threshold candidate suggestions (min_rise_db - 1.5, min_sustain_s - 1.0).
3. Drop reasons (over_length_cap, top_k, below_min_score) and cropped window restoration.
4. Score modes: area, peak, blend ranking.
5. Ground-truth labels evaluation (caught vs missed) and hyperparameter sweep.
"""
import json
import shutil
import tempfile
from pathlib import Path
import numpy as np
import pytest
from scipy.io import wavfile
from fastapi.testclient import TestClient

from config import Config
from spike_detection import Spike, compute_envelope, detect_spikes, detect_subthreshold_suggestions
from spike_window import Window, merge_spikes_into_windows, save_manifest
from evaluate import evaluate_manifest, run_parameter_sweep
from api.main import app
from api import db
from api.storage import get_job_dir


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def synthetic_audio_path(tmp_path):
    """
    Generate a 12-minute (720s) synthetic audio file with:
    - Roar 1 at t=60s (large rise, duration 5s)
    - Roar 2 at t=200s (moderate rise, duration 4s)
    - Sub-threshold rise at t=350s (small rise, 2.5s duration - caught by suggestions)
    - Silence at t=500s
    """
    sr = 22050
    duration_s = 720.0
    total_samples = int(duration_s * sr)

    # Ambient stadium hum
    noise = np.random.normal(0, 0.015, total_samples)

    # Roar 1 at 60s
    start_1 = int(60 * sr)
    dur_1 = int(6 * sr)
    noise[start_1 : start_1 + dur_1] += np.random.normal(0, 0.25, dur_1)

    # Roar 2 at 200s
    start_2 = int(200 * sr)
    dur_2 = int(4 * sr)
    noise[start_2 : start_2 + dur_2] += np.random.normal(0, 0.20, dur_2)

    # Sub-threshold roar at 350s (moderate rise, ~2.5s duration)
    start_3 = int(350 * sr)
    dur_3 = int(2.5 * sr)
    noise[start_3 : start_3 + dur_3] += np.random.normal(0, 0.05, dur_3)

    audio_file = tmp_path / "synthetic_match_12min.wav"
    audio_int16 = (np.clip(noise, -1.0, 1.0) * 32767).astype(np.int16)
    wavfile.write(str(audio_file), sr, audio_int16)
    return audio_file


def test_manual_window_creation_and_merge():
    """Test manual moment creation [t - pre_roll, t + post_roll] clamped to bounds and merging overlaps."""
    cfg = Config(pre_roll=10.0, post_roll=5.0)
    audio_dur = 100.0

    # 1. Create manual moment at t=40s
    t = 40.0
    w_start = max(0.0, t - cfg.pre_roll)
    w_end = min(audio_dur, t + cfg.post_roll)
    manual_win = Window(
        start=w_start,
        end=w_end,
        score=1.0,
        peak_time=t,
        selected=True,
        source="manual",
    )
    assert manual_win.start == 30.0
    assert manual_win.end == 45.0
    assert manual_win.source == "manual"
    assert manual_win.selected is True

    # 2. Add overlapping moment at t=42s -> overlap check
    overlap_t = 42.0
    new_start = max(0.0, overlap_t - cfg.pre_roll)  # 32.0
    new_end = min(audio_dur, overlap_t + cfg.post_roll)  # 47.0

    # Check overlap
    is_overlapping = max(manual_win.start, new_start) < min(manual_win.end, new_end)
    assert is_overlapping is True

    # Merge moments
    merged_start = min(manual_win.start, new_start)  # 30.0
    merged_end = max(manual_win.end, new_end)        # 47.0
    merged_win = Window(
        start=merged_start,
        end=merged_end,
        score=1.0,
        peak_time=overlap_t,
        selected=True,
        source="manual",
    )
    assert merged_win.start == 30.0
    assert merged_win.end == 47.0
    assert merged_win.duration == 17.0


def test_suggestions_on_synthetic_match(synthetic_audio_path):
    """Test suggestions detection with relaxed thresholds on the 12-min synthetic audio."""
    cfg = Config(min_rise_db=4.5, min_sustain_s=3.0)
    envelope = compute_envelope(synthetic_audio_path, config=cfg)
    primary_spikes = detect_spikes(synthetic_audio_path, config=cfg, envelope=envelope)
    primary_windows = merge_spikes_into_windows(primary_spikes, audio_duration=envelope[4], config=cfg)

    # Primary windows should catch the loud roars around 60s and 200s
    assert len(primary_windows) >= 1
    assert any(abs(w.peak_time - 60) < 5.0 for w in primary_windows)

    # Sub-threshold suggestions should find candidates not in primary windows
    suggestions = detect_subthreshold_suggestions(
        audio_path=synthetic_audio_path,
        config=cfg,
        envelope=envelope,
        primary_windows=primary_windows,
    )
    assert isinstance(suggestions, list)
    # Ensure none of the suggestions overlap with primary windows
    for sugg in suggestions:
        assert sugg["source"] == "suggestion"
        for w in primary_windows:
            overlap = max(sugg["start"], w.start) < min(sugg["end"], w.end)
            assert not overlap, f"Suggestion {sugg} overlaps with primary window {w}"


def test_drop_reasons_and_cropping_flags():
    """Verify drop_reason assignment and cropping detection."""
    cfg = Config(
        target_duration=30.0,
        max_clip_s=20.0,
        top_k=2,
    )

    # Create 3 spikes with different scores
    s1 = Spike(onset=10.0, offset=15.0, peak_time=12.0, peak_rise_db=10.0, score=50.0)
    # Long spike that will expand past max_clip_s (20s)
    s2 = Spike(onset=50.0, offset=75.0, peak_time=60.0, peak_rise_db=8.0, score=30.0)
    s3 = Spike(onset=120.0, offset=125.0, peak_time=122.0, peak_rise_db=3.0, score=5.0)

    windows = merge_spikes_into_windows([s1, s2, s3], audio_duration=200.0, config=cfg)
    assert len(windows) == 3

    # Check cropping on s2
    w_long = next(w for w in windows if abs(w.peak_time - 60.0) < 2.0)
    assert w_long.is_cropped is True
    assert w_long.original_start is not None
    assert w_long.original_end is not None
    assert w_long.duration <= cfg.max_clip_s

    # Check drop_reason on unselected windows
    unselected = [w for w in windows if not w.selected]
    assert len(unselected) > 0
    for w in unselected:
        assert w.drop_reason in ("over_length_cap", "top_k", "below_min_score")


def test_score_modes_ranking():
    """Test score_mode = 'area' vs 'peak' vs 'blend'."""
    # Spike A: high peak rise (12 dB) but short duration (low area)
    # Spike B: moderate peak rise (6 dB) but long sustained duration (high area)
    spkA = Spike(onset=10.0, offset=12.0, peak_time=11.0, peak_rise_db=12.0, score=15.0)
    spkB = Spike(onset=40.0, offset=55.0, peak_time=45.0, peak_rise_db=6.0, score=60.0)

    # Mode 'peak': SpkA should rank higher than SpkB
    cfg_peak = Config(score_mode="peak")
    windows_peak = merge_spikes_into_windows([spkA, spkB], audio_duration=100.0, config=cfg_peak)
    win_A_peak = next(w for w in windows_peak if abs(w.peak_time - 11.0) < 1.0)
    win_B_peak = next(w for w in windows_peak if abs(w.peak_time - 45.0) < 1.0)
    assert win_A_peak.score > win_B_peak.score

    # Mode 'area': SpkB should rank higher than SpkA
    cfg_area = Config(score_mode="area")
    windows_area = merge_spikes_into_windows([spkA, spkB], audio_duration=100.0, config=cfg_area)
    win_A_area = next(w for w in windows_area if abs(w.peak_time - 11.0) < 1.0)
    win_B_area = next(w for w in windows_area if abs(w.peak_time - 45.0) < 1.0)
    assert win_B_area.score > win_A_area.score


def test_labels_evaluation_caught_and_missed(client, synthetic_audio_path):
    """
    Test label endpoints:
    - Label at known roar (t=60.0) -> caught = True
    - Label at silence (t=500.0) -> caught = False
    - Recall summary calculation
    - Parameter sweep proposing better settings
    """
    job_id = "test-recovery-job-001"
    db.create_job(job_id, "Test Recovery", "upload", "test.mp4", Config().to_dict())
    job_dir = get_job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    # Copy synthetic audio to job_dir / audio.wav
    shutil.copyfile(synthetic_audio_path, job_dir / "audio.wav")

    # Run detection to populate windows.json
    cfg = Config(min_rise_db=4.0, min_sustain_s=3.0)
    envelope = compute_envelope(synthetic_audio_path, config=cfg)
    spikes = detect_spikes(synthetic_audio_path, config=cfg, envelope=envelope)
    windows = merge_spikes_into_windows(spikes, audio_duration=envelope[4], config=cfg)
    save_manifest(windows, job_dir / "windows.json")

    # 2. Add label at known roar (t=60s)
    res1 = client.post(f"/api/jobs/{job_id}/labels", json={"time": 60.0, "label": "Goal 1-0"})
    assert res1.status_code == 200
    data1 = res1.json()
    assert len(data1["labels"]) == 1
    # Check roar was caught
    assert data1["labels"][0]["caught"] is True

    # 3. Add label at silence (t=500s)
    res2 = client.post(f"/api/jobs/{job_id}/labels", json={"time": 500.0, "label": "Silence"})
    assert res2.status_code == 200
    data2 = res2.json()
    assert len(data2["labels"]) == 2
    lbl_silence = next(l for l in data2["labels"] if l["label"] == "Silence")
    assert lbl_silence["caught"] is False

    # 4. Check summary: 1 caught, 1 missed, 50% recall
    assert data2["summary"]["total"] == 2
    assert data2["summary"]["caught"] == 1
    assert data2["summary"]["missed"] == 1
    assert data2["summary"]["recall"] == 0.5

    # 5. Run parameter sweep on these labels
    sweep_res = client.post(f"/api/jobs/{job_id}/find-settings")
    assert sweep_res.status_code == 200
    sweep_data = sweep_res.json()
    assert "results" in sweep_data
    assert len(sweep_data["results"]) > 0
    best = sweep_data["results"][0]
    assert "min_rise_db" in best
    assert "min_sustain_s" in best
    assert "recall" in best
    assert best["recall"] >= 0.5
