"""
Test window creation, merging, constraint enforcement, and greedy selection.
"""
from pathlib import Path
from spike_detection import Spike
from spike_window import Window, merge_spikes_into_windows, save_manifest
from config import Config


def test_windows_never_overlap():
    """Verify that candidate windows never overlap after merging."""
    # Spikes close to each other
    spikes = [
        Spike(onset=20.0, offset=23.0, peak_time=21.0, peak_rise_db=10.0, score=20.0),
        Spike(onset=23.5, offset=26.0, peak_time=24.5, peak_rise_db=12.0, score=30.0),
        Spike(onset=60.0, offset=65.0, peak_time=62.0, peak_rise_db=8.0, score=15.0),
    ]
    cfg = Config(pre_roll=4.0, post_roll=4.0, merge_gap=2.0)
    windows = merge_spikes_into_windows(spikes, audio_duration=100.0, config=cfg)

    # Verify zero overlaps
    for i in range(len(windows) - 1):
        assert windows[i].end <= windows[i + 1].start, (
            f"Window {i} [{windows[i].start}, {windows[i].end}] overlaps with window {i+1} [{windows[i+1].start}, {windows[i+1].end}]"
        )


def test_windows_clamped_to_boundaries():
    """Verify windows are strictly clamped to [0, audio_duration]."""
    spikes = [
        Spike(onset=2.0, offset=4.0, peak_time=3.0, peak_rise_db=10.0, score=20.0),
        Spike(onset=95.0, offset=99.0, peak_time=97.0, peak_rise_db=12.0, score=25.0),
    ]
    # pre_roll = 10s would push start below 0; post_roll = 10s would push end above 100
    cfg = Config(pre_roll=10.0, post_roll=10.0)
    windows = merge_spikes_into_windows(spikes, audio_duration=100.0, config=cfg)

    for w in windows:
        assert w.start >= 0.0, f"Window start {w.start} is less than 0"
        assert w.end <= 100.0, f"Window end {w.end} exceeds audio duration 100.0"


def test_windows_min_and_max_duration():
    """Verify enforcement of min_clip_s and max_clip_s constraints."""
    # 1. Very short spike
    short_spike = [Spike(onset=50.0, offset=51.0, peak_time=50.5, peak_rise_db=5.0, score=10.0)]
    cfg_min = Config(pre_roll=0.0, post_roll=0.0, min_clip_s=6.0, max_clip_s=45.0)
    w_short = merge_spikes_into_windows(short_spike, audio_duration=100.0, config=cfg_min)
    assert w_short[0].duration >= 6.0

    # 2. Very long spike (60s duration)
    long_spike = [Spike(onset=20.0, offset=80.0, peak_time=50.0, peak_rise_db=15.0, score=100.0)]
    cfg_max = Config(pre_roll=0.0, post_roll=0.0, min_clip_s=6.0, max_clip_s=45.0)
    w_long = merge_spikes_into_windows(long_spike, audio_duration=100.0, config=cfg_max)
    assert w_long[0].duration <= 45.0
    # Peak must be contained in the clamped window
    assert w_long[0].start <= 50.0 <= w_long[0].end


def test_greedy_selection_honours_target_duration():
    """Verify greedy selection respects target_duration and selects highest score first."""
    spikes = [
        Spike(onset=10.0, offset=20.0, peak_time=15.0, peak_rise_db=10.0, score=100.0), # Score 100, dur ~ 10s
        Spike(onset=40.0, offset=50.0, peak_time=45.0, peak_rise_db=8.0, score=50.0),   # Score 50, dur ~ 10s
        Spike(onset=70.0, offset=80.0, peak_time=75.0, peak_rise_db=5.0, score=10.0),   # Score 10, dur ~ 10s
    ]
    # Budget of 15s: should select only the highest scoring window (onset 10s)
    cfg = Config(pre_roll=0.0, post_roll=0.0, target_duration=15.0)
    windows = merge_spikes_into_windows(spikes, audio_duration=100.0, config=cfg)

    selected = [w for w in windows if w.selected]
    assert len(selected) == 1
    assert selected[0].score == 100.0
    assert sum(w.duration for w in selected) <= 15.0


def test_manifest_writing(tmp_path: Path):
    """Verify JSON and CSV manifest generation."""
    windows = [
        Window(start=10.0, end=25.0, score=45.0, peak_time=18.0, spike_count=1, selected=True),
        Window(start=50.0, end=65.0, score=15.0, peak_time=58.0, spike_count=1, selected=False),
    ]
    manifest_file = tmp_path / "test_manifest.json"
    json_path, csv_path = save_manifest(windows, manifest_file)

    assert json_path.exists()
    assert csv_path.exists()
    assert json_path.stat().st_size > 0
    assert csv_path.stat().st_size > 0
