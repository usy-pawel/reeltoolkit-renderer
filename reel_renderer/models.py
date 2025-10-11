"""Pydantic models describing render job specifications."""

from __future__ import annotations

from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, field_validator


NumberRange = Tuple[float, float]


class Dimensions(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: int = Field(gt=0)


class MotionTransition(BaseModel):
    type: Literal["fade", "crossfade", "dissolve"]
    duration: float = Field(gt=0)


class Motion(BaseModel):
    type: Literal[
        "zoom-in",
        "zoom-out",
        "pan-left",
        "pan-right",
        "pan-up",
        "pan-down",
    ]
    amount: float | None = Field(default=None, ge=0.0, le=1.0)
    transition: MotionTransition | None = None


class TransformSpec(BaseModel):
    scale: float | None = Field(default=None, gt=0.0, le=6.0)
    offset_x: float | None = None
    offset_y: float | None = None


class SlideSpec(BaseModel):
    image: str
    audio: str
    motion: Motion | None = None
    subtitle: bool | None = True
    transform: TransformSpec | None = None


class SubtitleSpec(BaseModel):
    format: Literal["ass", "srt"] = "ass"
    file: str


class BackgroundMusicSpec(BaseModel):
    file: str
    volume: float | None = Field(default=None, ge=0.0, le=2.0)
    duck: bool | None = None
    mute_ranges: List[NumberRange] | None = None

    @field_validator("mute_ranges")
    def _validate_ranges(
        cls, value: Optional[List[NumberRange]]
    ) -> Optional[List[NumberRange]]:
        if value is None:
            return None
        cleaned: List[NumberRange] = []
        for start, end in value:
            if end <= start:
                raise ValueError("mute range end must be greater than start")
            cleaned.append((float(start), float(end)))
        return cleaned


class RenderOptions(BaseModel):
    use_parallel: bool = False
    quality: Literal["draft", "final"] = "final"
    gpu_preset: str | None = None

    @field_validator("gpu_preset")
    @classmethod
    def _normalize_gpu(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized.upper()


class RenderJobSpec(BaseModel):
    job_id: str
    output_name: str = Field(default="render.mp4", min_length=1)
    dimensions: Dimensions
    background_color: str = "#000000"
    render: RenderOptions = Field(default_factory=RenderOptions)
    slides: List[SlideSpec]
    subtitle: SubtitleSpec | None = None
    ending_video: str | None = None
    background_music: BackgroundMusicSpec | None = None

    @field_validator("slides")
    def _validate_slides(cls, value: List[SlideSpec]) -> List[SlideSpec]:
        if not value:
            raise ValueError("at least one slide is required")
        return value
