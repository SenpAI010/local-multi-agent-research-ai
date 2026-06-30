"""
Tools Module: Note management
"""
from pathlib import Path
from typing import Any, Dict, List
import re

class NoteTools:
    """
    Tools für Notizen-Verwaltung.
    - save_note
    - list_notes
    """

    def __init__(self, sandbox_mgr):
        self.sandbox = sandbox_mgr

    def sanitize_filename(self, name: str) -> str:
        """Bereinigt Dateinamen."""
        safe = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
        safe = safe[:80] if safe else "note"
        return safe

    def save_note(self, title: str, text: str) -> Dict[str, Any]:
        """Speichert eine Notiz."""
        try:
            print("\n=== APPROVAL REQUIRED (SAVE NOTE) ===")
            print(f"Title: {title}")
            print(text[:1000] + ("..." if len(text) > 1000 else ""))
            ans = input("Save note permanently? [y/N] ").strip().lower()
            if ans not in {"y", "yes", "j", "ja"}:
                return {"ok": False, "error": "User denied note save."}

            fname = self.sanitize_filename(title) + ".txt"
            path = (self.sandbox.notes_dir / fname).resolve()

            if not self.sandbox.is_within(self.sandbox.notes_dir, path):
                return {"ok": False, "error": "Invalid note path."}

            path.write_text(text, encoding="utf-8")
            return {"ok": True, "file": str(path)}
        
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def list_notes(self) -> Dict[str, Any]:
        """Listet alle Notizen auf."""
        try:
            notes = sorted([p.name for p in self.sandbox.notes_dir.glob("*.txt")])
            return {"ok": True, "notes": notes}
        
        except Exception as e:
            return {"ok": False, "error": str(e)}
