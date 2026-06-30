"""
Window Tracker: Track active windows (Discord, Zoom, VS Code, etc.)
"""
import threading
import time
import os
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime

@dataclass
class WindowEvent:
    """Event wenn sich Fenster ändert."""
    timestamp: datetime
    previous_window: str
    current_window: str
    is_special: bool  # True wenn Discord/Zoom/VSCode
    
    def to_dict(self):
        return {
            "timestamp": self.timestamp.isoformat(),
            "previous": self.previous_window,
            "current": self.current_window,
            "is_special": self.is_special,
        }


class WindowTracker:
    """
    Überwacht aktive Fenster und erkennt spezielle Apps.
    
    Special Windows:
    - VS Code
    - Discord
    - Zoom
    - Unity Editor
    - Browser (Chrome, Firefox, Edge)
    """

    # Keyword Matching für spezielle Fenster
    SPECIAL_KEYWORDS = {
        "vs code": ["Visual Studio Code", "vscode", "code.exe"],
        "discord": ["Discord", "discord.exe"],
        "zoom": ["Zoom", "zoom.exe", "Zoom Meeting"],
        "unity": ["Unity", "UnityEditor", "unity.exe"],
        "browser": ["Chrome", "Firefox", "Edge", "Chromium", "brave"],
        "terminal": ["PowerShell", "CMD", "Terminal", "pwsh"],
    }

    def __init__(self, poll_interval_sec: float = 1.0):
        self.poll_interval_sec = poll_interval_sec
        self.current_window = "(unknown)"
        self.previous_window = "(unknown)"
        self.window_history: List[WindowEvent] = []
        self.callbacks: List = []
        self.is_running = False
        self.lock = threading.Lock()
        self.verbose = os.environ.get("LOCAL_AGENT_VERBOSE_WINDOWS", "0") == "1"

    def add_callback(self, callback) -> None:
        """Registriert Callback für Window-Wechsel."""
        self.callbacks.append(callback)

    def get_active_window(self) -> str:
        """Holt Titel des aktiven Fensters."""
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            GetForegroundWindow = user32.GetForegroundWindow
            GetWindowTextLength = user32.GetWindowTextLengthW
            GetWindowText = user32.GetWindowTextW

            GetForegroundWindow.restype = wintypes.HWND
            GetWindowTextLength.argtypes = [wintypes.HWND]
            GetWindowTextLength.restype = ctypes.c_int
            GetWindowText.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            GetWindowText.restype = ctypes.c_int

            hwnd = GetForegroundWindow()
            if not hwnd:
                return "(desktop)"

            length = GetWindowTextLength(hwnd)
            
            if length == 0:
                return "(desktop)"
            
            buff = ctypes.create_unicode_buffer(length + 1)
            copied = GetWindowText(hwnd, buff, length + 1)
            if copied == 0:
                return "(untitled)"
            return buff.value or "(unknown)"
        
        except Exception as e:
            return f"(unavailable: {e})"

    def classify_window(self, window_title: str) -> Optional[str]:
        """
        Klassifiziert ein Fenster.
        
        Returns: z.B. "vs code", "discord", "unity", None
        """
        title_lower = window_title.lower()
        
        for category, keywords in self.SPECIAL_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in title_lower:
                    return category
        
        return None

    def run_loop(self) -> None:
        """Führt den Tracker-Loop aus (für Threading)."""
        self.is_running = True
        if self.verbose:
            print("📊 Window Tracker started")
        
        try:
            while self.is_running:
                current = self.get_active_window()
                
                # Window wechsel?
                if current != self.current_window:
                    with self.lock:
                        self.previous_window = self.current_window
                        self.current_window = current
                    
                    # Event erstellen
                    is_special = self.classify_window(current) is not None
                    event = WindowEvent(
                        timestamp=datetime.now(),
                        previous_window=self.previous_window,
                        current_window=current,
                        is_special=is_special,
                    )
                    
                    with self.lock:
                        self.window_history.append(event)
                        if len(self.window_history) > 1000:
                            self.window_history.pop(0)
                    
                    # Fire callbacks
                    for cb in self.callbacks:
                        try:
                            cb(event)
                        except Exception as e:
                            print(f"❌ Callback error: {e}")
                    
                    if self.verbose:
                        print(f"🪟 Window: {current} [{self.classify_window(current) or 'other'}]")
                
                time.sleep(self.poll_interval_sec)
        
        except KeyboardInterrupt:
            pass
        
        finally:
            self.is_running = False
            if self.verbose:
                print("📊 Window Tracker stopped")

    def stop(self) -> None:
        """Stoppt den Tracker."""
        self.is_running = False

    def get_current_window(self) -> str:
        """Holt aktuelles Fenster."""
        with self.lock:
            return self.current_window

    def get_window_history(self, limit: int = 20) -> List[WindowEvent]:
        """Holt History der Fenster-Wechsel."""
        with self.lock:
            return self.window_history[-limit:]

    def list_open_windows(self) -> List[Dict[str, str]]:
        """List visible top-level Windows windows without interacting with them."""
        windows: List[Dict[str, str]] = []
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            EnumWindows = user32.EnumWindows
            IsWindowVisible = user32.IsWindowVisible
            GetWindowTextLength = user32.GetWindowTextLengthW
            GetWindowText = user32.GetWindowTextW

            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            def callback(hwnd, _lparam):
                if not IsWindowVisible(hwnd):
                    return True
                length = GetWindowTextLength(hwnd)
                if length <= 0:
                    return True
                buff = ctypes.create_unicode_buffer(length + 1)
                copied = GetWindowText(hwnd, buff, length + 1)
                if copied > 0 and buff.value.strip():
                    title = buff.value.strip()
                    windows.append({
                        "title": title,
                        "category": self.classify_window(title) or "other",
                    })
                return True

            EnumWindows(WNDENUMPROC(callback), 0)
        except Exception:
            return []

        seen = set()
        unique = []
        for item in windows:
            title = item["title"]
            if title in seen:
                continue
            seen.add(title)
            unique.append(item)
        return unique

    def is_in_special_window(self, category: Optional[str] = None) -> bool:
        """Prüft ob in speziellem Fenster."""
        current = self.get_current_window()
        current_cat = self.classify_window(current)
        
        if category:
            return current_cat == category
        
        return current_cat is not None


__all__ = ["WindowTracker", "WindowEvent"]
