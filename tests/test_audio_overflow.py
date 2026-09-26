"""
Test mono int16 audio handling to ensure absence of integer squaring overflow.
"""
from pathlib import Path
import numpy as np
from scipy.io import wavfile

from spike_detection import load_audio, compute_envelope
from config import Config


def test_mono_int16_no_overflow(tmp_path: Path):
    """Ensure loud mono int16 audio does not overflow when loaded or squared."""
    sr = 22050
    # Create alternating large positive and negative int16 values near max (32767)
    n_samples = sr * 2  # 2 seconds
    t = np.arange(n_samples) / sr
    # 500 Hz full-scale tone
    sig = (32700 * np.sin(2 * np.pi * 500 * t)).astype(np.int16)

    wav_file = tmp_path / "loud_int16_mono.wav"
    wavfile.write(str(wav_file), sr, sig)

    loaded_sr, float_audio = load_audio(wav_file)

    assert loaded_sr == sr
    assert float_audio.dtype == np.float32
    # Verify samples are bounded in [-1.0, 1.0]
    assert np.all(float_audio >= -1.0)
    assert np.all(float_audio <= 1.0)
    assert np.max(float_audio) > 0.95

    # Compute envelope and ensure all dB values are finite and non-negative RMS
    times, smoothed_db, baseline_db, rise_db, dur = compute_envelope(wav_file, Config())
    assert np.all(np.isfinite(smoothed_db))
    assert np.all(np.isfinite(baseline_db))
    assert np.all(np.isfinite(rise_db))
    assert dur > 1.95
