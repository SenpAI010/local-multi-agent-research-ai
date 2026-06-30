"""
Multimodal Integration: Vision + Text in Agent System
"""
import threading
import asyncio
import os
from typing import Optional, Dict, Any, List, Callable
from pathlib import Path
from PIL import Image
from datetime import datetime

from agent_system.observers.screenshot_monitor import ScreenshotMonitor, ScreenshotMetadata
from agent_system.observers.window_tracker import WindowTracker, WindowEvent
from agent_system.observers.ocr_engine import OCREngine
from agent_system.observers.error_detector import ErrorDetector


class MultimodalContext:
    """
    Stores aktuellen visuellen Kontext für den Agent.
    """

    def __init__(self):
        self.latest_screenshot: Optional[Image.Image] = None
        self.latest_metadata: Optional[ScreenshotMetadata] = None
        self.ocr_text: str = ""
        self.detected_errors: List[Dict[str, Any]] = []
        self.active_window: str = "(unknown)"
        self.active_window_category: Optional[str] = None
        self.ocr_available: bool = False
        self.last_update: Optional[datetime] = None

    def to_context_string(self) -> str:
        """Konvertiert zu String für LLM-Kontext."""
        parts = []

        if self.active_window:
            parts.append(f"Active Window: {self.active_window}")
            if self.active_window_category:
                parts.append(f"  Category: {self.active_window_category}")

        if self.detected_errors:
            parts.append(f"\nDetected {len(self.detected_errors)} error(s):")
            for err in self.detected_errors[:5]:  # Max 5
                parts.append(f"  - Line {err.get('line', '?')}: {err.get('type', 'unknown')}")

        if self.ocr_text:
            parts.append(f"\nVisible Text (OCR):\n{self.ocr_text[:500]}...")
        elif self.latest_metadata:
            if self.ocr_available:
                parts.append("\nVisible Text (OCR): no readable text detected")
            else:
                parts.append("\nVisible Text (OCR): unavailable; install EasyOCR or Tesseract to read screen text")

        if self.latest_metadata:
            parts.append(f"\nScreenshot: {self.latest_metadata.width}x{self.latest_metadata.height}")

        return "\n".join(parts)


