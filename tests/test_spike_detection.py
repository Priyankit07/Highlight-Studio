"""
Test excitement spike detection: recovery of known roars, rejection of distractors,
and graceful handling of silent audio or signals shorter than baseline window.
"""
from pathlib import Path
import json
import numpy as np
from scipy.io import wavfile

from spike_detection import detect_spikes
from config import Config
from tools.make_synthetic_match import generate_synthetic_audio


def test_spike_detection_synthetic_roars_and_rejections(tmp_path: Path):
    """
    Verify:
    1. At least 4 of 5 known roars recovered within +/- 3s.
    2. Jingle (2-12s), mic thump (160s), and referee whistle (280s) are NOT selected.
    """
    # Use existing synthetic audio if available, or generate a test file
    project_root = Path(__file__).resolve().parent.parent
    synthetic_wav = project_root / "tools" / "synthetic_match.wav"
    events_json = project_root / "tools" / "synthetic_events.json"

    if not synthetic_wav.exists() or not events_json.exists():
        audio_float, events, _ = generate_synthetic_audio(duration_s=720.0, sample_rate=22050)
        synthetic_wav = tmp_path / "test_match.wav"
        wavfile.write(str(synthetic_wav), 22050, (audio_float * 32767).astype(np.int16))
    else:
        with open(events_json, "r", encoding="utf-8") as f:
            events = json.load(f)

    cfg = Config(min_rise_db=4.0, min_sustain_s=3.0, skip_start_s=30.0)
    spikes = detect_spikes(synthetic_wav, config=cfg)

    # 1. Check recovery of 5 ground-truth roars
    roars = [e for e in events if e.get("type") == "roar"]
    assert len(roars) == 5

    found_roars = 0
    for r in roars:
        r_peak = r["peak"]
        if any(abs(s.peak_time - r_peak) <= 3.0 for s in spikes):
            found_roars += 1

    # Ground rule requirement: at least 4 of 5 recovered
    assert found_roars >= 4, f"Only recovered {found_roars} of 5 roars"

    # 2. Check rejection of distractors
    for s in spikes:
        # No spike in jingle zone (0 - 30s)
        assert s.peak_time >= 30.0, f"Jingle distractor detected at {s.peak_time}s"
        # No spike at mic thump (160s)
        assert not (159.0 <= s.peak_time <= 161.5), f"Mic thump detected at {s.peak_time}s"
        # No spike at whistle (280s)
        assert not (279.0 <= s.peak_time <= 282.5), f"Whistle detected at {s.peak_time}s"


def test_silent_audio(tmp_path: Path):
    """Silent audio should return empty list of spikes without crashing."""
    wav_path = tmp_path / "silence.wav"
    sr = 22050
    wavfile.write(str(wav_path), sr, np.zeros(sr * 10, dtype=np.int16))

    spikes = detect_spikes(wav_path, Config())
    assert spikes == []


def test_short_audio_shorter_than_baseline_window(tmp_path: Path):
    """Audio shorter than baseline window (e.g. 5 seconds vs 90s baseline) must not crash."""
    wav_path = tmp_path / "short.wav"
    sr = 22050
    # 5 seconds of low noise
    noise = np.random.normal(0, 100, sr * 5).astype(np.int16)
    wavfile.write(str(wav_path), sr, noise)

    spikes = detect_spikes(wav_path, Config(baseline_window_s=90.0, skip_start_s=0.0))
    assert isinstance(spikes, list)
