#!/usr/bin/env python3
"""
Generate a synthetic football broadcast (WAV + MP4) with known event times.
Used for baseline measurement, test suites, and tuning.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt


def _butter_bandpass_filter(data: np.ndarray, lowcut: float, highcut: float, fs: int, order: int = 4) -> np.ndarray:
    sos = butter(order, [lowcut, highcut], btype="band", fs=fs, output="sos")
    return sosfilt(sos, data)


def generate_synthetic_audio(
    duration_s: float = 720.0,
    sample_rate: int = 22050,
    seed: int = 42,
) -> tuple[np.ndarray, list[dict], list[dict]]:
    """
    Generate synthetic broadcast audio and ground-truth events.

    Returns:
        (audio_float, all_events, ground_truth_roars)
    """
    np.random.seed(seed)
    n_samples = int(duration_s * sample_rate)
    t = np.arange(n_samples) / sample_rate

    # 1. Base crowd noise: bandpassed white noise (100 Hz - 1400 Hz) with slow drift
    raw_noise = np.random.normal(0, 1, n_samples)
    crowd_noise = _butter_bandpass_filter(raw_noise, 100.0, 1400.0, sample_rate, order=4)
    # Normalize crowd base to RMS ~ 0.05
    crowd_noise = crowd_noise / (np.std(crowd_noise) + 1e-9) * 0.05

    # Slow crowd drift (periods ~ 30-90s)
    drift = 1.0 + 0.25 * np.sin(2 * np.pi * t / 47.0) + 0.15 * np.cos(2 * np.pi * t / 79.0)
    audio = crowd_noise * drift

    events = []

    # 2. Intro jingle: loud 10s music in first 15s (t = 2.0s to 12.0s)
    jingle_start = 2.0
    jingle_duration = 10.0
    jingle_mask = (t >= jingle_start) & (t < jingle_start + jingle_duration)
    t_j = t[jingle_mask] - jingle_start
    # Chord: 440 Hz (A4) + 554.37 Hz (C#5) + 659.25 Hz (E5) + drum beat simulation
    jingle_sig = (
        0.35 * np.sin(2 * np.pi * 440.0 * t_j)
        + 0.25 * np.sin(2 * np.pi * 554.37 * t_j)
        + 0.25 * np.sin(2 * np.pi * 659.25 * t_j)
        + 0.20 * np.sin(2 * np.pi * 880.0 * t_j)
    )
    # Modulation envelope
    jingle_env = np.sin(np.pi * t_j / jingle_duration) ** 0.5
    # Very loud: peak around 0.85
    jingle_full = jingle_sig * jingle_env
    jingle_full = jingle_full / np.max(np.abs(jingle_full)) * 0.85
    audio[jingle_mask] += jingle_full

    events.append({
        "type": "jingle",
        "start": jingle_start,
        "end": jingle_start + jingle_duration,
        "peak": jingle_start + jingle_duration / 2.0,
        "description": "Loud intro broadcast jingle (distractor)",
    })

    # 3. 55 commentary bursts (+3 dB, 2-5s duration)
    # Speech-like bandpassed noise (300-3000 Hz) with voice pitch modulation
    rng = np.random.default_rng(seed)
    burst_starts = np.linspace(20.0, duration_s - 15.0, 55) + rng.uniform(-1.5, 1.5, 55)
    for b_idx, b_start in enumerate(burst_starts):
        b_dur = rng.uniform(2.0, 5.0)
        b_mask = (t >= b_start) & (t < b_start + b_dur)
        if not np.any(b_mask):
            continue
        t_b = t[b_mask] - b_start
        # Speech formants simulation: harmonics of 130 Hz + shaped noise
        voice = (
            np.sin(2 * np.pi * 130.0 * t_b) * 0.4
            + np.sin(2 * np.pi * 260.0 * t_b) * 0.3
            + np.sin(2 * np.pi * 390.0 * t_b) * 0.2
        ) * (0.5 + 0.5 * np.sin(2 * np.pi * 3.5 * t_b))
        speech_noise = rng.normal(0, 1, len(t_b))
        speech_noise = _butter_bandpass_filter(speech_noise, 300.0, 3000.0, sample_rate, order=2)
        speech_noise = speech_noise / (np.std(speech_noise) + 1e-9)

        burst_sig = (0.5 * voice + 0.5 * speech_noise)
        # +3 dB above baseline crowd: multiplier ~ 1.41 of crowd RMS
        burst_env = np.sin(np.pi * t_b / b_dur)  # smooth window
        audio[b_mask] += burst_sig * burst_env * 0.07

    # 4. 5 Crowd roars (ground truth highlights!)
    # Attack < 0.5s, 5-10s decay, +10 to +15 dB above crowd
    # Times chosen: t = 95s, t = 210s, t = 345s, t = 490s, t = 620s
    roar_configs = [
        {"start": 95.0, "attack": 0.3, "decay": 7.0, "gain": 0.55, "label": "Roar 1 (Goal)"},
        {"start": 210.0, "attack": 0.25, "decay": 6.0, "gain": 0.50, "label": "Roar 2 (Chance)"},
        {"start": 345.0, "attack": 0.4, "decay": 8.5, "gain": 0.60, "label": "Roar 3 (Goal)"},
        {"start": 490.0, "attack": 0.35, "decay": 5.5, "gain": 0.48, "label": "Roar 4 (Near Miss)"},
        {"start": 620.0, "attack": 0.3, "decay": 9.0, "gain": 0.65, "label": "Roar 5 (Goal)"},
    ]

    ground_truth_roars = []
    for r in roar_configs:
        r_start = r["start"]
        r_attack = r["attack"]
        r_decay = r["decay"]
        r_total = r_attack + r_decay
        r_mask = (t >= r_start) & (t < r_start + r_total)
        if not np.any(r_mask):
            continue
        t_r = t[r_mask] - r_start

        # Roar envelope: fast linear rise in attack, exponential decay
        env = np.zeros_like(t_r)
        att_idx = t_r < r_attack
        dec_idx = ~att_idx
        env[att_idx] = t_r[att_idx] / r_attack
        env[dec_idx] = np.exp(-(t_r[dec_idx] - r_attack) / (r_decay * 0.35))

        # Roar acoustics: broad excitement energy (150 - 3200 Hz filtered noise with turbulence)
        r_noise = rng.normal(0, 1, len(t_r))
        r_filtered = _butter_bandpass_filter(r_noise, 150.0, 3200.0, sample_rate, order=3)
        r_filtered = r_filtered / (np.std(r_filtered) + 1e-9)

        roar_sig = r_filtered * env * r["gain"]
        audio[r_mask] += roar_sig

        peak_time = r_start + r_attack
        end_time = r_start + r_total
        event_dict = {
            "type": "roar",
            "start": round(r_start, 2),
            "peak": round(peak_time, 2),
            "end": round(end_time, 2),
            "duration": round(r_total, 2),
            "description": r["label"],
        }
        events.append(event_dict)
        ground_truth_roars.append(event_dict)

    # 5. One 0.1s very loud mic thump at t = 160.0s (distractor)
    thump_start = 160.0
    thump_dur = 0.1
    thump_mask = (t >= thump_start) & (t < thump_start + thump_dur)
    if np.any(thump_mask):
        t_th = t[thump_mask] - thump_start
        # Low frequency transient 80 Hz decaying rapidly, very loud peak
        thump_sig = 0.90 * np.sin(2 * np.pi * 80.0 * t_th) * np.exp(-t_th / 0.02)
        audio[thump_mask] += thump_sig
        events.append({
            "type": "thump",
            "start": thump_start,
            "end": round(thump_start + thump_dur, 2),
            "peak": round(thump_start + 0.01, 2),
            "description": "0.1s loud mic thump (distractor)",
        })

    # 6. One 1.2s 3 kHz referee whistle at t = 280.0s (distractor)
    whistle_start = 280.0
    whistle_dur = 1.2
    whistle_mask = (t >= whistle_start) & (t < whistle_start + whistle_dur)
    if np.any(whistle_mask):
        t_wh = t[whistle_mask] - whistle_start
        # 3 kHz tone + trill modulation (around 25 Hz)
        trill = 1.0 + 0.05 * np.sin(2 * np.pi * 25.0 * t_wh)
        whistle_sig = 0.65 * np.sin(2 * np.pi * 3000.0 * trill * t_wh)
        # Envelope with fast 0.05s fade in/out
        wh_env = np.ones_like(t_wh)
        fade_samples = int(0.05 * sample_rate)
        if len(t_wh) > 2 * fade_samples:
            wh_env[:fade_samples] = np.linspace(0, 1, fade_samples)
            wh_env[-fade_samples:] = np.linspace(1, 0, fade_samples)
        audio[whistle_mask] += whistle_sig * wh_env
        events.append({
            "type": "whistle",
            "start": whistle_start,
            "end": round(whistle_start + whistle_dur, 2),
            "peak": round(whistle_start + whistle_dur / 2.0, 2),
            "description": "1.2s 3 kHz referee whistle (distractor)",
        })

    # Normalize audio to avoid clipping: scale so max absolute value is 0.95
    max_val = np.max(np.abs(audio))
    if max_val > 0:
        audio = audio / max_val * 0.95

    return audio.astype(np.float32), events, ground_truth_roars


def make_synthetic_match(
    output_wav: Path,
    output_mp4: Path,
    events_json: Path,
    events_csv: Path,
    duration_s: float = 720.0,
    sample_rate: int = 22050,
) -> None:
    """Generate synthetic audio, video MP4, and ground-truth events."""
    print(f"Generating synthetic audio ({duration_s:.1f}s, {sample_rate} Hz)...")
    audio, events, roars = generate_synthetic_audio(duration_s=duration_s, sample_rate=sample_rate)

    # Save WAV as int16
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    audio_int16 = (audio * 32767).astype(np.int16)
    wavfile.write(str(output_wav), sample_rate, audio_int16)
    print(f"Saved audio: {output_wav}")

    # Save events JSON
    events_json.parent.mkdir(parents=True, exist_ok=True)
    with open(events_json, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2)
    print(f"Saved events: {events_json}")

    # Save events CSV (time, label, type)
    events_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(events_csv, "w", encoding="utf-8") as f:
        f.write("time,label,type,duration\n")
        for ev in events:
            f.write(f"{ev['start']:.2f},{ev['description']},{ev['type']},{ev.get('duration', ev['end'] - ev['start']):.2f}\n")
    print(f"Saved events CSV: {events_csv}")

    # Generate synthetic MP4 using FFmpeg lavfi (dark green background)
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe,
        "-y",
        "-f", "lavfi",
        "-i", f"color=c=0x134e1b:s=640x360:r=25:d={duration_s}",
        "-i", str(output_wav),
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(output_mp4),
    ]
    print(f"Rendering synthetic MP4 via ffmpeg: {output_mp4}...")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    print(f"Successfully generated synthetic broadcast video: {output_mp4}")


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic football broadcast audio/video.")
    parser.add_argument("--duration", type=float, default=720.0, help="Duration in seconds (default: 720.0 = 12 mins)")
    parser.add_argument("--sr", type=int, default=22050, help="Sample rate (default: 22050)")
    parser.add_argument("--out-dir", type=Path, default=None, help="Output directory for generated media and events")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    if args.out_dir:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        output_wav = out_dir / "synthetic_match.wav"
        output_mp4 = out_dir / "synthetic_match.mp4"
        events_json = out_dir / "synthetic_events.json"
        events_csv = out_dir / "synthetic_events.csv"
    else:
        tools_dir = project_root / "tools"
        raw_videos_dir = project_root / "raw videos"
        output_wav = tools_dir / "synthetic_match.wav"
        output_mp4 = raw_videos_dir / "synthetic_match.mp4"
        events_json = tools_dir / "synthetic_events.json"
        events_csv = tools_dir / "synthetic_events.csv"

    make_synthetic_match(
        output_wav=output_wav,
        output_mp4=output_mp4,
        events_json=events_json,
        events_csv=events_csv,
        duration_s=args.duration,
        sample_rate=args.sr,
    )


if __name__ == "__main__":
    main()
