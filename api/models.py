"""
Pydantic models and configuration schema for the Highlight Generator API.
"""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator


VALID_PRESETS = [
    "ultrafast", "superfast", "veryfast", "faster", "fast",
    "medium", "slow", "slower", "veryslow"
]


class ConfigModel(BaseModel):
    """
    Validated configuration parameters matching Config dataclass.
    Includes field metadata for dynamic UI schema generation.
    """
    # Basic parameters
    min_rise_db: float = Field(
        default=4.0, ge=1.0, le=15.0,
        description="Minimum volume rise in dB above recent rolling baseline to trigger a highlight candidate",
        json_schema_extra={"group": "basic", "step": 0.5, "unit": "dB"}
    )
    min_sustain_s: float = Field(
        default=3.0, ge=1.0, le=8.0,
        description="Minimum duration excitement must persist above threshold to reject brief clicks and referee whistles",
        json_schema_extra={"group": "basic", "step": 0.5, "unit": "s"}
    )
    target_duration: float = Field(
        default=480.0, ge=0.0, le=3600.0,
        description="Upper cap on reel length in seconds (0 = include all detected moments)",
        json_schema_extra={"group": "basic", "step": 30.0, "unit": "s"}
    )
    pre_roll: float = Field(
        default=12.0, ge=0.0, le=60.0,
        description="Seconds to include before the excitement peak to capture build-up play",
        json_schema_extra={"group": "basic", "step": 1.0, "unit": "s"}
    )
    post_roll: float = Field(
        default=6.0, ge=0.0, le=60.0,
        description="Seconds to include after the excitement subsides for celebration and replays",
        json_schema_extra={"group": "basic", "step": 1.0, "unit": "s"}
    )

    # Advanced parameters
    skip_start_s: float = Field(
        default=30.0, ge=0.0, le=600.0,
        description="Initial seconds of broadcast to ignore (pre-match intros, studio graphics)",
        json_schema_extra={"group": "advanced", "step": 5.0, "unit": "s"}
    )
    skip_end_s: float = Field(
        default=0.0, ge=0.0, le=600.0,
        description="Trailing seconds of broadcast to ignore",
        json_schema_extra={"group": "advanced", "step": 5.0, "unit": "s"}
    )
    merge_gap: float = Field(
        default=2.0, ge=0.0, le=30.0,
        description="Merge consecutive windows if gap between them is less than this duration",
        json_schema_extra={"group": "advanced", "step": 0.5, "unit": "s"}
    )
    min_clip_s: float = Field(
        default=6.0, ge=2.0, le=30.0,
        description="Minimum allowed duration for any individual highlight clip",
        json_schema_extra={"group": "advanced", "step": 1.0, "unit": "s"}
    )
    max_clip_s: float = Field(
        default=45.0, ge=10.0, le=120.0,
        description="Maximum allowed duration for any individual highlight clip",
        json_schema_extra={"group": "advanced", "step": 5.0, "unit": "s"}
    )
    baseline_window_s: float = Field(
        default=90.0, ge=30.0, le=300.0,
        description="Rolling median baseline window to adapt to ambient stadium crowd noise",
        json_schema_extra={"group": "advanced", "step": 5.0, "unit": "s"}
    )
    top_k: int | None = Field(
        default=None, ge=1, le=100,
        description="Maximum number of candidate moments to select into reel",
        json_schema_extra={"group": "advanced", "step": 1, "unit": "moments"}
    )
    fade_duration_s: float = Field(
        default=0.25, ge=0.0, le=1.0,
        description="Duration in seconds of video and audio fade transitions at clip boundaries",
        json_schema_extra={"group": "advanced", "step": 0.05, "unit": "s"}
    )
    crf: int = Field(
        default=20, ge=16, le=28,
        description="x264 Constant Rate Factor encoding quality (lower is higher visual quality)",
        json_schema_extra={"group": "advanced", "step": 1, "unit": "CRF"}
    )
    preset: str = Field(
        default="veryfast",
        description="x264 encoding speed preset",
        json_schema_extra={"group": "advanced", "choices": VALID_PRESETS}
    )
    score_mode: Literal["area", "peak", "blend"] = Field(
        default="area",
        description="Moment ranking score mode (area: crowd excitement integral, peak: max spike height in dB, blend: normalized combination)",
        json_schema_extra={"group": "advanced", "choices": ["area", "peak", "blend"]}
    )

    @field_validator("preset")
    @classmethod
    def validate_preset(cls, v: str) -> str:
        if v not in VALID_PRESETS:
            raise ValueError(f"preset must be one of: {', '.join(VALID_PRESETS)}")
        return v

    @field_validator("target_duration")
    @classmethod
    def validate_target_duration(cls, v: float) -> float:
        if v != 0.0 and (v < 30.0 or v > 3600.0):
            raise ValueError("target_duration must be 0 (keep all) or between 30 and 3600 seconds")
        return v

    @model_validator(mode="after")
    def validate_clip_duration_order(self) -> ConfigModel:
        if self.min_clip_s > self.max_clip_s:
            raise ValueError(f"min_clip_s ({self.min_clip_s}s) cannot be greater than max_clip_s ({self.max_clip_s}s)")
        return self


