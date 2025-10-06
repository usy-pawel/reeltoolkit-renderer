"""RunPod handler with stub rendering - tests async pipeline."""
import runpod
import logging
import sys
import asyncio
import base64
import tempfile
from pathlib import Path
from typing import Any, Dict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def _load_spec(payload: Dict[str, Any]):
    """Lazy import RenderJobSpec only when needed."""
    from reel_renderer import RenderJobSpec
    
    spec_raw = payload.get("spec")
    if spec_raw is None:
        raise ValueError("missing 'spec' field")
    
    if isinstance(spec_raw, str):
        return RenderJobSpec.model_validate_json(spec_raw)
    return RenderJobSpec.model_validate(spec_raw)


def _write_base64_zip(data_b64: str, dest: Path) -> None:
    """Decode base64 bundle and write to file."""
    dest.write_bytes(base64.b64decode(data_b64))


async def handler_async(job: Dict[str, Any]) -> Dict[str, Any]:
    """Async handler with stub rendering."""
    logger.info(f"Handler received job: {job.get('id', 'unknown')}")
    
    ji = (job or {}).get("input") or {}
    
    # Healthcheck - empty input or ping both pass
    if not ji or ji.get("ping"):
        logger.info("Health check - responding with ready status")
        return {"ok": True, "ready": True}
    
    # Lazy import render_reel (after healthcheck)
    from reel_renderer import render_reel
    
    # Validate spec
    spec = _load_spec(ji)
    logger.info(f"Validated spec: job_id={spec.job_id}")
    
    # Get bundle
    bundle_b64 = ji.get("bundle_b64")
    if not bundle_b64:
        raise ValueError("'bundle_b64' required (base64 zip with assets)")
    
    logger.info(f"Processing bundle (size: {len(bundle_b64)} chars base64)")
    
    # Render (stub - no actual video processing)
    with tempfile.TemporaryDirectory(prefix=f"srv_{spec.job_id}_") as td:
        temp_dir = Path(td)
        logger.info(f"Created temp directory: {temp_dir}")
        
        bundle_path = temp_dir / "bundle.zip"
        _write_base64_zip(bundle_b64, bundle_path)
        logger.info(f"Wrote bundle to: {bundle_path}")
        
        output_path = temp_dir / spec.output_name
        logger.info(f"Starting stub render to: {output_path}")
        
        # Call stub render_reel
        final_file = await render_reel(spec, bundle_path, output_path)
        logger.info(f"Stub render complete: {final_file}")
        
        data = final_file.read_bytes()
        logger.info(f"Output size: {len(data)} bytes")
        
        # Return base64 encoded result
        return {
            "ok": True,
            "job_id": spec.job_id,
            "size_bytes": len(data),
            "video_b64": base64.b64encode(data).decode("utf-8"),
            "message": "Stub render successful - actual rendering not yet implemented"
        }


def handler(job: Dict[str, Any]) -> Dict[str, Any]:
    """Sync wrapper for async handler."""
    logger.info("Handler called (sync wrapper)")
    return asyncio.run(handler_async(job))


# Start worker at module level
logger.info("Starting RunPod worker with stub rendering...")
runpod.serverless.start({"handler": handler})
