# Modal.com Quick Start 🚀

## 1. Install & Setup (5 minutes)

```bash
# Install Modal
pip install modal

# Authenticate (opens browser)
modal token new

# Copy your code to Modal's servers
cd /c/workspace/reeltoolkit-renderer
```

## 2. Deploy (30 seconds)

```bash
modal deploy modal_app.py
```

**✅ That's it!** Modal builds the container, installs ffmpeg and all dependencies.

---

## 3. Test FFmpeg Function

### Option A: CLI Test
```bash
modal run modal_app.py
```

This runs the `test_ffmpeg()` function and saves `test_output.mp4` locally.

### Option B: Python SDK
```python
import modal

# Lookup your deployed function
test_fn = modal.Function.lookup("reeltoolkit-renderer", "test_ffmpeg")

# Call it (runs on Modal's servers)
result = test_fn.remote()

print(f"Video size: {result['size_bytes']} bytes")
```

### Option C: Local test script
```bash
python test_modal_local.py
```

---

## 4. Call from Your App

```python
import modal
import base64

# Lookup the render function
render = modal.Function.lookup("reeltoolkit-renderer", "render_reel")

# Prepare your data
spec = {
    "job_id": "my-video-001",
    "output_name": "output.mp4",
    "dimensions": {"width": 1080, "height": 1920, "fps": 30},
    "background_color": "#000000",
    "render": {"use_parallel": False, "quality": "final"},
    "slides": [
        {
            "duration": 3.0,
            "background": {"type": "color", "value": "#FF0000"}
        }
    ]
}

# Load your asset bundle
with open("bundle.zip", "rb") as f:
    bundle_b64 = base64.b64encode(f.read()).decode()

# Render! (happens on Modal's servers)
result = render.remote(spec, bundle_b64)

# Save the video
if result["success"]:
    video = base64.b64decode(result["video_b64"])
    with open("output.mp4", "wb") as f:
        f.write(video)
    print(f"✅ Rendered {result['size_bytes']} bytes")
```

---

## 5. HTTP Endpoint (Optional)

After deployment, Modal gives you a URL:
```
https://yourname--reeltoolkit-renderer-render-endpoint.modal.run
```

Call it with curl:
```bash
curl -X POST https://yourname--reeltoolkit-renderer-render-endpoint.modal.run \
  -H "Content-Type: application/json" \
  -d @request.json
```

---

## What Modal Does for You

✅ **Automatic scaling** - spin up containers on demand  
✅ **Zero config** - no Dockerfile needed  
✅ **Fast cold starts** - ~1-2 seconds  
✅ **Built-in ffmpeg** - via `.apt_install("ffmpeg")`  
✅ **Pay per second** - very cheap (~$0.002/minute)  
✅ **Logs & monitoring** - `modal app logs reeltoolkit-renderer`

---

## Common Commands

```bash
# Deploy changes
modal deploy modal_app.py

# View logs
modal app logs reeltoolkit-renderer

# List apps
modal app list

# Stop app
modal app stop reeltoolkit-renderer

# Run locally (for testing)
modal run modal_app.py
```

---

## Differences from RunPod

| Feature | RunPod | Modal |
|---------|--------|-------|
| **Deployment** | Docker image + UI | `modal deploy` command |
| **Code changes** | Rebuild image | Instant redeploy |
| **Calling** | REST API | Python SDK or HTTP |
| **Logs** | Web UI | `modal app logs` |
| **Cold start** | 10-30s | 1-2s |
| **Pricing** | Per minute | Per second |

---

## Need Help?

📖 **Full docs:** `MODAL_DEPLOYMENT.md`  
🐛 **Issues:** Check `modal app logs reeltoolkit-renderer`  
💬 **Modal Docs:** https://modal.com/docs

---

**Ready to go! 🎬**
