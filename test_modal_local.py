"""Test Modal functions locally before deployment."""
import base64
from pathlib import Path


def test_ffmpeg_call():
    """Test the Modal ffmpeg function."""
    import modal
    
    print("🔍 Looking up Modal app...")
    try:
        app = modal.App.lookup("reeltoolkit-renderer", create_if_missing=False)
        print("✅ App found")
    except Exception as e:
        print(f"❌ App not found. Deploy first with: modal deploy modal_app.py")
        print(f"Error: {e}")
        return
    
    print("🔍 Looking up test_ffmpeg function...")
    test_fn = modal.Function.lookup("reeltoolkit-renderer", "test_ffmpeg")
    
    print("🚀 Calling remote function...")
    result = test_fn.remote()
    
    if result.get("success"):
        print(f"✅ Success!")
        print(f"   Size: {result['size_bytes']} bytes")
        print(f"   Message: {result['message']}")
        
        # Save video to local file
        video_bytes = base64.b64decode(result["video_b64"])
        output_path = Path("test_modal_output.mp4")
        output_path.write_bytes(video_bytes)
        print(f"💾 Saved to: {output_path.absolute()}")
    else:
        print(f"❌ Failed: {result.get('error')}")


def test_render_call():
    """Test the Modal render function with a minimal spec."""
    import modal
    
    print("🔍 Looking up Modal app...")
    app = modal.App.lookup("reeltoolkit-renderer", create_if_missing=False)
    
    print("🔍 Looking up render_reel function...")
    render_fn = modal.Function.lookup("reeltoolkit-renderer", "render_reel")
    
    # Minimal spec
    spec = {
        "job_id": "modal-test-001",
        "output_name": "output.mp4",
        "dimensions": {"width": 720, "height": 1280, "fps": 25},
        "background_color": "#FF0000",  # Red background
        "render": {"use_parallel": False, "quality": "preview"},
        "slides": [
            {
                "duration": 2.0,
                "background": {"type": "color", "value": "#0000FF"}  # Blue slide
            }
        ]
    }
    
    # Create minimal bundle (empty ZIP)
    import zipfile
    import tempfile
    
    tmp_zip = Path(tempfile.mktemp(suffix=".zip"))
    with zipfile.ZipFile(tmp_zip, 'w') as zf:
        # Add a dummy file
        zf.writestr("dummy.txt", "Modal test")
    
    bundle_b64 = base64.b64encode(tmp_zip.read_bytes()).decode('utf-8')
    tmp_zip.unlink()
    
    print("🚀 Calling remote render function...")
    result = render_fn.remote(spec, bundle_b64)
    
    if result.get("success"):
        print(f"✅ Render success!")
        print(f"   Job ID: {result['job_id']}")
        print(f"   Size: {result['size_bytes']} bytes")
        
        # Save video
        video_bytes = base64.b64decode(result["video_b64"])
        output_path = Path(f"{result['job_id']}.mp4")
        output_path.write_bytes(video_bytes)
        print(f"💾 Saved to: {output_path.absolute()}")
    else:
        print(f"❌ Render failed: {result.get('error')}")
        if "traceback" in result:
            print(f"\n{result['traceback']}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "render":
        test_render_call()
    else:
        print("Testing ffmpeg function...")
        test_ffmpeg_call()
        
        print("\n" + "="*60)
        print("To test full render, run:")
        print("  python test_modal_local.py render")
