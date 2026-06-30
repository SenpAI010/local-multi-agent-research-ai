"""
Memory Manager: SQLite + User-Profil + Explizite Bestätigung
"""
import sqlite3
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

class MemoryManager:
    """
    Verwaltet:
    - Konversations-Historie
    - Zusammenfassungen
    - User-Profil (persistentes Gedächtnis)
    
    WICHTIG: Vor jedem Speichern wird der Nutzer gefragt!
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialisiert Datenbank-Schema."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                summary TEXT NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS profile (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                ts INTEGER NOT NULL
            );
        """)
        conn.commit()
        conn.close()

    def ask_yes_no(self, prompt: str, default: bool = False) -> bool:
        """Ask for explicit user approval before persistent actions."""
        if self._avatar_allows_auto_memory(prompt):
            print(f"{prompt} [auto: avatar trust profile]")
            return True

        suffix = "[Y/n]" if default else "[y/N]"
        ans = input(f"{prompt} {suffix} ").strip().lower()
        if not ans:
            return default
        return ans in {"y", "yes", "j", "ja"}

    def _avatar_allows_auto_memory(self, prompt: str) -> bool:
        """Allow opt-in automatic memory saves from avatar trust settings."""
        text = prompt.lower()
        memory_prompt = any(
            marker in text
            for marker in ("memory", "sqlite", "semantic", "summary", "profile")
        )
        if not memory_prompt:
            return False

        path = self.db_path.parent / "avatar_permissions.json"
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return False
        return bool(data.get("auto_memory", False))

    def add_message(self, role: str, content: str, require_approval: bool = True) -> bool:
        """Speichert eine Chat-Nachricht."""
        if require_approval:
            preview = content[:500] + ("..." if len(content) > 500 else "")
            print("\n=== MEMORY SAVE APPROVAL ===")
            print(f"Role: {role}")
            print(preview)
            if not self.ask_yes_no("Save this message to SQLite memory?"):
                print("Save cancelled.")
                return False

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO messages(ts, role, content) VALUES(?,?,?)",
            (int(time.time()), role, content),
        )
        conn.commit()
        conn.close()
        return True

    def get_recent_messages(self, limit: int = 30) -> List[Tuple[str, str]]:
        """Holt letzte Chat-Nachrichten."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
        conn.close()
        rows.reverse()
        return [(r[0], r[1]) for r in rows]

    def add_summary(self, summary: str, require_approval: bool = True) -> bool:
        """Speichert eine Zusammenfassung."""
        if require_approval:
            print("\n=== SUMMARY SAVE APPROVAL ===")
            print(summary[:1000] + ("..." if len(summary) > 1000 else ""))
            if not self.ask_yes_no("Save this summary to SQLite memory?"):
                print("Summary save cancelled.")
                return False

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO summaries(ts, summary) VALUES(?,?)",
            (int(time.time()), summary),
        )
        conn.commit()
        conn.close()
        print("Summary saved.")
        return True

    def get_latest_summary(self) -> Optional[str]:
        """Holt die neueste Zusammenfassung."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute("SELECT summary FROM summaries ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None

    # ===== USER-PROFIL (mit Bestätigung) =====

    def get_profile(self) -> Dict[str, Any]:
        """Holt User-Profil aus Datenbank."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute("SELECT key, value FROM profile")
        rows = cur.fetchall()
        conn.close()

        profile = {}
        for key, value in rows:
            try:
                profile[key] = json.loads(value)
            except json.JSONDecodeError:
                profile[key] = value

        return profile

    def set_profile_field(self, key: str, value: Any, require_approval: bool = True) -> bool:
        """
        Setzt ein Profil-Feld MIT BESTÄTIGUNG.
        
        Returns: True wenn gespeichert, False wenn abgelehnt.
        """
        if require_approval:
            print(f"\n=== PROFILE SAVE APPROVAL ===")
            print(f"Key: {key}")
            print(f"Value: {json.dumps(value, ensure_ascii=False, indent=2)}")
            ans = input("Save to profile? [y/N] ").strip().lower()
            if ans != "y":
                print("❌ Save cancelled.")
                return False

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO profile(key, value, ts) VALUES(?,?,?)",
            (key, json.dumps(value, ensure_ascii=False), int(time.time())),
        )
        conn.commit()
        conn.close()
        print("✅ Saved to profile.")
        return True

    def setup_user_profile(self) -> Dict[str, Any]:
        """
        Interaktive Einrichtung des User-Profils (First-Run).
        """
        existing = self.get_profile()
        if existing:
            print("User-Profil existiert bereits:")
            print(json.dumps(existing, ensure_ascii=False, indent=2))
            return existing

        print("\n=== USER PROFILE SETUP ===\n")

        profile = {}

        # Name
        name = input("Dein Name: ").strip()
        if name:
            profile["name"] = name

        # Rolle/Studium
        role = input("Deine Rolle (z.B. 'Masterstudent Mathematik'): ").strip()
        if role:
            profile["role"] = role

        # Tech-Stack
        print("\nTech-Stack (jeweils Enter zum Überspringen):")
        tech_stack = {}
        
        ide = input("  IDE (z.B. VS Code, Unity): ").strip()
        if ide:
            tech_stack["ide"] = ide

        langs = input("  Programmiersprachen (kommasepariert): ").strip()
        if langs:
            tech_stack["languages"] = [l.strip() for l in langs.split(",")]

        frameworks = input("  Frameworks/Tools (z.B. ROS 2, Gazebo): ").strip()
        if frameworks:
            tech_stack["frameworks"] = [f.strip() for f in frameworks.split(",")]

        if tech_stack:
            profile["tech_stack"] = tech_stack

        # Speichern
        if profile:
            self.set_profile_field("user_info", profile, require_approval=True)
            return profile

        return {}

    def build_system_prompt(self) -> str:
        """
        Baut System-Prompt basierend auf User-Profil.
        """
        profile = self.get_profile()
        user_info = profile.get("user_info", {})

        name = user_info.get("name", "User")
        role = user_info.get("role", "Developer")
        tech_stack = user_info.get("tech_stack", {})

        tech_desc = ""
        if tech_stack:
            ide = tech_stack.get("ide", "")
            langs = tech_stack.get("languages", [])
            frameworks = tech_stack.get("frameworks", [])
            
            parts = []
            if ide:
                parts.append(f"IDE: {ide}")
            if langs:
                parts.append(f"Languages: {', '.join(langs)}")
            if frameworks:
                parts.append(f"Frameworks: {', '.join(frameworks)}")
            
            tech_desc = "\n".join(parts)

        system = f"""You are a helpful, local AI assistant.

