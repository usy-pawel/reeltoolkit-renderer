"""RunPod serverless handler for ReelToolkit Renderer.

This exposes a single `reel.render` endpoint. Input JSON:
{
  "spec": <RenderJobSpec JSON>,
  "bundle_b64": "<base64 zip file of assets>",
  "auth_token": "optional override token"
}

Returns JSON with keys:
{
  "job_id": str,
  "size_bytes": int,
  "video_b64": "...",  (if inline=True)
  "inline": bool
}

The handler uses the same pipeline used by the FastAPI app. It is intended for
small / moderate reels. Large outputs might exceed RunPod limits; in that case
switch to the HTTP streaming service route or provide put_url for upload.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

import runpod

from reel_renderer import RenderJobSpec, render_reel

# Configure logging for RunPod
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

MAX_INLINE_BYTES = int(os.getenv("MAX_INLINE_BYTES", str(25 * 1024 * 1024)))  # 25MB default


def _write_base64_zip(data_b64: str, dest: Path) -> None:
    dest.write_bytes(base64.b64decode(data_b64))


def _load_spec(payload: Dict[str, Any]) -> RenderJobSpec:
    spec_raw = payload.get("spec")
    if spec_raw is None:
        raise ValueError("missing 'spec' field")
    if isinstance(spec_raw, str):
        return RenderJobSpec.model_validate_json(spec_raw)
    return RenderJobSpec.model_validate(spec_raw)


async def handler_async(job: Dict[str, Any]) -> Dict[str, Any]:
    """Core async logic for rendering. Processes job["input"] per RunPod convention."""
    logger.info(f"Handler received job: {job.get('id', 'unknown')}")
    job_input = job.get("input") or {}  # RunPod can send None

    # Healthcheck for RunPod "Testing" (empty input or ping should pass)
    if not job_input or job_input.get("ping"):
        logger.info("Health check - responding with ready status")
        return {"ok": True, "ready": True}

    # Auth check (optional - only if RENDER_AUTH_TOKEN is set)
    expected_token = os.getenv("RENDER_AUTH_TOKEN")
    provided_token = job_input.get("auth_token")
    if expected_token and provided_token != expected_token:
        logger.error("Authentication failed: invalid token")
        raise PermissionError("invalid or missing auth token")

    spec = _load_spec(job_input)
    logger.info(f"Loaded spec for job_id: {spec.job_id}")
    
    bundle_b64 = job_input.get("bundle_b64")
    if not bundle_b64:
        logger.error("Missing bundle_b64 in job input")
        raise ValueError("'bundle_b64' required (base64 zip with assets)")

    logger.info(f"Processing bundle (size: {len(bundle_b64)} chars base64)")
    with tempfile.TemporaryDirectory(prefix=f"srv_{spec.job_id}_") as td:
        temp_dir = Path(td)
        logger.info(f"Created temp directory: {temp_dir}")
        
        bundle_path = temp_dir / "bundle.zip"
        _write_base64_zip(bundle_b64, bundle_path)
        logger.info(f"Wrote bundle to: {bundle_path}")
        
        output_path = temp_dir / spec.output_name
        logger.info(f"Starting render to: {output_path}")
        
        final_file = await render_reel(spec, bundle_path, output_path)
        logger.info(f"Render complete: {final_file}")
        
        data = final_file.read_bytes()
        logger.info(f"Output size: {len(data)} bytes")

        # Protect against oversized responses
        if len(data) <= MAX_INLINE_BYTES:
            return {
                "job_id": spec.job_id,
                "size_bytes": len(data),
                "video_b64": base64.b64encode(data).decode("utf-8"),
                "inline": True,
            }
        else:
            # Result too big for inline response - would need upload to storage
            return {
                "job_id": spec.job_id,
                "size_bytes": len(data),
                "inline": False,
                "error": f"result too big for inline (> {MAX_INLINE_BYTES} bytes). Consider providing put_url.",
            }


def handler(job: Dict[str, Any]) -> Dict[str, Any]:
    """Sync wrapper matching RunPod docs pattern. Always uses asyncio.run."""
    logger.info("Handler called (sync wrapper)")
    return asyncio.run(handler_async(job))


# CRITICAL: Start worker at module level, not under __main__
# RunPod Serverless imports the module, doesn't run it as __main__
logger.info("Initializing RunPod serverless worker at module level...")
logger.info(f"Python version: {sys.version}")
logger.info(f"Working directory: {os.getcwd()}")
logger.info(f"RENDER_TEMP_ROOT: {os.getenv('RENDER_TEMP_ROOT', 'not set')}")

runpod.serverless.start({"handler": handler})
