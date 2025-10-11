# ReelToolkit Renderer

[![CI](https://github.com/<your-org>/reeltoolkit-renderer/actions/workflows/ci.yml/badge.svg)](https://github.com/<your-org>/reeltoolkit-renderer/actions/workflows/ci.yml)

Serverless video rendering service powered by FFmpeg and MoviePy. Deploy to Modal.com for fast, scalable video generation with ~2s cold starts.

## Features

- 🚀 **Serverless:** Deploy to Modal.com with instant scaling
- ⚡ **Fast:** ~2s cold starts, no container warm-up
- 🎬 **FFmpeg-based:** Pure FFmpeg rendering for reliability
- 📦 **Zip bundles:** Upload assets as base64-encoded zips
- 🌐 **Dual interface:** Python SDK or HTTP endpoint
- 💰 **Cost-effective:** Pay per second, ~$0.002/minute

## Quick start - Modal Deployment

### 1. Install and authenticate

```bash
pip install modal
modal token new  # Opens browser for authentication
```

### 2. Deploy

```bash
cd reeltoolkit-renderer
modal deploy modal_app_simple.py
```

### 3. Test

```bash
# CLI test
modal run modal_app_simple.py

# Or call from Python
import modal

test_fn = modal.Function.lookup("reeltoolkit-renderer-simple", "test_ffmpeg")
result = test_fn.remote()
print(f"Video size: {result['size_bytes']} bytes")
```



### 4. Use HTTP endpoint### 4. Use HTTP endpoint

```bash```bash

curl -X POST https://your-endpoint.modal.run/render \curl -X POST https://your-endpoint.modal.run/render \

  -H "Content-Type: application/json" \  -H "Content-Type: application/json" \

  -d '{"width": 1080, "height": 1920, "duration": 3, "color": "blue"}'  -d '{"width": 1080, "height": 1920, "duration": 3, "color": "blue"}'

``````



📖 **Full docs:** See [MODAL_QUICKSTART.md](MODAL_QUICKSTART.md) and [TODO_MODAL.md](TODO_MODAL.md)📖 **Full docs:** See [MODAL_QUICKSTART.md](MODAL_QUICKSTART.md) and [TODO_MODAL.md](TODO_MODAL.md)

## GPU selection and render resolution

- **Per-request preset** – include `render.gpu_preset` in the job payload. Supported values: `T40`, `L40`, `L40S` (case-insensitive). Example:

  ```json
  {
    "spec": {
      "job_id": "vip-render",
      "dimensions": {"width": 1080, "height": 1920, "fps": 30},
      "render": {
        "quality": "final",
        "gpu_preset": "L40S"
      },
      "slides": []
    },
    "bundle_b64": "..."
  }
  ```

- **Deployment default** – set the `MODAL_RENDER_GPU` variable before `modal deploy` to choose the fallback preset (for requests that omit `render.gpu_preset`).

  ```bash
  export MODAL_RENDER_GPU=L40
  modal deploy modal_app.py
  ```

- **Resolution override** – incoming jobs provide `dimensions.width` and `dimensions.height`, but the Modal renderer forces a target width of 360 px (function `_override_dimensions` in `modal_app.py`). Height is rescaled to keep the aspect ratio and both dimensions are rounded to even numbers (codec requirement).

  > To render in a different base width, adjust the `target_width` argument or disable the override logic in `_override_dimensions`.



## Local Development## Local Development



### Run FastAPI service locally### Run FastAPI service locally

```bash```bash

# Install dependencies# Install dependencies

pip install -e .pip install -e .



# Run the service# Run the service

render-service --host 0.0.0.0 --port 8080render-service --host 0.0.0.0 --port 8080

``````



### Test with curl### Test with curl

```bash```bash

curl -X POST http://localhost:8080/render/reel \curl -X POST http://localhost:8080/render/reel \

  -H "Authorization: Bearer <TOKEN>" \  -H "Authorization: Bearer <TOKEN>" \

  -F "payload=@payload.json" \  -F "payload=@payload.json" \

  -F "bundle=@workspace.zip" \  -F "bundle=@workspace.zip" \

  -o output.mp4  -o output.mp4

``````



## Repository layout## Repository layout



``````

reel_renderer/        # Reusable pipeline module (render_reel)reel_renderer/        # Reusable pipeline module (render_reel)

renderer_service/     # FastAPI application (local dev)renderer_service/     # FastAPI application (local dev)

modal_app_simple.py   # Modal deployment (FFmpeg only) ✅modal_app_simple.py   # Modal deployment (FFmpeg only)

modal_app.py          # Modal deployment (full pipeline, WIP)modal_app.py          # Modal deployment (full pipeline, WIP)

tests/                # Teststests/                # Tests

``````



## Deployment Options## Deployment Options



### 1. Modal.com (Recommended) ⭐1. Build the container image (`docker build -t your-org/reeltoolkit-renderer .`). The multistage Dockerfile now compiles FFmpeg `6.1.1` with `nv-codec-headers`, enabling NVENC/NPP support. You can override the version with `--build-arg FFMPEG_VERSION=6.1.1`.

2. Provide the service with GPU access if you expect to use accelerated encoders.

**Pros:**3. Configure environment variables:

- ✅ Instant deploy (~3 seconds)  - `RENDER_AUTH_TOKEN`: optional bearer token shared with the backend.

- ✅ Fast cold starts (~2 seconds)  - `RENDER_MAX_WORKERS`: override default FFmpeg concurrency.

- ✅ Pay per second  - `RENDER_TEMP_ROOT`: mount point for working directories (defaults to system temp).

- ✅ Python-native API4. Expose `/render/reel` and stream responses back to the backend.

- ✅ Auto-scaling5. **RunPod quick start**:

  - Create a new RunPod template using the CUDA Base image or your FFmpeg-enabled container.

**Deploy:**  - Mount persistent storage for `/var/reeltoolkit/work` if you want to inspect bundles.

```bash  - Set the environment variables above in the RunPod dashboard.

pip install modal  - Point a webhook or TCP load balancer at the pod’s public endpoint and record the base URL for `RENDER_SERVICE_URL`.

modal token new  6. To run the container locally with GPU acceleration:

modal deploy modal_app_simple.py

```  ```bash

  docker run \

📖 See [MODAL_QUICKSTART.md](MODAL_QUICKSTART.md) for details.    --gpus all \

    -p 8080:8080 \

### 2. Self-hosted / Local    -e RENDER_AUTH_TOKEN=super-secret-token \

    -e RENDER_MAX_WORKERS=16 \

Run the FastAPI service:    -v $(pwd)/work:/var/reeltoolkit/work \

```bash    your-org/reeltoolkit-renderer

pip install -e .  ```

render-service --host 0.0.0.0 --port 8080

```  Verify NVENC is available inside the running container:



### 3. Other platforms  ```bash

  ffmpeg -hide_banner -encoders | grep nvenc

The FastAPI service (`renderer_service/`) can run on:  ```

- AWS Lambda (with Docker)

- Google Cloud Run### RunPod Serverless (handler)

- Azure Container Instances

- Any Kubernetes clusterThe repository includes a `handler.py` compatible with RunPod Serverless. It exposes a single function endpoint that accepts a JSON payload with a base64-encoded zip bundle and a render spec. After deploying to the Hub, you can invoke it like:



## Development```jsonc

{

### Run tests  "input": {

```bash    "spec": {

pytest tests/      "job_id": "demo-1",

```      "output_name": "render.mp4",

      "dimensions": {"width": 720, "height": 1280, "fps": 30},

### Install for development      "background_color": "#000000",

```bash      "render": {"use_parallel": false, "quality": "draft"},

pip install -e .      "slides": [

```        {"image": "slide1.png", "audio": "slide1.mp3"}

      ]

## Documentation    },

    "bundle_b64": "<base64 zip containing slide1.png & slide1.mp3>",

- [MODAL_QUICKSTART.md](MODAL_QUICKSTART.md) - Quick start guide for Modal    "auth_token": "<optional if RENDER_AUTH_TOKEN set>"

- [MODAL_DEPLOYMENT.md](MODAL_DEPLOYMENT.md) - Detailed Modal deployment docs  }

- [TODO_MODAL.md](TODO_MODAL.md) - Current status and next steps}

