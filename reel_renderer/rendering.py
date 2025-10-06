"""Video rendering with moviepy and ffmpeg - HEAVY IMPORTS HERE."""
import asyncio
from pathlib import Path
from typing import Union

# Heavy imports - only loaded when actually rendering
import numpy as np
from moviepy.editor import ColorClip

from .types import RenderJobSpec


async def render_reel(
    spec: RenderJobSpec,
    bundle_path: Union[str, Path],
    output_path: Union[str, Path]
) -> Path:
    """
    Render a video reel based on specification.
    
    For now: generates a simple colored clip to test end-to-end.
    bundle_path can be empty/minimal for testing.
    
    Args:
        spec: Render job specification
        bundle_path: Path to bundle ZIP (can be minimal for testing)
        output_path: Where to write the output video
        
    Returns:
        Path to the rendered video file
    """
    output_path = Path(output_path)
    
    # Simple test render: 1-second blank clip
    def _render():
        clip = ColorClip(
            size=(spec.width, spec.height),
            color=(0, 0, 0),  # black
            duration=1.0
        )
        clip.fps = spec.fps
        clip.write_videofile(
            str(output_path),
            fps=spec.fps,
            codec='libx264',
            audio=False,
            logger=None  # suppress moviepy logs
        )
        clip.close()
    
    # Run in executor to avoid blocking
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _render)
    
    return output_path
