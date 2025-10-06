"""Video rendering with moviepy and ffmpeg - HEAVY IMPORTS HERE."""
import os
import asyncio
import zipfile
from pathlib import Path
from typing import Union

from .types import RenderJobSpec

# Set ffmpeg paths BEFORE any moviepy imports to prevent network downloads
os.environ.setdefault("IMAGEIO_FFMPEG_EXE", "/usr/bin/ffmpeg")
os.environ.setdefault("MOVIEPY_USE_IMAGEIO_FFMPEG", "1")
os.environ.setdefault("FFMPEG_BINARY", "/usr/bin/ffmpeg")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/.cache")


def _extract_bundle(bundle_zip: Path, dest: Path) -> None:
    """Extract bundle ZIP to destination directory."""
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle_zip, "r") as z:
        z.extractall(dest)


async def render_reel(
    spec: RenderJobSpec,
    bundle_path: Union[str, Path],
    output_path: Union[str, Path]
) -> Path:
    """
    Render a video reel based on specification.
    
    Minimal MoviePy render: black background + optional image overlay.
    No audio, no ImageMagick, single-threaded for stability.
    
    Args:
        spec: Render job specification
        bundle_path: Path to bundle ZIP
        output_path: Where to write the output video
        
    Returns:
        Path to the rendered video file
    """
    bundle_path = Path(bundle_path)
    output_path = Path(output_path)
    
    # 1) Extract bundle (even if empty - shouldn't hang)
    tmp_assets = output_path.parent / "assets"
    _extract_bundle(bundle_path, tmp_assets)
    
    # 2) LAZY IMPORT moviepy - ONLY HERE, not at module level
    from moviepy.editor import ColorClip, ImageClip, CompositeVideoClip
    
    # 3) Black background 1 second (no audio)
    bg = ColorClip(
        size=(spec.width, spec.height),
        color=(0, 0, 0),
        duration=1.0
    ).set_fps(spec.fps)
    
    # 4) Optional: add image overlay if frame.png exists in bundle
    img_path = tmp_assets / "frame.png"
    if img_path.exists():
        img = ImageClip(str(img_path)).set_duration(1.0)
        clip = CompositeVideoClip([bg, img.set_position("center")])
    else:
        clip = bg
    
    # 5) Write video - explicit params (no audio, single thread, fast)
    def _write():
        clip.write_videofile(
            str(output_path),
            fps=spec.fps,
            codec="libx264",
            preset="ultrafast",
            threads=1,
            audio=False,
            verbose=False,
            logger=None,
            ffmpeg_params=["-movflags", "+faststart"]
        )
    
    # Run in thread pool to avoid blocking event loop
    await asyncio.to_thread(_write)
    clip.close()
    
    return output_path
