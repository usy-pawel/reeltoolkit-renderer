"""Minimal handler - NO imports except runpod."""
import runpod

def handler(job):
    """Minimal handler for testing if Pydantic in requirements breaks anything."""
    ji = (job or {}).get("input") or {}
    if not ji or ji.get("ping"):
        return {"ok": True, "ready": True}
    return {"echo": ji}

runpod.serverless.start({"handler": handler})
