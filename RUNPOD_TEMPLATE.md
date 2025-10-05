# RunPod Template Configuration

## Image Configuration

**Container Image:**
```
ghcr.io/usy-pawel/reeltoolkit-renderer:latest
```

Or use specific version (recommended for production):
```
ghcr.io/usy-pawel/reeltoolkit-renderer:0.1
```

## For RunPod Serverless

### Basic Settings
- **Template Name**: `reeltoolkit-renderer`
- **Container Image**: `ghcr.io/usy-pawel/reeltoolkit-renderer:latest`
- **Container Start Command**: 
  ```bash
  python3 handler.py
  ```
- **Container Disk**: `20 GB` (minimum)

### Environment Variables
```env
RENDER_AUTH_TOKEN=your-secret-token-here
MAX_INLINE_BYTES=26214400
RENDER_MAX_WORKERS=16
RENDER_TEMP_ROOT=/runpod-volume
```

### GPU Configuration
- **GPU Type**: Any NVIDIA GPU with CUDA support
- **GPU Count**: 1
- **Min vRAM**: 8 GB (recommended)

### Advanced Settings
- **Container Startup Timeout**: `300` seconds
- **Idle Timeout**: `300` seconds
- **Execution Timeout**: `3600` seconds (adjust based on your video length)

### Network Configuration
- **Active Workers**: 0 (serverless auto-scales)
- **Max Workers**: Set based on your needs

## For RunPod Pods (HTTP Service)

### Basic Settings
- **Template Name**: `reeltoolkit-renderer-http`
- **Container Image**: `ghcr.io/usy-pawel/reeltoolkit-renderer:latest`
- **Docker Command**: (leave default or use)
  ```bash
  uvicorn renderer_service.app:app --host 0.0.0.0 --port 8080
  ```
- **Container Disk**: `20 GB`

### Environment Variables
```env
RENDER_AUTH_TOKEN=your-secret-token-here
RENDER_MAX_WORKERS=16
RENDER_TEMP_ROOT=/workspace
```

### Exposed Ports
```
8080/http
```

### GPU Configuration
- **GPU Type**: Any NVIDIA GPU
- **GPU Count**: 1

### Volume Mounts (Optional)
```
Container Path: /workspace
```

## Quick Start Commands

### Test Serverless Endpoint
```bash
curl -X POST https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/runsync \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_RUNPOD_API_KEY" \
  -d '{
    "input": {
      "spec": {
        "job_id": "test-1",
        "output_name": "test.mp4",
        "dimensions": {"width": 720, "height": 1280, "fps": 30},
        "slides": []
      },
      "bundle_b64": "UEsDBBQAAAAIAA==",
      "auth_token": "your-secret-token-here"
    }
  }'
```

### Test HTTP Service
```bash
curl http://YOUR_POD_IP:8080/health
```

## Verification Steps

1. **Check image is available**:
   ```bash
   docker pull ghcr.io/usy-pawel/reeltoolkit-renderer:latest
   ```

2. **Verify NVENC support** (from RunPod terminal):
   ```bash
   ffmpeg -hide_banner -encoders | grep nvenc
   ```

3. **Test handler** (serverless):
   ```bash
   python3 -c "import runpod; print('RunPod SDK:', runpod.__version__)"
   ```

## Troubleshooting

### Issue: Pod stuck on "Pending"
**Solutions**:
1. Ensure image is set to Public in GitHub Container Registry
2. Check GPU availability in your region
3. Increase container startup timeout to 300s
4. Verify image tag exists: https://github.com/usy-pawel/reeltoolkit-renderer/pkgs/container/reeltoolkit-renderer

### Issue: "Failed to pull image"
**Solutions**:
1. Make package public: GitHub → Packages → reeltoolkit-renderer → Package settings → Change visibility → Public
2. Check image URL is correct (no typos)
3. Try with `:latest` tag instead of specific version

### Issue: "NVENC not available"
**Solutions**:
1. Ensure you selected GPU pod (not CPU)
2. Verify CUDA is enabled in RunPod settings
3. Check GPU type supports NVENC (most modern NVIDIA GPUs do)

### Issue: "Module not found" errors
**Solutions**:
1. Image may still be pulling (check startup timeout)
2. Verify correct start command (`python3 handler.py` for serverless)
3. Check logs for build errors

## Image Tags Strategy

- **`:latest`** - Always the newest build from `main` branch (auto-updates)
- **`:0.1`** - Latest patch in 0.1.x series (e.g., 0.1.9)
- **`:0.1.9`** - Specific version (pinned, won't change)
- **`:main-abc123`** - Specific commit from main branch

**Recommendation**: Use `:0.1` for automatic patch updates while maintaining compatibility.
