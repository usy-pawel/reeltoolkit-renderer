"""Simplified Modal app - FFmpeg only, no MoviePy complexity."""
import modal
import base64
import tempfile
import subprocess
from pathlib import Path

# Create Modal app
app = modal.App("reeltoolkit-renderer-simple")

# Simple image with just ffmpeg
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install("fastapi[standard]")
)


@app.function(
    image=image,
    timeout=600,
    memory=2048,
)
def test_ffmpeg():
    """Generate a test video with ffmpeg."""
    print("🎬 Generating test video with ffmpeg...")
    
    tmp_dir = tempfile.mkdtemp(prefix="modal_ffmpeg_")
    out_path = Path(tmp_dir) / "test.mp4"
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", 
        "-i", "color=c=black:s=720x1280:d=1:r=25",
        "-pix_fmt", "yuv420p",
        "-an",
        str(out_path)
    ]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"✅ FFmpeg success")
        
        video_bytes = out_path.read_bytes()
        video_b64 = base64.b64encode(video_bytes).decode('utf-8')
        
        return {
            "success": True,
            "size_bytes": len(video_bytes),
            "video_b64": video_b64
        }
        
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg failed: {e.stderr}")
        return {"success": False, "error": e.stderr}
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.function(image=image, timeout=600, memory=4096)
def render_simple(width: int = 720, height: int = 1280, duration: int = 2, color: str = "red"):
    """
    Simple render: colored video with ffmpeg.
    
    Args:
        width: Video width
        height: Video height  
        duration: Duration in seconds
        color: Background color (red, blue, green, black, etc.)
    
    Returns:
        dict with success, size_bytes, video_b64
    """
    print(f"🎬 Rendering {width}x{height} @ {duration}s, color={color}")
    
    tmp_dir = tempfile.mkdtemp(prefix="modal_render_")
    out_path = Path(tmp_dir) / "output.mp4"
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c={color}:s={width}x{height}:d={duration}:r=25",
        "-pix_fmt", "yuv420p",
        "-an",
        str(out_path)
    ]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"✅ Render complete")
        
        video_bytes = out_path.read_bytes()
        video_b64 = base64.b64encode(video_bytes).decode('utf-8')
        
        return {
            "success": True,
            "size_bytes": len(video_bytes),
            "video_b64": video_b64,
            "specs": {"width": width, "height": height, "duration": duration, "color": color}
        }
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Render failed: {e.stderr}")
        return {"success": False, "error": e.stderr}
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# HTTP endpoint
@app.function(image=image)
@modal.asgi_app()
def web():
    from fastapi import FastAPI
    
    app = FastAPI()
    
    @app.post("/test")
    async def test():
        result = test_ffmpeg.remote()
        return result
    
    @app.post("/render")
    async def render(width: int = 720, height: int = 1280, duration: int = 2, color: str = "red"):
        result = render_simple.remote(width, height, duration, color)
        return result
    
    return app


@app.local_entrypoint()
def main():
    """Test locally."""
    print("🧪 Testing ffmpeg...")
    result = test_ffmpeg.remote()
    
    if result["success"]:
        print(f"✅ Success! {result['size_bytes']} bytes")
        
        output_path = Path("test_simple_output.mp4")
        video_bytes = base64.b64decode(result["video_b64"])
        output_path.write_bytes(video_bytes)
        print(f"💾 Saved to: {output_path}")
    else:
        print(f"❌ Failed: {result.get('error')}")
