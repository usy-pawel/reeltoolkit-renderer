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
    
    # NOW import heavy stuff (lazy load after healthcheck)
    import asyncio
    import base64
    import tempfile
    from pathlib import Path
    from typing import Dict, Any
    
    from reel_renderer import RenderJobSpec
    from reel_renderer.rendering import render_reel
    
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
                
                # Render the video
                logger.info(f"Starting render for {spec.job_id}")
                result_path = await render_reel(spec, bundle_path, output_path)
                logger.info(f"Render complete: {result_path}")
                
                # Read result
                video_data = result_path.read_bytes()
                video_b64 = base64.b64encode(video_data).decode('ascii')
                
                logger.info(f"Returning video: {len(video_data)} bytes")
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

