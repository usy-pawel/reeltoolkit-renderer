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


def handler(event: Dict[str, Any]) -> Dict[str, Any]:  # type: ignore[override]
    payload = event.get("input") or event

    spec = _load_spec(payload)
    bundle_b64 = payload.get("bundle_b64")
    if not bundle_b64:
        raise ValueError("'bundle_b64' required (zip with assets)")

    auth_override = payload.get("auth_token")
    expected_token = os.getenv("RENDER_AUTH_TOKEN")
    if expected_token and auth_override and auth_override != expected_token:
        raise PermissionError("invalid auth token override")

    with tempfile.TemporaryDirectory(prefix=f"srv_{spec.job_id}_") as td:
        temp_dir = Path(td)
        bundle_path = temp_dir / "bundle.zip"
        _write_base64_zip(bundle_b64, bundle_path)
        output_path = temp_dir / spec.output_name
        final_path = runpod.serverless.utils.rp_run.sync_to_async(
            render_reel
        )  # type: ignore[attr-defined]
        # Above helper not always present; fall back to direct await if needed
        # but render_reel is async so we simply await it below.
        # Actually we just call it directly as it's already async.
        # Keeping placeholder for potential future synch calls.
        import asyncio
        final_file = asyncio.run(
            render_reel(spec, bundle_path, output_path)
        )
        data = final_file.read_bytes()
        return {
            "job_id": spec.job_id,
            "size_bytes": len(data),
            "video_b64": base64.b64encode(data).decode("utf-8"),
        }


runpod.serverless.start({"handler": handler})
