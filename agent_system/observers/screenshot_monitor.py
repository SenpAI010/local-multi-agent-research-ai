"""
Observers Module: Screenshot monitoring, OCR, Window tracking
"""
import asyncio
import time
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Callable, Any
from dataclasses import dataclass
from datetime import datetime
import threading
from PIL import ImageGrab, Image
import io

@dataclass
class ScreenshotMetadata:
    """Metadaten für einen Screenshot."""
    timestamp: datetime
    width: int
    height: int
    window_title: str
    filepath: Optional[Path] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "width": self.width,
            "height": self.height,
            "window_title": self.window_title,
            "filepath": str(self.filepath) if self.filepath else None,
        }


class ScreenshotMonitor:
    """
    Asynchroner Screenshot-Monitor.
    
    Features:
    - Regelmäßige Screenshot-Aufnahme
    - Optional: Speichern auf Disk
    - Callback-System für Verarbeitung
    - Thread-safe
    """

    def __init__(
        self,
        interval_sec: float = 2.0,
        save_dir: Optional[Path] = None,
        max_screenshots: int = 50,
    ):
        """
        Args:
            interval_sec: Interval zwischen Screenshots
            save_dir: Optional Verzeichnis für Screenshot-Speicherung
            max_screenshots: Max Screenshots im Memory
        """
        self.interval_sec = interval_sec
        self.save_dir = save_dir
        self.max_screenshots = max_screenshots
        
        self.screenshots: List[Tuple[Image.Image, ScreenshotMetadata]] = []
        self.callbacks: List[Callable[[Image.Image, ScreenshotMetadata], None]] = []
        self.should_capture: Optional[Callable[[str], bool]] = None
        self.is_running = False
        self.lock = threading.Lock()

    def add_callback(self, callback: Callable) -> None:
        """Registriert einen Callback für neue Screenshots."""
        self.callbacks.append(callback)

    def capture_screenshot(self) -> Tuple[Image.Image, ScreenshotMetadata]:
        """Nimmt einen Screenshot auf."""
        try:
            img = ImageGrab.grab()  # Windows native
            
            # Get active window title (Windows)
            window_title = self._get_window_title()
            
            metadata = ScreenshotMetadata(
                timestamp=datetime.now(),
                width=img.width,
                height=img.height,
                window_title=window_title,
            )
            
            # Optional: Speichern
            if self.save_dir:
                filepath = self._save_screenshot(img, metadata)
                metadata.filepath = filepath
            
            return img, metadata
        
        except Exception as e:
            print(f"❌ Screenshot capture failed: {e}")
            # Return black image as fallback
            black = Image.new("RGB", (1920, 1080), color=(0, 0, 0))
            return black, ScreenshotMetadata(
                timestamp=datetime.now(),
                width=1920,
                height=1080,
                window_title="(error)",
            )

    def _get_window_title(self) -> str:
        """Holt Titel des aktiven Fensters (Windows)."""
        try:
            import ctypes
            GetForegroundWindow = ctypes.windll.user32.GetForegroundWindow
            GetWindowTextLength = ctypes.windll.user32.GetWindowTextLength
            GetWindowText = ctypes.windll.user32.GetWindowText

            hwnd = GetForegroundWindow()
            length = GetWindowTextLength(hwnd)
            
            if length == 0:
                return "(unknown)"
            
            buff = ctypes.create_unicode_buffer(length + 1)
            GetWindowText(hwnd, buff, length + 1)
            return buff.value or "(unknown)"
        
        except Exception:
            return "(unavailable)"

    def _save_screenshot(self, img: Image.Image, metadata: ScreenshotMetadata) -> Path:
        """Speichert Screenshot auf Disk."""
        self.save_dir.mkdir(parents=True, exist_ok=True)
        
        filename = metadata.timestamp.strftime("screenshot_%Y%m%d_%H%M%S.png")
        filepath = self.save_dir / filename
        
        img.save(filepath, "PNG")
        return filepath

    def start(self) -> None:
        """Startet den Monitor (blockierend)."""
        if self.is_running:
            return
        
        self.is_running = True
        print(f"🎥 Screenshot Monitor started (interval={self.interval_sec}s)")

    def stop(self) -> None:
        """Stoppt den Monitor."""
        self.is_running = False
        print("🎥 Screenshot Monitor stopped")

    def run_loop(self) -> None:
        """Führt den Monitor-Loop aus (für Threading)."""
        self.start()
        
        try:
            while self.is_running:
                title = self._get_window_title()
                if self.should_capture and not self.should_capture(title):
                    time.sleep(self.interval_sec)
                    continue

                img, metadata = self.capture_screenshot()
                
                with self.lock:
                    self.screenshots.append((img, metadata))
                    
                    # Keep max_screenshots
                    if len(self.screenshots) > self.max_screenshots:
                        self.screenshots.pop(0)
                
                # Fire callbacks
                for cb in self.callbacks:
                    try:
                        cb(img, metadata)
                    except Exception as e:
                        print(f"❌ Callback error: {e}")
                
                time.sleep(self.interval_sec)
        
        except KeyboardInterrupt:
            pass
        
        finally:
            self.stop()

    def get_latest_screenshot(self) -> Optional[Tuple[Image.Image, ScreenshotMetadata]]:
        """Holt den neuesten Screenshot."""
        with self.lock:
            if self.screenshots:
                return self.screenshots[-1]
        return None

    def get_screenshots_since(self, seconds_ago: float) -> List[Tuple[Image.Image, ScreenshotMetadata]]:
        """Holt Screenshots der letzten N Sekunden."""
        cutoff = datetime.now().timestamp() - seconds_ago
        
        with self.lock:
            return [
                (img, meta) for img, meta in self.screenshots
                if meta.timestamp.timestamp() >= cutoff
            ]

    async def async_run_loop(self) -> None:
        """Async version des Monitor-Loops."""
        self.start()
        
        try:
            while self.is_running:
                img, metadata = await asyncio.to_thread(self.capture_screenshot)
                
                with self.lock:
                    self.screenshots.append((img, metadata))
                    if len(self.screenshots) > self.max_screenshots:
                        self.screenshots.pop(0)
                
                # Fire callbacks (async-safe)
                for cb in self.callbacks:
                    try:
                        if asyncio.iscoroutinefunction(cb):
                            await cb(img, metadata)
                        else:
                            await asyncio.to_thread(cb, img, metadata)
                    except Exception as e:
                        print(f"❌ Callback error: {e}")
                
                await asyncio.sleep(self.interval_sec)
        
        except asyncio.CancelledError:
            pass
        
        finally:
            self.stop()


__all__ = ["ScreenshotMonitor", "ScreenshotMetadata"]
