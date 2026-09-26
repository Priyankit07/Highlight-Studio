"""
End-to-end pipeline test on a short synthetic broadcast MP4.
Verifies audio extraction, detection, window creation, clip cutting, duration check, and manifest outputs.
"""
from pathlib import Path
import subprocess
import imageio_ffmpeg
import numpy as np
import pytest
from scipy.io import wavfile

from pipeline import run_pipeline
from config import Config


def _generate_short_match_mp4(mp4_path: Path, duration_s: float = 60.0, sr: int = 22050) -> list[float]:
    """Create a 60s synthetic football broadcast video with 2 known roars."""
    n_samples = int(duration_s * sr)
    t = np.arange(n_samples) / sr

    # Base noise
    audio = np.random.normal(0, 0.05, n_samples)

    # 2 Roars: at 20s and 45s
    roar_times = [20.0, 45.0]
    for r_t in roar_times:
        r_mask = (t >= r_t) & (t < r_t + 5.0)
        t_r = t[r_mask] - r_t
        env = np.sin(np.pi * t_r / 5.0)
        audio[r_mask] += np.random.normal(0, 0.5, len(t_r)) * env

    audio = (audio / np.max(np.abs(audio)) * 0.9 * 32767).astype(np.int16)
    wav_path = mp4_path.with_suffix(".wav")
    wavfile.write(str(wav_path), sr, audio)

    # Render MP4
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe, "-y",
        "-f", "lavfi", "-i", f"color=c=0x1a4314:s=320x240:r=25:d={duration_s}",
        "-i", str(wav_path),
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        str(mp4_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if wav_path.exists():
        wav_path.unlink()
    return roar_times


def test_pipeline_end_to_end(tmp_path: Path):
    """Run full pipeline on a 60s match video and verify outputs and duration tolerance."""
    match_mp4 = tmp_path / "e2e_match.mp4"
    roar_times = _generate_short_match_mp4(match_mp4, duration_s=60.0)

    out_dir = tmp_path / "output video"
    audio_dir = tmp_path / "audio output"

    cfg = Config(
        out_dir=out_dir,
        audio_dir=audio_dir,
        skip_start_s=5.0,
        pre_roll=4.0,
        post_roll=2.0,
        min_rise_db=3.0,
        min_sustain_s=2.0,
        target_duration=40.0,
        preset="ultrafast",
        plot=True,
    )

    reel_path = run_pipeline(match_mp4, config=cfg)

    assert reel_path is not None
    assert reel_path.exists()
    assert reel_path.stat().st_size > 0

    # Verify duration
    _, reel_secs = imageio_ffmpeg.count_frames_and_secs(str(reel_path))
    assert reel_secs > 5.0
    assert reel_secs <= 42.0

    # Verify manifest and plot files exist
    manifest_json = out_dir / "e2e_match" / "windows.json"
    manifest_csv = out_dir / "e2e_match" / "windows.csv"
    debug_plot = out_dir / "e2e_match" / "debug.png"

    assert manifest_json.exists()
    assert manifest_csv.exists()
    assert debug_plot.exists()
