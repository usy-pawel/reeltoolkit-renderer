"""Stub render pipeline - no heavy dependencies yet."""
from pathlib import Path


async def render_reel(spec, bundle_path: Path, output_path: Path) -> Path:
    """Stub renderer - returns tiny file instead of actual video.
    
    This tests the async pipeline without moviepy/ffmpeg dependencies.
    """
    # Create parent directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write stub video file
    output_path.write_bytes(b"STUB_VIDEO_CONTENT")
    
    return output_path
