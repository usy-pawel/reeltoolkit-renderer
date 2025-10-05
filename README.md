# ReelToolkit Renderer

[![CI](https://github.com/<your-org>/reeltoolkit-renderer/actions/workflows/ci.yml/badge.svg)](https://github.com/<your-org>/reeltoolkit-renderer/actions/workflows/ci.yml)
[![Runpod](https://api.runpod.io/badge/usy-pawel/reeltoolkit-renderer)](https://console.runpod.io/hub/usy-pawel/reeltoolkit-renderer)

Dedicated GPU-friendly rendering service that turns prepared slide bundles into final MP4 reels. The service exposes a small FastAPI endpoint, and it can also be invoked as a reusable Python library from the monolithic backend during local development.

## Features

- 🚀 Parallel FFmpeg-based slide rendering with MoviePy fallback
- 🔥 Subtitle burn-in (ASS/SRT) and optional tail concatenation
- 🎚️ Global background music mixing with ducking & masked mute ranges
- 📦 Zip bundle ingestion so upstream systems keep control of asset downloads
- 🌐 FastAPI service ready for RunPod or any GPU-enabled host

## Quick start

```bash
# Install dependencies
uv venv .venv
source .venv/bin/activate  # (use .venv\Scripts\activate on Windows)
pip install -e .

# Run the service
render-service --host 0.0.0.0 --port 8080
```

Send a request:

```bash
curl -X POST http://localhost:8080/render/reel \
  -H "Authorization: Bearer <TOKEN>" \
  -F "payload=@payload.json" \
  -F "bundle=@workspace.zip" \
  -o output.mp4
```

## Repository setup

```bash
# from the workspace root
cd reeltoolkit-renderer
git init
git remote add origin git@github.com:<your-org>/reeltoolkit-renderer.git
git add .
git commit -m "feat: initial GPU renderer"
git push -u origin main
```

After pushing, enable Actions in the GitHub UI so the CI workflow can run on pull requests.

Ship the package to other projects with:

```bash
pip install git+ssh://git@github.com/<your-org>/reeltoolkit-renderer.git
```

## Repository layout

```
reel_renderer/        # Reusable pipeline module (`render_reel`)
renderer_service/     # FastAPI application & server bootstrap
tests/                # Lightweight contract & pipeline tests
```

## Deployment

1. Build the container image (`docker build -t your-org/reeltoolkit-renderer .`). The multistage Dockerfile now compiles FFmpeg `6.1.1` with `nv-codec-headers`, enabling NVENC/NPP support. You can override the version with `--build-arg FFMPEG_VERSION=6.1.1`.
2. Provide the service with GPU access if you expect to use accelerated encoders.
3. Configure environment variables:
  - `RENDER_AUTH_TOKEN`: optional bearer token shared with the backend.
  - `RENDER_MAX_WORKERS`: override default FFmpeg concurrency.
  - `RENDER_TEMP_ROOT`: mount point for working directories (defaults to system temp).
4. Expose `/render/reel` and stream responses back to the backend.
5. **RunPod quick start**:
  - Create a new RunPod template using the CUDA Base image or your FFmpeg-enabled container.
  - Mount persistent storage for `/var/reeltoolkit/work` if you want to inspect bundles.
  - Set the environment variables above in the RunPod dashboard.
  - Point a webhook or TCP load balancer at the pod’s public endpoint and record the base URL for `RENDER_SERVICE_URL`.
  6. To run the container locally with GPU acceleration:

  ```bash
  docker run \
    --gpus all \
    -p 8080:8080 \
    -e RENDER_AUTH_TOKEN=super-secret-token \
    -e RENDER_MAX_WORKERS=16 \
    -v $(pwd)/work:/var/reeltoolkit/work \
    your-org/reeltoolkit-renderer
  ```

  Verify NVENC is available inside the running container:

  ```bash
  ffmpeg -hide_banner -encoders | grep nvenc
  ```

### RunPod Serverless (handler)

The repository includes a `handler.py` compatible with RunPod Serverless. It exposes a single function endpoint that accepts a JSON payload with a base64-encoded zip bundle and a render spec. After deploying to the Hub, you can invoke it like:

```jsonc
{
  "input": {
    "spec": {
      "job_id": "demo-1",
      "output_name": "render.mp4",
      "dimensions": {"width": 720, "height": 1280, "fps": 30},
      "background_color": "#000000",
      "render": {"use_parallel": false, "quality": "draft"},
      "slides": [
        {"image": "slide1.png", "audio": "slide1.mp3"}
      ]
    },
    "bundle_b64": "<base64 zip containing slide1.png & slide1.mp3>",
    "auth_token": "<optional if RENDER_AUTH_TOKEN set>"
  }
}
```

The response contains `video_b64` with the rendered MP4 (base64) if the output is smaller than `MAX_INLINE_BYTES` (default 25MB). For larger outputs, the handler returns `inline: false` with an error message. In production, consider providing a `put_url` (presigned upload URL) in the input to upload large results to cloud storage instead of returning them inline.

**Environment variables:**
- `RENDER_AUTH_TOKEN` – optional bearer token for job authorization
- `MAX_INLINE_BYTES` – max size (bytes) for inline base64 response (default: 26214400)
- `RENDER_MAX_WORKERS` – FFmpeg parallel worker count (default: 16)

## Development roadmap

- [x] Container image with NVIDIA FFmpeg build
- [ ] Metrics endpoint (Prometheus)
- [ ] Health and readiness probes
- [ ] Expanded test suite with golden MP4 fixtures

## License

MIT License – see parent repository.