def get_config_schema() -> list[dict[str, Any]]:
    """
    Extract structured schema list from ConfigModel for UI dynamic forms.
    """
    schema = []
    json_schema = ConfigModel.model_json_schema()
    properties = json_schema.get("properties", {})
    for name, prop in properties.items():
        field = ConfigModel.model_fields.get(name)
        extra = (field.json_schema_extra or {}) if field else {}

        type_str = prop.get("type", "number")
        if type_str == "number":
            type_str = "float"
        elif type_str == "integer":
            type_str = "int"
        elif type_str == "string":
            type_str = "str"

        item = {
            "name": name,
            "type": type_str,
            "default": prop.get("default"),
            "description": prop.get("description", ""),
            "group": extra.get("group", "advanced"),
            "step": extra.get("step"),
            "unit": extra.get("unit"),
            "min": prop.get("minimum"),
            "max": prop.get("maximum"),
            "choices": extra.get("choices"),
        }
        schema.append(item)
    return schema


# API Request and Response Models

class UploadInitRequest(BaseModel):
    filename: str
    size: int = Field(gt=0, description="File size in bytes")


class UploadInitResponse(BaseModel):
    upload_id: str
    chunk_size: int


class UploadStatusResponse(BaseModel):
    upload_id: str
    received: list[int]


class JobSource(BaseModel):
    type: Literal["upload", "url"]
    upload_id: str | None = None
    url: str | None = None


class CreateJobRequest(BaseModel):
    source: JobSource
    title: str | None = None
    config: dict[str, Any] | None = None


class RetuneRequest(BaseModel):
    config: dict[str, Any]


class RenderWindow(BaseModel):
    start: float = Field(ge=0.0)
    end: float = Field(gt=0.0)


class CreateRenderRequest(BaseModel):
    windows: list[RenderWindow]
    fade_duration_s: float | None = Field(default=None, ge=0.0, le=1.0)
    crf: int | None = Field(default=None, ge=16, le=28)
    preset: str | None = None

    @field_validator("preset")
    @classmethod
    def validate_render_preset(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_PRESETS:
            raise ValueError(f"preset must be one of: {', '.join(VALID_PRESETS)}")
        return v

    @model_validator(mode="after")
    def validate_windows_order_and_no_overlaps(self) -> CreateRenderRequest:
        if not self.windows:
            raise ValueError("windows list cannot be empty")

        for idx, w in enumerate(self.windows):
            dur = w.end - w.start
            if dur < 2.0:
                raise ValueError(f"Window #{idx+1} ({w.start:.2f}s - {w.end:.2f}s) is shorter than minimum allowed 2.0s")

        # Verify sorted and zero overlaps
        for i in range(len(self.windows) - 1):
            curr_w = self.windows[i]
            next_w = self.windows[i + 1]
            if curr_w.start > next_w.start:
                raise ValueError(f"Windows must be in chronological order: window #{i+1} starts after window #{i+2}")
            if curr_w.end > next_w.start:
                raise ValueError(
                    f"Overlapping windows detected: window #{i+1} ({curr_w.start:.2f}s - {curr_w.end:.2f}s) overlaps with window #{i+2} ({next_w.start:.2f}s - {next_w.end:.2f}s)"
                )

        return self


class LabelItem(BaseModel):
    id: str | None = None
    time: float = Field(ge=0.0)
    label: str = Field(min_length=1)


class SaveLabelsRequest(BaseModel):
    labels: list[LabelItem]


class UpdateWindowModel(BaseModel):
    start: float = Field(ge=0.0)
    end: float = Field(gt=0.0)
    score: float = 0.0
    peak_time: float = 0.0
    spike_count: int = 1
    selected: bool = True
    source: str = "auto"
    drop_reason: str | None = None
    peak_rise_db: float = 0.0
    original_start: float | None = None
    original_end: float | None = None
    is_cropped: bool = False
    tag: str | None = None
    note: str | None = None


class UpdateWindowsRequest(BaseModel):
    windows: list[UpdateWindowModel]
