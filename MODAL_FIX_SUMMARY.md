# Modal Rendering Fix - h264_nvenc Error Resolution

## Problem Summary

The Modal renderer was failing with the following errors:
1. **"Unknown encoder 'h264_nvenc'"** - FFmpeg couldn't find the NVIDIA GPU encoder
2. **"Broken pipe"** - FFmpeg process crash due to codec mismatch

## Root Cause

The Modal app was configured with:
- ✅ GPU allocation (`gpu=GPU_CONFIG`)
- ✅ CPU-only FFmpeg build (from BtbN/FFmpeg-Builds - no NVENC support)
- ❌ Environment variable `RENDER_USE_NVENC=1` (requesting GPU encoding)

This mismatch caused MoviePy to request `h264_nvenc` codec, which wasn't available in the FFmpeg binary, leading to a broken pipe error when FFmpeg failed to initialize.

## Changes Made

### 1. **modal_app.py** - Disabled NVENC and GPU
```python
# Changed from:
os.environ.setdefault("RENDER_USE_NVENC", "1")

# To:
os.environ.setdefault("RENDER_USE_NVENC", "0")
```

Removed GPU allocation since we're using CPU-only FFmpeg:
```python
@app.function(
    image=image,
    timeout=600,
    memory=8192,
    # GPU removed - using CPU-only FFmpeg build with libx264
)
```

Added diagnostic logging:
- FFmpeg path verification
- NVENC status logging
- FFmpeg version check

### 2. **reel_renderer/video.py** - Better Error Handling
Added try-catch for broken pipe errors:
```python
try:
    final.write_videofile(...)
except (BrokenPipeError, IOError, OSError) as e:
    error_msg = f"FFmpeg pipe error during video writing: {e}"
    print(error_msg)
    if os.path.exists(output_path):
        size = os.path.getsize(output_path)
        print(f"Partial output exists: {size} bytes")
    raise RuntimeError(error_msg) from e
```

## Deployment Instructions

### Step 1: Navigate to Renderer Directory
```bash
cd c:/workspace/reeltoolkit-renderer
```

### Step 2: Deploy to Modal
```bash
modal deploy modal_app.py
```

This will:
- Rebuild the Modal container image
- Deploy the updated `render_reel` function
- Use CPU-only rendering with `libx264` codec

### Step 3: Test the Deployment
You can test with the built-in test function:
```bash
modal run modal_app.py
```

Or test the render function directly from Python:
```python
import modal
fn = modal.Function.from_name("reeltoolkit-renderer", "render_reel")
# Call with your test payload
```

### Step 4: Backend Environment Variables
Ensure your backend has these environment variables set:
```bash
RENDER_SERVICE_PROVIDER=modal
MODAL_RENDER_APP=reeltoolkit-renderer
MODAL_RENDER_FUNCTION=render_reel
RENDER_SERVICE_TIMEOUT=600
```

## Expected Behavior After Fix

### ✅ What Will Happen:
1. Modal will use **libx264** codec (CPU encoding)
2. No GPU will be allocated (cost savings!)
3. Rendering will work with transitions enabled
4. Better error messages if something goes wrong

### 📊 Performance Impact:
- **CPU encoding** is slower than GPU encoding
- But it's required for transitions anyway
- Modal containers are still fast with good CPU allocation

### 💰 Cost Impact:
- **Reduced costs** - no GPU allocation needed
- CPU-only instances are cheaper
- Still fast enough for production use

## Logs to Watch For

When rendering, you should now see:
```
🎬 Starting render: 720x1280 @ 25fps
🔧 FFmpeg path: /usr/local/bin/ffmpeg
🎥 NVENC enabled: 0
✅ FFmpeg version check passed
Rendering video with codec: libx264, preset: veryfast
```

## Alternative: GPU-Enabled FFmpeg (Future Enhancement)

If you want GPU acceleration in the future, you would need to:
1. Use a different FFmpeg build with NVENC support
2. Use a Modal GPU image or custom NVIDIA CUDA image
3. Set `RENDER_USE_NVENC=1`
4. Re-enable `gpu=GPU_CONFIG`

Example FFmpeg build with NVENC:
```python
# Use NVIDIA CUDA base image
image = modal.Image.from_registry(
    "nvidia/cuda:12.0.0-runtime-ubuntu22.04",
    python_version="3.11"
)
# Install FFmpeg with NVENC support via add-apt-repository ppa
```

But for now, **CPU rendering with libx264 is the correct solution**.

## Testing Checklist

- [ ] Deploy Modal app: `modal deploy modal_app.py`
- [ ] Check Modal logs show: `NVENC enabled: 0`
- [ ] Check Modal logs show: `codec: libx264`
- [ ] Test a simple render without transitions
- [ ] Test a render with transitions
- [ ] Verify video output is valid MP4
- [ ] Check Modal costs are reduced (no GPU)

## Related Files Changed

1. `c:\workspace\reeltoolkit-renderer\modal_app.py`
2. `c:\workspace\reeltoolkit-renderer\reel_renderer\video.py`

## Support

If you still encounter issues:
1. Check Modal logs: `modal app logs reeltoolkit-renderer`
2. Verify FFmpeg in container: `modal run modal_app.py::test_ffmpeg`
3. Check backend logs for full error traceback
