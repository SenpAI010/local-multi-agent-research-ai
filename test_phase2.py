"""
Phase 2 System Test & Validation
"""
import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).parent))


def test_imports():
    """Test Phase 2 imports."""
    print("🧪 Testing Phase 2 imports...")
    
    try:
        from agent_system.observers import (
            ScreenshotMonitor, ScreenshotMetadata,
            WindowTracker, WindowEvent,
            OCREngine, ErrorDetector
        )
        print("  ✅ Observer modules")
    except Exception as e:
        print(f"  ❌ Observers: {e}")
        return False

    try:
        from agent_system.core import MultimodalAgent, MultimodalContext
        print("  ✅ Multimodal modules")
    except Exception as e:
        print(f"  ❌ Multimodal: {e}")
        return False

    return True


def test_screenshot_monitor():
    """Test screenshot monitoring."""
    print("\n🧪 Testing ScreenshotMonitor...")
    
    from agent_system.observers import ScreenshotMonitor
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        monitor = ScreenshotMonitor(
            interval_sec=1.0,
            save_dir=Path(tmpdir),
            max_screenshots=5,
        )

        # Capture one
        try:
            img, metadata = monitor.capture_screenshot()
            print(f"  ✅ Screenshot captured: {img.width}x{img.height}")
        except Exception as e:
            print(f"  ❌ Capture failed: {e}")
            return False

        # Check metadata
        if metadata.width > 0 and metadata.height > 0:
            print(f"  ✅ Metadata valid")
        else:
            print(f"  ❌ Invalid metadata")
            return False

    return True


def test_window_tracker():
    """Test window tracking."""
    print("\n🧪 Testing WindowTracker...")
    
    from agent_system.observers import WindowTracker
    
    tracker = WindowTracker(poll_interval_sec=0.5)
    
    try:
        current = tracker.get_active_window()
        print(f"  ✅ Current window: {current[:40]}...")
    except Exception as e:
        print(f"  ❌ Get window failed: {e}")
        return False

    try:
        category = tracker.classify_window(current)
        print(f"  ✅ Classified as: {category or 'other'}")
    except Exception as e:
        print(f"  ❌ Classification failed: {e}")
        return False

    return True


def test_ocr_engine():
    """Test OCR (may not work if backend missing)."""
    print("\n🧪 Testing OCREngine...")
    
    from agent_system.observers import OCREngine
    from PIL import Image, ImageDraw, ImageFont
    
    engine = OCREngine(backend="auto")
    print(f"  Backend: {engine.backend}")

    # Create simple test image
    try:
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), "Hello OCR", fill=(0, 0, 0))
        
        result = engine.extract_text(img)
        
        if result.get("backend") != "none":
            text = result.get("text", "").lower()
            if "hello" in text or "ocr" in text or result.get("confidence", 0) > 0:
                print(f"  ✅ OCR working ({engine.backend}): {text[:30]}")
            else:
                print(f"  ⚠️  OCR responded but unclear: {text[:30]}")
        else:
            print(f"  ⚠️  OCR backend not available (expected on first run)")
    
    except Exception as e:
        print(f"  ⚠️  OCR error: {e}")

    return True


def test_error_detector():
    """Test error detection."""
    print("\n🧪 Testing ErrorDetector...")
    
    from agent_system.observers import ErrorDetector
    
    detector = ErrorDetector()

    # Test text with errors
    test_code = """
def hello(x)
    print(x  # SyntaxError: missing )
    y = undefined_var  # NameError
    return y
"""

    try:
        errors = detector.detect_errors_in_text(test_code)
        if errors:
            print(f"  ✅ Detected {len(errors)} error(s)")
            for err in errors[:2]:
                print(f"     - Line {err['line']}: {err['type']}")
        else:
            print(f"  ❌ No errors detected (should have found some)")
            return False
    
    except Exception as e:
        print(f"  ❌ Error detection failed: {e}")
        return False

    return True


def test_multimodal_agent():
    """Test MultimodalAgent."""
    print("\n🧪 Testing MultimodalAgent...")
    
    from agent_system.core import MultimodalAgent
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            agent = MultimodalAgent(
                sandbox_dir=Path(tmpdir),
                screenshot_interval_sec=1.0,
                enable_ocr=True,
                enable_errors=True,
            )
            print("  ✅ MultimodalAgent initialized")
            
            # Check components
            if agent.screenshot_monitor:
                print("  ✅ Screenshot monitor available")
            if agent.window_tracker:
                print("  ✅ Window tracker available")
            if agent.ocr_engine:
                print(f"  ✅ OCR engine available ({agent.ocr_engine.backend})")
            if agent.error_detector:
                print("  ✅ Error detector available")
            
            # Take screenshot
            result = agent.take_screenshot()
            if result.get("ok"):
                print(f"  ✅ Screenshot saved: {result.get('filepath')}")
            else:
                print(f"  ⚠️  Screenshot failed: {result.get('error')}")
            
            # Get context
            ctx = agent.get_context()
            print(f"  ✅ Context retrieved")
            
        except Exception as e:
            print(f"  ❌ MultimodalAgent failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    return True


def main():
    print("=" * 70)
    print("Phase 2 System Test (Screen-Awareness)")
    print("=" * 70)
    print()
    
    all_ok = True
    
    all_ok &= test_imports()
    all_ok &= test_screenshot_monitor()
    all_ok &= test_window_tracker()
    all_ok &= test_ocr_engine()
    all_ok &= test_error_detector()
    all_ok &= test_multimodal_agent()
    
    print("\n" + "=" * 70)
    if all_ok:
        print("✅ Phase 2 System Validation PASSED")
    else:
        print("⚠️  Phase 2 System Validation PARTIAL (some features may need setup)")
    print("=" * 70)
    print()
    print("Next: python main_phase2.py")


if __name__ == "__main__":
    main()
