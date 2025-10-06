"""RunPod handler with Pydantic validation - NO rendering yet."""
import runpod
import logging
import sys
from typing import Any, Dict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def _load_spec(payload: Dict[str, Any]):
    """Lazy import RenderJobSpec only when needed for validation."""
    from reel_renderer import RenderJobSpec
    
    spec_raw = payload.get("spec")
    if spec_raw is None:
        raise ValueError("missing 'spec' field")
    
    if isinstance(spec_raw, str):
        return RenderJobSpec.model_validate_json(spec_raw)
    return RenderJobSpec.model_validate(spec_raw)


def handler(job):
    """Handler with Pydantic validation but no actual rendering."""
    logger.info(f"Handler received job: {job.get('id', 'unknown')}")
    
    # Handle empty job or None
    ji = (job or {}).get("input") or {}
    
    # Healthcheck - empty input or ping both pass
    if not ji or ji.get("ping"):
        logger.info("Health check - responding with ready status")
        return {"ok": True, "ready": True}
    
    # Test Pydantic validation
    try:
        spec = _load_spec(ji)
        logger.info(f"✅ Pydantic validation successful: job_id={spec.job_id}")
        
        # Return spec info without rendering
        return {
            "ok": True,
            "validated": True,
            "job_id": spec.job_id,
            "output_name": spec.output_name,
            "dimensions": {
                "width": spec.dimensions.width,
                "height": spec.dimensions.height,
                "fps": spec.dimensions.fps
            },
            "slides_count": len(spec.slides),
            "message": "Validation successful - rendering not implemented yet"
        }
    except Exception as e:
        logger.error(f"❌ Validation failed: {e}")
        return {
            "ok": False,
            "error": str(e),
            "error_type": type(e).__name__
        }


# Start worker at module level
logger.info("Starting RunPod worker with Pydantic validation...")
runpod.serverless.start({"handler": handler})