USER PROFILE:
- Name: {name}
- Role: {role}
- Tech Stack:
{tech_desc if tech_desc else '  (not configured)'}

TOOL USE:
If tools are available, use Ollama's native structured tool-calling mechanism.
Never print JSON tool calls as normal assistant text.
If you do not need a tool, answer normally in natural language.

BUILDING / CODING REQUESTS:
- If the user asks you to code, build, create, make a game/app/tool/file, or
  "mach das", use the available workbench file tools instead of only explaining.
- Create real files with `wb_write_file` in your own workbench/sandbox, then tell
  the user the exact created filenames and how to run/open them.
- If multiple files are needed, create all required files. Keep the first version
  small but runnable.
- Do not claim that you created a file unless a tool call actually succeeded.
- If a requested action is outside your allowed workspace or needs execution,
  ask for explicit approval and give a copyable fallback.

IMPORTANT:
- NEVER make up tool results. Always use the real tools.
- NEVER use tools for permanent deletions or dangerous operations.
- If the user asks whether you can see the monitor/screen, answer based on
  the provided visual context: screenshots/window titles may be available,
  while readable screen text requires OCR.
- You are read-only toward external applications by default. Only control an
  external app when the local runtime has asked for explicit per-action user
  approval. Never click or move the mouse. Prefer drafting copyable text.
- Keep responses helpful, factual, and in the user's preferred language.
"""
        return system
    
    def close(self):
        """Close database connections."""
        try:
            if hasattr(self, '_conn') and self._conn:
                self._conn.close()
        except Exception:
            pass
