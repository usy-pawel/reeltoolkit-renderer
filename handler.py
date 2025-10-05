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
  "video_b64": "..."
}

The handler uses the same pipeline used by the FastAPI app. It is intended for
small / moderate reels. Large outputs might exceed RunPod limits; in that case
switch to the HTTP streaming service route.
"""
from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

import runpod
import asyncio

from reel_renderer import RenderJobSpec, render_reel


def _write_base64_zip(data_b64: str, dest: Path) -> None:
    raw = base64.b64decode(data_b64)
    dest.write_bytes(raw)


def _load_spec(payload: Dict[str, Any]) -> RenderJobSpec:
    if "spec" not in payload:
        raise ValueError("missing 'spec' field")
    spec_raw = payload["spec"]
    if isinstance(spec_raw, str):
        return RenderJobSpec.model_validate_json(spec_raw)
    return RenderJobSpec.model_validate(spec_raw)


async def handler_async(job: Dict[str, Any]) -> Dict[str, Any]:
    """Core async logic for rendering. Processes job["input"] per RunPod convention."""
    job_input = job["input"]

    spec = _load_spec(job_input)
    bundle_b64 = job_input.get("bundle_b64")
    if not bundle_b64:
        raise ValueError("'bundle_b64' required (base64 zip with assets)")

    expected_token = os.getenv("RENDER_AUTH_TOKEN")
    provided_token = job_input.get("auth_token")
    if expected_token and provided_token != expected_token:
        raise PermissionError("invalid or missing auth token")

    with tempfile.TemporaryDirectory(prefix=f"srv_{spec.job_id}_") as td:
        temp_dir = Path(td)
        bundle_path = temp_dir / "bundle.zip"
        _write_base64_zip(bundle_b64, bundle_path)
        output_path = temp_dir / spec.output_name
        final_file = await render_reel(spec, bundle_path, output_path)
        data = final_file.read_bytes()
        return {
            "job_id": spec.job_id,
            "size_bytes": len(data),
            "video_b64": base64.b64encode(data).decode("utf-8"),
        }


def handler(job: Dict[str, Any]) -> Dict[str, Any]:
    """Sync wrapper matching RunPod docs pattern: def handler(job)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        return asyncio.ensure_future(handler_async(job))  # type: ignore[return-value]
    return asyncio.run(handler_async(job))

runpod.serverless.start({"handler": handler})
