"""Test GPU rendering with real render_reel function."""
import base64
import json
from pathlib import Path
import tempfile
import zipfile
from PIL import Image
import modal

# Sample render spec
spec = {
    "job_id": "test_gpu_render",
    "dimensions": {
        "width": 720,
        "height": 1280,
        "fps": 25
    },
    "slides": [
        {
            "image": "slide_1.png",
            "audio": "slide_1.mp3",
            "duration": 2.0,
            "motion": {"type": "zoom-in", "amount": 0.1}
        }
    ],
    "ending_video": None,
    "subtitle": None,
    "background_music": None
}

def create_test_bundle():
    """Create a minimal test bundle with fake assets."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="test_bundle_"))
    
    # Create fake image
    img = Image.new('RGB', (720, 1280), color='blue')
    img.save(tmp_dir / "slide_1.png")
    
    # Create fake audio (silence)
    # We'll use a minimal valid MP3 file
    # For simplicity, create empty file (will cause audio warning but won't crash)
    (tmp_dir / "slide_1.mp3").write_bytes(b'\xff\xfb\x90\x00' * 100)  # Minimal MP3 header
    
    # Create ZIP bundle
    bundle_path = tmp_dir / "bundle.zip"
    with zipfile.ZipFile(bundle_path, 'w') as zf:
        zf.write(tmp_dir / "slide_1.png", arcname="slide_1.png")
        zf.write(tmp_dir / "slide_1.mp3", arcname="slide_1.mp3")
    
    bundle_bytes = bundle_path.read_bytes()
    bundle_b64 = base64.b64encode(bundle_bytes).decode('utf-8')
    
    return bundle_b64

def main():
    """Test the GPU rendering function."""
    print("🧪 Testing GPU rendering with NVENC...")
    print("=" * 60)
    
    # Create test bundle
    print("📦 Creating test bundle...")
    bundle_b64 = create_test_bundle()
    print(f"✅ Bundle created: {len(bundle_b64)} bytes (base64)")
    
    # Get Modal function
    print("🔗 Connecting to Modal function...")
    fn = modal.Function.from_name("reeltoolkit-renderer", "render_reel")
    
    # Call the function
    print("🎬 Calling render_reel with GPU...")
    print("⏳ This will use GPU + NVENC if available...")
    
    result = fn.remote(spec, bundle_b64)
    
    print("=" * 60)
    
    if result.get("success"):
        print("✅ GPU RENDER SUCCESS!")
        print(f"📊 Video size: {result.get('size_bytes')} bytes")
        print(f"🎞️  Job ID: {result.get('job_id')}")
        
        # Save video
        output_path = Path("test_gpu_output.mp4")
        video_bytes = base64.b64decode(result["video_b64"])
        output_path.write_bytes(video_bytes)
        print(f"💾 Saved to: {output_path}")
        
        # Check if NVENC was used (look for it in logs)
        print("\n📋 Check Modal logs for:")
        print("   - '🎮 GPU detected'")
        print("   - '✅ h264_nvenc encoder is available'")
        print("   - 'Rendering video with codec: h264_nvenc'")
        
    else:
        print("❌ RENDER FAILED!")
        print(f"Error: {result.get('error')}")
        if result.get('traceback'):
            print("\nTraceback:")
            print(result['traceback'])

if __name__ == "__main__":
    main()
