"""RunPod serverless handler with lazy imports for heavy dependencies."""
import runpod
import logging
import sys
import os

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


def handler(job):
    """
    RunPod serverless handler with lazy imports.
    Heavy dependencies (moviepy, etc) only loaded after healthcheck.
    """
    ji = (job or {}).get("input") or {}
    
    # Healthcheck - fast path, no imports
    if not ji or ji.get("ping"):
        return {"ok": True, "ready": True}
    
    # After healthcheck - set ffmpeg path to avoid downloads
    os.environ.setdefault("IMAGEIO_FFMPEG_EXE", "/usr/bin/ffmpeg")
    
    # STUB TEST - pure ffmpeg (no moviepy, no imports)
    if ji.get("stub") == "ffmpeg":
        import subprocess
        import uuid
        import base64
        import tempfile
        from pathlib import Path
        
        logger.info("STUB TEST: Generating 1-second video with pure ffmpeg")
        tmp = tempfile.mkdtemp(prefix="stub_")
        out_path = Path(tmp) / "out.mp4"
        
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=720x1280:d=1:r=25",
            "-pix_fmt", "yuv420p", "-an", str(out_path)
        ]
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.info(f"FFmpeg output: {result.stdout}")
            data = out_path.read_bytes()
            video_b64 = base64.b64encode(data).decode()
            
            logger.info(f"STUB TEST SUCCESS: Generated {len(data)} bytes")
            return {
                "job_id": f"stub-{uuid.uuid4()}",
                "size_bytes": len(data),
                "video_b64": video_b64,
                "inline": True,
                "stub": True
            }
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg failed: {e.stderr}")
            return {"error": f"FFmpeg failed: {e.stderr}"}
        except Exception as e:
            logger.error(f"STUB TEST FAILED: {e}", exc_info=True)
            return {"error": str(e)}
    
    # NOW import heavy stuff (lazy load after healthcheck)
    import asyncio
    import base64
    import tempfile
    from pathlib import Path
    from typing import Dict, Any
    
    # Import types first (lightweight)
    from reel_renderer import RenderJobSpec
    
    # Set all ffmpeg env vars to prevent network downloads
    os.environ.setdefault("IMAGEIO_FFMPEG_EXE", "/usr/bin/ffmpeg")
    os.environ.setdefault("MOVIEPY_USE_IMAGEIO_FFMPEG", "1")
    os.environ.setdefault("FFMPEG_BINARY", "/usr/bin/ffmpeg")
    os.environ.setdefault("XDG_CACHE_HOME", "/tmp/.cache")
    
    # Import rendering INSIDE function - super lazy
    logger.info(f"About to import rendering module...")
    from reel_renderer.rendering import render_reel
    logger.info(f"Rendering module imported successfully")
    
    logger.info(f"Processing job: {ji.get('spec', {}).get('job_id', 'unknown')}")
    
    async def process_job() -> Dict[str, Any]:
        """Process the render job asynchronously."""
        try:
            # Validate spec
            spec_data = ji.get("spec")
            if not spec_data:
                return {"error": "Missing 'spec' in input"}
            
            spec = RenderJobSpec(**spec_data)
            logger.info(f"Validated spec for job {spec.job_id}")
            
            # Decode bundle
            bundle_b64 = ji.get("bundle_b64", "")
            if not bundle_b64:
                return {"error": "Missing 'bundle_b64' in input"}
            
            bundle_data = base64.b64decode(bundle_b64)
            
            # Write to temp files
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                
                bundle_path = tmpdir_path / "bundle.zip"
                bundle_path.write_bytes(bundle_data)
                logger.info(f"Wrote bundle: {len(bundle_data)} bytes")
                
                output_path = tmpdir_path / spec.output_name
                
                # Render the video with HARD TIMEOUT
                logger.info(f"Starting render_reel for job {spec.job_id}")
                logger.info(f"Bundle size: {len(bundle_data)} bytes, Output: {output_path}")
                
                try:
                    result_path = await asyncio.wait_for(
                        render_reel(spec, bundle_path, output_path),
                        timeout=120  # Hard 120s timeout to prevent hanging
                    )
                    logger.info(f"render_reel finished successfully: {result_path}")
                except asyncio.TimeoutError:
                    logger.error(f"render_reel TIMED OUT after 120s for job {spec.job_id}")
                    return {
                        "job_id": spec.job_id,
                        "inline": False,
                        "error": "render timed out after 120s"
                    }
                
                # Read result
                video_data = result_path.read_bytes()
                video_b64 = base64.b64encode(video_data).decode('ascii')
                
                logger.info(f"Returning video: {len(video_data)} bytes for job {spec.job_id}")
                return {
                    "inline": True,
                    "video_b64": video_b64,
                    "size_bytes": len(video_data),
                    "job_id": spec.job_id
                }
                
        except Exception as e:
            logger.error(f"Render failed: {e}", exc_info=True)
            return {"error": str(e)}
    
    # Run async function
    return asyncio.run(process_job())


runpod.serverless.start({"handler": handler})

