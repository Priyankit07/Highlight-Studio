"""
Test envelope reuse in detect_spikes and progress callback in pipeline.
"""
from pathlib import Path
import numpy as np
import pytest
from scipy.io import wavfile

from spike_detection import compute_envelope, detect_spikes
from pipeline import run_pipeline
from config import Config


def test_detect_spikes_envelope_reuse(tmp_path: Path):
    """Passing precomputed envelope produces identical spikes and avoids recalculating."""
    sr = 22050
    t = np.arange(sr * 15) / sr
    audio = np.random.normal(0, 0.05, len(t))
    # Add spike at 8s
    spike_mask = (t >= 8.0) & (t < 11.0)
    audio[spike_mask] += 0.8 * np.sin(np.pi * (t[spike_mask] - 8.0) / 3.0)
    audio_int16 = (audio / np.max(np.abs(audio)) * 0.9 * 32767).astype(np.int16)

    wav_path = tmp_path / "test.wav"
    wavfile.write(str(wav_path), sr, audio_int16)

    cfg = Config(skip_start_s=2.0, min_rise_db=3.0, min_sustain_s=1.0)

    # 1. Normal call
    spikes_normal = detect_spikes(wav_path, config=cfg)

    # 2. Call with precomputed envelope
    env = compute_envelope(wav_path, config=cfg)
    spikes_reused = detect_spikes(wav_path, config=cfg, envelope=env)

    assert len(spikes_normal) == len(spikes_reused)
    for s1, s2 in zip(spikes_normal, spikes_reused):
        assert s1.peak_time == s2.peak_time
        assert s1.peak_rise_db == s2.peak_rise_db
        assert s1.score == s2.score


def test_progress_cb_called(tmp_path: Path):
    """Test progress_cb is triggered through stages."""
    events = []

    def cb(stage: str, fraction: float | None, message: str):
        events.append((stage, fraction, message))

    # Create short 10s video
    from tests.test_pipeline_e2e import _generate_short_match_mp4
    v_path = tmp_path / "short_match.mp4"
    _generate_short_match_mp4(v_path, duration_s=15.0)

    cfg = Config(
        out_dir=tmp_path / "out",
        audio_dir=tmp_path / "audio",
        skip_start_s=2.0,
        pre_roll=2.0,
        post_roll=1.0,
        min_rise_db=2.0,
        min_sustain_s=1.0,
        preset="ultrafast",
    )

    run_pipeline(v_path, config=cfg, progress_cb=cb)

    stages_seen = {e[0] for e in events}
    assert "extracting_audio" in stages_seen
    assert "detecting" in stages_seen
    assert "selecting" in stages_seen
