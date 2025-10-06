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
Full rendering function with MoviePy pipeline.

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
Default: 600 seconds (10 minutes)

Change in `modal_app.py`:
```python
@app.function(
    image=image,
    timeout=1200,  # 20 minutes
)
```

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
Add GPU for faster rendering:
```python
@app.function(
    image=image,
    gpu="T4",  # or "A10G", "A100"
)
```

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
