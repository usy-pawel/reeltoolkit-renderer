# Modal.com Deployment Guide

## 🚀 Quick Start

### 1. Install Modal
```bash
pip install modal
```

### 2. Authenticate
```bash
modal token new
```
This opens a browser to authenticate with your Modal account.

### 3. Deploy
```bash
modal deploy modal_app.py
```

### 4. Test
```bash
# Test the ffmpeg function
modal run modal_app.py

# Or call a specific function
modal run modal_app.py::test_ffmpeg
```

---

## 📦 Available Functions

### `test_ffmpeg()`
Simple test function - generates 1-second black video using ffmpeg.

**Call from Python:**
```python
import modal

app = modal.App.lookup("reeltoolkit-renderer", create_if_missing=False)
test_fn = modal.Function.lookup("reeltoolkit-renderer", "test_ffmpeg")

result = test_fn.remote()
print(result)
```

**Call from CLI:**
```bash
modal run modal_app.py::test_ffmpeg
```

---

### `render_reel(spec_dict, bundle_b64)`
Smart entry point that auto-selects the GPU tier per render.

**Call from Python:**
```python
import modal
import base64

app = modal.App.lookup("reeltoolkit-renderer", create_if_missing=False)
render_fn = modal.Function.lookup("reeltoolkit-renderer", "render_reel")

# Prepare your data
spec = {
    "job_id": "test-001",
    "output_name": "output.mp4",
    "dimensions": {"width": 1080, "height": 1920, "fps": 30},
    "background_color": "#000000",
    "render": {"use_parallel": False, "quality": "final"},
    "slides": []
}

# Read bundle ZIP and encode
with open("bundle.zip", "rb") as f:
    bundle_b64 = base64.b64encode(f.read()).decode('utf-8')

# Call the function
result = render_fn.remote(spec, bundle_b64)
print(f"Job ID: {result['job_id']}")
print(f"Size: {result['size_bytes']} bytes")

# Decode and save video
video_bytes = base64.b64decode(result['video_b64'])
with open("output.mp4", "wb") as f:
    f.write(video_bytes)
```

---

### `render_endpoint()` (HTTP)
HTTP endpoint for easy integration.

**After deployment, Modal gives you a URL like:**
```
https://yourname--reeltoolkit-renderer-render-endpoint.modal.run
```

**Call with curl:**
```bash
curl -X POST https://yourname--reeltoolkit-renderer-render-endpoint.modal.run \
  -H "Content-Type: application/json" \
  -d '{
    "spec": {
      "job_id": "test-001",
      "output_name": "output.mp4",
      "dimensions": {"width": 1080, "height": 1920, "fps": 30},
      "background_color": "#000000",
      "render": {"use_parallel": false, "quality": "final"},
      "slides": []
    },
    "bundle_b64": "UEsDBBQAAAAIAA..."
  }'
```

---

## 🔧 Configuration

### Timeout
Default GPU render timeout: **1800 seconds (30 minutes)**. The dispatcher function waits slightly longer to accommodate result delivery.

Override timeouts at deploy time with environment variables:

```bash
export MODAL_GPU_TIMEOUT_SECONDS=2400               # GPU worker timeout
export MODAL_RENDER_TIMEOUT_SECONDS=2700            # Dispatcher timeout (optional)
modal deploy modal_app.py
```

If the dispatcher timeout is omitted or set lower than the GPU timeout, it is automatically bumped to keep the session alive until the GPU job returns.

### Memory
Default: 2GB (test), 4GB (render)

Change in `modal_app.py`:
```python
@app.function(
    image=image,
    memory=8192,  # 8GB
)
```

### GPU Support
GPU tier is selected per request. The renderer reads the optional
`render.gpu_preset` value inside the `spec` payload and dispatches the job to
the matching Modal function. Supported presets: `L4`, `L40S`. Values are
case-insensitive, and aliases such as `L40` or `L4S` automatically normalize to
`L40S`.

If no preset is requested in the payload, the deployment default is used. Set
`MODAL_RENDER_GPU` before running `modal deploy` to change the default tier.

```bash
# Example: request an L40S GPU tier at deploy time
export MODAL_RENDER_GPU=L40S
modal deploy modal_app.py
```

Example request overriding the GPU tier for a single render:

```json
{
  "spec": {
    "job_id": "vip-render",
    "output_name": "output.mp4",
    "dimensions": {"width": 1080, "height": 1920, "fps": 30},
    "render": {
      "quality": "final",
      "use_parallel": false,
  "gpu_preset": "L40S"
    },
    "slides": []
  },
  "bundle_b64": "..."
}
```

If you need a class that is not in the presets (for example `A100-80GB` or
`H100`), set `MODAL_RENDER_GPU` to the exact Modal GPU string and it will be
passed through as-is. Redeploy any time you change the value.

> **Note:** Secrets are injected only when the function runs, so they cannot
> change the GPU tier. Keep `MODAL_RENDER_GPU` in your shell (or `.env`) before
> running `modal deploy`. You can still store the preferred GPU string in the
> `reel-secrets` secret for auditing or runtime logging, but it will not affect
> the compute profile.

### Cost estimation

Each Modal job now prints an estimated GPU cost and returns it to the backend.
By default the code uses ballpark hourly prices for the supported GPU tiers, but
you can override them through environment variables:

```bash
# Override the rate for every GPU
export MODAL_GPU_RATE_USD_PER_HOUR=2.50

# Override a specific GPU tier
export MODAL_GPU_RATE_USD_PER_HOUR_L40=1.10

# Provide a JSON mapping for multiple tiers at once
export MODAL_GPU_RATE_OVERRIDES='{"T40": 0.59, "L40S": 1.95}'
```

Values are interpreted as USD per hour. The renderer logs which source was used
(`default`, `MODAL_GPU_RATE_USD_PER_HOUR`, etc.). If no rate is available it
will log a warning and skip the estimate.

---

## 📊 Monitoring

### View logs
```bash
modal app logs reeltoolkit-renderer
```

### List deployed apps
```bash
modal app list
```

### Stop app
```bash
modal app stop reeltoolkit-renderer
```

---

## 💰 Pricing Notes

Modal charges for:
- **Compute time** (per second, based on CPU/RAM/GPU)
- **Storage** (for volumes, if used)

**Free tier:** Generous free credits each month (~$30)

**Typical costs:**
- CPU (2GB RAM): ~$0.000025/second = ~$0.0015/minute
- 1-minute render ≈ $0.002 (very cheap!)

---

## 🔄 Updating

After code changes:
```bash
modal deploy modal_app.py
```

Modal automatically versions deployments. Rollback:
```bash
modal app stop reeltoolkit-renderer
modal deploy modal_app.py --force
```

---

## 🐛 Troubleshooting

### "App not found"
Redeploy:
```bash
modal deploy modal_app.py
```

### Import errors
Make sure all packages in `modal_app.py` image definition match your local environment.

### ffmpeg not found
Check image definition includes:
```python
.apt_install("ffmpeg")
```

### Timeout errors
Increase timeout or optimize rendering (use parallel mode).

---

## 📚 Resources

- [Modal Docs](https://modal.com/docs)
- [Modal Python SDK](https://modal.com/docs/reference)
- [Pricing](https://modal.com/pricing)
