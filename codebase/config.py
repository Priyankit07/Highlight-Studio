"""
Unified Configuration for Highlight Generator.
Holds all tunable hyperparameters with defaults, TOML overrides, and CLI overrides.
All user-facing durations are in seconds.
"""
from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore


@dataclass
class Config:
    # Audio extraction
    sample_rate: int = 22050
    mono: bool = True

    # Audio envelope & processing
    frame_length_s: float = 0.5
    hop_length_s: float = 0.1
    smooth_window_s: float = 1.0
    bandpass_enabled: bool = False
    bandpass_low: float = 300.0
    bandpass_high: float = 3400.0

    # Adaptive baseline
    baseline_window_s: float = 90.0

    # Candidate detection
    min_rise_db: float = 4.0
    min_sustain_s: float = 3.0
    skip_start_s: float = 30.0
    skip_end_s: float = 0.0

    # Window creation & expansion
    pre_roll: float = 12.0
    post_roll: float = 6.0
    merge_gap: float = 2.0
    min_clip_s: float = 6.0
    max_clip_s: float = 45.0

    # Selection
    target_duration: float = 480.0  # seconds (0 = keep all)
    top_k: int | None = None
    min_score: float | None = None
    score_mode: str = "area"  # "area" (default) | "peak" | "blend"

    # Clip cutting & encoding
    crf: int = 20
    preset: str = "veryfast"
    fade_duration_s: float = 0.25
    max_workers: int = 2
    keep_clips: bool = False

    # Output & Execution
    out_dir: Path = field(default_factory=lambda: Path("output video"))
    audio_dir: Path = field(default_factory=lambda: Path("audio output"))
    reuse_audio: bool = False
    dry_run: bool = False
    plot: bool = False
    verbose: bool = False

    @classmethod
    def from_toml(cls, toml_path: str | Path) -> Config:
        """Load configuration from a TOML file and return a Config instance."""
        p = Path(toml_path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {p}")

        with open(p, "rb") as f:
            data = tomllib.load(f)

        # Flatten nested sections if any, or top-level keys
        flat_data: dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(v, dict):
                flat_data.update(v)
            else:
                flat_data[k] = v

        # Convert path strings to Path objects where appropriate
        if "out_dir" in flat_data and isinstance(flat_data["out_dir"], str):
            flat_data["out_dir"] = Path(flat_data["out_dir"])
        if "audio_dir" in flat_data and isinstance(flat_data["audio_dir"], str):
            flat_data["audio_dir"] = Path(flat_data["audio_dir"])

        # Filter to only valid fields on Config
        valid_keys = {f for f in cls.__dataclass_fields__}
        filtered_data = {k: v for k, v in flat_data.items() if k in valid_keys}

        return cls(**filtered_data)

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary representation."""
        d = asdict(self)
        d["out_dir"] = str(self.out_dir)
        d["audio_dir"] = str(self.audio_dir)
        return d