- [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guidelines```



## LicenseThe response contains `video_b64` with the rendered MP4 (base64) if the output is smaller than `MAX_INLINE_BYTES` (default 25MB). For larger outputs, the handler returns `inline: false` with an error message. In production, consider providing a `put_url` (presigned upload URL) in the input to upload large results to cloud storage instead of returning them inline.



MIT License – see parent repository.**Environment variables:**

- `RENDER_AUTH_TOKEN` – optional bearer token for job authorization
- `MAX_INLINE_BYTES` – max size (bytes) for inline base64 response (default: 26214400)
- `RENDER_MAX_WORKERS` – FFmpeg parallel worker count (default: 16)

## Docker Image

Docker images are automatically built and published to GitHub Container Registry on every release:

```bash
# Pull the latest image
docker pull ghcr.io/usy-pawel/reeltoolkit-renderer:latest

# Or specific version
docker pull ghcr.io/usy-pawel/reeltoolkit-renderer:0.1.8

# Run locally
docker run --gpus all -p 8080:8080 \
  -e RENDER_AUTH_TOKEN=your-token \
  ghcr.io/usy-pawel/reeltoolkit-renderer:latest
```

See [RUNPOD_DEPLOYMENT.md](./RUNPOD_DEPLOYMENT.md) for detailed deployment instructions and troubleshooting.

## Development roadmap

- [x] Container image with NVIDIA FFmpeg build
- [x] Automated Docker builds on release
- [ ] Metrics endpoint (Prometheus)
- [ ] Health and readiness probes
- [ ] Expanded test suite with golden MP4 fixtures

## License

MIT License – see parent repository.
