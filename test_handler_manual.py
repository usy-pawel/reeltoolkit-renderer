#!/usr/bin/env python3
"""Quick manual test to verify handler.py can start and respond."""
import sys
import os

# Simulate RunPod job structure
test_job = {
    "input": {
        "spec": {
            "job_id": "test-001",
            "output_name": "test.mp4",
            "dimensions": {"width": 640, "height": 480, "fps": 30},
            "background_color": "#000000",
            "render": {"use_parallel": False, "quality": "draft"},
            "slides": []
        }
    }
}

print("=" * 60)
print("Testing handler.py import and basic structure...")
print("=" * 60)

try:
    # Test 1: Can we import handler?
    print("\n[1/4] Importing handler module...")
    import handler
    print("✓ Import successful")
    
    # Test 2: Does handler function exist?
    print("\n[2/4] Checking handler function exists...")
    assert hasattr(handler, 'handler'), "handler() function not found!"
    assert callable(handler.handler), "handler is not callable!"
    print("✓ handler() function exists")
    
    # Test 3: Does handler_async exist?
    print("\n[3/4] Checking handler_async function exists...")
    assert hasattr(handler, 'handler_async'), "handler_async() function not found!"
    assert callable(handler.handler_async), "handler_async is not callable!"
    print("✓ handler_async() function exists")
    
    # Test 4: Can handler run without crashing immediately?
    print("\n[4/4] Testing handler can be called (expecting error due to missing bundle)...")
    try:
        result = handler.handler(test_job)
        print(f"✗ Unexpected success: {result}")
    except ValueError as e:
        if "bundle_b64" in str(e):
            print(f"✓ Handler executed and correctly rejected missing bundle: {e}")
        else:
            print(f"✗ Wrong ValueError: {e}")
            sys.exit(1)
    except Exception as e:
        print(f"✗ Unexpected error type: {type(e).__name__}: {e}")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("✓ ALL TESTS PASSED - handler.py is working!")
    print("=" * 60)
    sys.exit(0)
    
except ImportError as e:
    print(f"\n✗ FAILED: Cannot import handler: {e}")
    sys.exit(1)
except Exception as e:
    print(f"\n✗ FAILED: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