class MultimodalAgent:
    """
    Agent mit Screen-Awareness.
    
    Kombiniert:
    - Screenshot-Monitoring
    - Window-Tracking
    - OCR
    - Error-Detection
    """

    def __init__(
        self,
        sandbox_dir: Path,
        screenshot_interval_sec: float = 2.0,
        enable_ocr: bool = True,
        enable_errors: bool = True,
    ):
        self.sandbox_dir = Path(sandbox_dir)
        self.screenshot_dir = self.sandbox_dir / "screenshots"
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        # Components
        self.screenshot_monitor = ScreenshotMonitor(
            interval_sec=screenshot_interval_sec,
            save_dir=self.screenshot_dir,
            max_screenshots=20,
        )

        self.window_tracker = WindowTracker(poll_interval_sec=0.5)

        self.ocr_engine = OCREngine() if enable_ocr else None
        self.error_detector = ErrorDetector() if enable_errors else None

        # Context
        self.context = MultimodalContext()
        self.context.ocr_available = bool(
            self.ocr_engine and getattr(self.ocr_engine, "backend", "none") != "none"
        )
        self.context_callbacks: List[Callable] = []

        # Setup callbacks
        self.screenshot_monitor.add_callback(self._on_screenshot)
        self.window_tracker.add_callback(self._on_window_change)

        self.is_running = False
        self.background_threads: List[threading.Thread] = []
        self.verbose_window_log = os.environ.get("LOCAL_AGENT_VERBOSE_WINDOWS", "0") == "1"

    def add_context_callback(self, callback: Callable) -> None:
        """Registriert Callback bei Context-Updates."""
        self.context_callbacks.append(callback)

    def _on_screenshot(self, img: Image.Image, metadata: ScreenshotMetadata) -> None:
        """Callback wenn neuer Screenshot."""
        self.context.latest_screenshot = img
        self.context.latest_metadata = metadata

        # OCR
        if self.ocr_engine:
            try:
                ocr_result = self.ocr_engine.extract_text(img)
                self.context.ocr_text = ocr_result.get("text", "")[:1000]
            except Exception as e:
                print(f"❌ OCR error: {e}")

        # Error detection
        if self.error_detector and self.context.ocr_text:
            try:
                errors = self.error_detector.detect_errors_in_text(self.context.ocr_text)
                self.context.detected_errors = errors
            except Exception as e:
                print(f"❌ Error detection: {e}")

        self.context.last_update = datetime.now()

        # Fire callbacks
        for cb in self.context_callbacks:
            try:
                cb(self.context)
            except Exception as e:
                print(f"❌ Context callback error: {e}")

    def _on_window_change(self, event: WindowEvent) -> None:
        """Callback wenn Fenster sich ändert."""
        self.context.active_window = event.current_window
        self.context.active_window_category = self.window_tracker.classify_window(event.current_window)

        if self.verbose_window_log:
            print(f"🪟 {event.current_window} [{self.context.active_window_category or 'other'}]")

        # Fire callbacks
        for cb in self.context_callbacks:
            try:
                cb(self.context)
            except Exception as e:
                print(f"❌ Context callback error: {e}")

    def start_monitoring(self) -> None:
        """Startet Screen- & Window-Monitoring im Hintergrund."""
        if self.is_running:
            return

        self.is_running = True

        # Screenshot monitor (Thread)
        t1 = threading.Thread(target=self.screenshot_monitor.run_loop, daemon=True)
        t1.start()
        self.background_threads.append(t1)

        # Window tracker (Thread)
        t2 = threading.Thread(target=self.window_tracker.run_loop, daemon=True)
        t2.start()
        self.background_threads.append(t2)

        print("🔭 Multimodal Monitoring started")

    def stop_monitoring(self) -> None:
        """Stoppt Monitoring."""
        self.is_running = False
        self.screenshot_monitor.stop()
        self.window_tracker.stop()
        print("🔭 Multimodal Monitoring stopped")

    def get_context(self) -> MultimodalContext:
        """Holt aktuellen Kontext."""
        return self.context

    def get_context_string(self) -> str:
        """Holt Kontext als String für LLM."""
        return self.context.to_context_string()

    def take_screenshot(self) -> Optional[Dict[str, Any]]:
        """On-Demand Screenshot."""
        try:
            img, metadata = self.screenshot_monitor.capture_screenshot()
            self._on_screenshot(img, metadata)
            return {
                "ok": True,
                "filepath": str(metadata.filepath) if metadata.filepath else None,
                "window": metadata.window_title,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def analyze_active_window(self) -> Dict[str, Any]:
        """Analysiert aktives Fenster mit OCR + Error Detection."""
        latest = self.screenshot_monitor.get_latest_screenshot()
        
        if not latest:
            return {"ok": False, "error": "No screenshot available"}

        img, metadata = latest

        result = {
            "window": metadata.window_title,
            "timestamp": metadata.timestamp.isoformat(),
        }

        # OCR
        if self.ocr_engine:
            try:
                ocr = self.ocr_engine.extract_text(img)
                result["ocr_text"] = ocr.get("text", "")[:500]
                result["ocr_confidence"] = ocr.get("confidence", 0.0)
            except Exception as e:
                result["ocr_error"] = str(e)

        # Error detection
        if self.error_detector and "ocr_text" in result:
            try:
                errors = self.error_detector.detect_errors_in_text(result["ocr_text"])
                result["errors"] = errors
                result["error_count"] = len(errors)
                
                if errors:
                    suggestions = self.error_detector.suggest_fixes(errors)
                    result["suggestions"] = suggestions
            except Exception as e:
                result["error_detection_error"] = str(e)

        return result

    def is_in_special_window(self, category: Optional[str] = None) -> bool:
        """Prüft ob in speziellem Fenster (Discord, Zoom, etc.)."""
        return self.window_tracker.is_in_special_window(category)


__all__ = ["MultimodalAgent", "MultimodalContext"]
