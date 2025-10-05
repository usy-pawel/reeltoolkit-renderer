"""Minimal RunPod handler for sanity check."""
import runpod

def handler(job):
    """Super lightweight handler for testing RunPod Serverless configuration."""
    # Handle empty job or None
    ji = (job or {}).get("input") or {}
    
    # Healthcheck - empty input or ping both pass
    if not ji or ji.get("ping"):
        return {"ok": True, "ready": True}
    
    # Echo whatever was sent
    return {"echo": ji}

# Start worker at module level
runpod.serverless.start({"handler": handler})
