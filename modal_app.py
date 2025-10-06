"""Modal.com serverless handler for ReelToolkit Renderer.

Simple ffmpeg-based video rendering deployed on Modal.
"""
import modal
import base64
import tempfile
import subprocess
from pathlib import Path

# Create Modal app
app = modal.App("reeltoolkit-renderer")

# Define the container image with ffmpeg and reel_renderer
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "fastapi[standard]",  # Required for web endpoints
        "pydantic==2.8.2",
        "typing_extensions>=4.9.0",
        "numpy",
        "Pillow",
        "imageio==2.34.0",
        "imageio-ffmpeg==0.4.9",
        "moviepy==1.0.3"
    )
    .add_local_dir("reel_renderer", remote_path="/root/reel_renderer")
)


@app.function(
    image=image,
    timeout=600,  # 10 minutes max
    memory=2048,  # 2GB RAM
)
def test_ffmpeg():
    """
    Simple test: generate a 1-second black video using pure ffmpeg.
    Returns base64-encoded video.
    """
    print("🎬 Generating test video with ffmpeg...")
    
    # Create temp output file
    tmp_dir = tempfile.mkdtemp(prefix="modal_ffmpeg_")
    out_path = Path(tmp_dir) / "test.mp4"
    
    # FFmpeg command: 1-second black video, 720x1280 (portrait)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", 
        "-i", "color=c=black:s=720x1280:d=1:r=25",
        "-pix_fmt", "yuv420p",
        "-an",  # no audio
        str(out_path)
    ]
    
    try:
        result = subprocess.run(
            cmd, 
            check=True, 
            capture_output=True, 
            text=True
        )
        print(f"✅ FFmpeg success: {result.stderr[-200:]}")  # Last 200 chars
        
        # Read and encode video
        video_bytes = out_path.read_bytes()
        video_b64 = base64.b64encode(video_bytes).decode('utf-8')
        
        return {
            "success": True,
            "size_bytes": len(video_bytes),
            "video_b64": video_b64,
            "message": "Test video generated successfully"
        }
        
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg failed: {e.stderr}")
        return {
            "success": False,
            "error": e.stderr
        }
    finally:
        # Cleanup
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.function(
    image=image,
    timeout=600,
    memory=4096,  # 4GB for real rendering
)
def render_reel(spec_dict: dict, bundle_b64: str):
    """
    Full rendering function.
    
    Args:
        spec_dict: RenderJobSpec as dictionary
        bundle_b64: Base64-encoded ZIP file with assets
    
    Returns:
        dict with job_id, size_bytes, video_b64
    """
    import os
    import zipfile
    import asyncio
    from reel_renderer.types import RenderJobSpec
    from reel_renderer.pipeline import render_reel as do_render_async
    
    print(f"📦 Received render job: {spec_dict.get('job_id', 'unknown')}")
    
    # Set ffmpeg path
    os.environ["IMAGEIO_FFMPEG_EXE"] = "/usr/bin/ffmpeg"
    
    # Create temp workspace
    tmp_dir = Path(tempfile.mkdtemp(prefix="modal_render_"))
    bundle_zip = tmp_dir / "bundle.zip"
    bundle_dir = tmp_dir / "bundle"
    output_video = tmp_dir / "output.mp4"
    
    try:
        # 1. Write bundle ZIP
        bundle_zip.write_bytes(base64.b64decode(bundle_b64))
        print(f"📁 Bundle size: {bundle_zip.stat().st_size} bytes")
        
        # 2. Extract bundle
        bundle_dir.mkdir()
        with zipfile.ZipFile(bundle_zip) as zf:
            zf.extractall(bundle_dir)
        print(f"📂 Extracted to: {bundle_dir}")
        
        # 3. Parse spec and render (async!)
        spec = RenderJobSpec.model_validate(spec_dict)
        print(f"🎬 Starting render: {spec.dimensions.width}x{spec.dimensions.height} @ {spec.dimensions.fps}fps")
        
        # Run async function
        asyncio.run(do_render_async(
            spec=spec,
            bundle_path=bundle_dir,
            output_path=output_video
        ))
        
        # 4. Encode result
        video_bytes = output_video.read_bytes()
        video_b64 = base64.b64encode(video_bytes).decode('utf-8')
        
        print(f"✅ Render complete: {len(video_bytes)} bytes")
        
        return {
            "success": True,
            "job_id": spec.job_id,
            "size_bytes": len(video_bytes),
            "video_b64": video_b64,
            "inline": True
        }
        
    except Exception as e:
        print(f"❌ Render failed: {e}")
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }
    finally:
        # Cleanup
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# Optional: HTTP endpoint for easy testing
@app.function(image=image)
@modal.asgi_app()
def render_endpoint():
    """
    FastAPI endpoint: POST /render with JSON {spec, bundle_b64}
    Returns the render result.
    """
    from fastapi import FastAPI
    
    web_app = FastAPI()
    
    @web_app.post("/render")
    async def render(data: dict):
        spec = data.get("spec")
        bundle_b64 = data.get("bundle_b64")
        
        if not spec or not bundle_b64:
            return {"error": "Missing 'spec' or 'bundle_b64'"}
        
        # Call the rendering function
        result = render_reel.remote(spec, bundle_b64)
        return result
    
    return web_app


# For local testing
@app.local_entrypoint()
def main():
    """Test the ffmpeg function locally."""
    print("🧪 Testing ffmpeg function...")
    result = test_ffmpeg.remote()
    
    if result["success"]:
        print(f"✅ Success! Video size: {result['size_bytes']} bytes")
        
        # Optionally save to file
        output_path = Path("test_output.mp4")
        video_bytes = base64.b64decode(result["video_b64"])
        output_path.write_bytes(video_bytes)
        print(f"💾 Saved to: {output_path}")
    else:
        print(f"❌ Failed: {result.get('error')}")
