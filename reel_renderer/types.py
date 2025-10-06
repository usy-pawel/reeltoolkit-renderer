"""Pydantic models for render job specification."""
from pydantic import BaseModel, Field
from typing import Optional


class RenderJobSpec(BaseModel):
    """Specification for a video render job."""
    job_id: str
    output_name: str = "out.mp4"
    width: int = 720
    height: int = 1280
    fps: int = 25
    
    # Optional fields for full spec compatibility
    background_color: Optional[str] = "#000000"
