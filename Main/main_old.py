"""
Personal Agent (LOCAL + FREE) — Ollama edition (Windows 11)

- CLI chat
- Local LLM via Ollama: http://localhost:11434/api/chat
- Safe tools: save_note, list_notes, run_command (allowlist + ALWAYS approval)
- SQLite memory + periodic summary
- Sandbox restricted to ./agent_sandbox

Setup:
1) Install Ollama
2) In PowerShell:  ollama pull qwen2.5:7b-instruct
3) pip install requests
4) Run: python Main/main.py
"""

from __future__ import annotations
import sys

import json
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import ipaddress
from urllib.parse import urlparse

import requests
import re
from urllib.parse import quote_plus, unquote

# =========================
# Config
# =========================

OLLAMA_MODEL = "qwen2.5:7b-instruct"  # you can change later
OLLAMA_URL = "http://localhost:11434/api/chat"

SANDBOX_DIR = Path("./agent_sandbox").resolve()
NOTES_DIR = (SANDBOX_DIR / "notes").resolve()
DB_PATH = (SANDBOX_DIR / "memory.sqlite3").resolve()
WORKBENCH_DIR = (SANDBOX_DIR / "workbench").resolve()
WORKBENCH_VENV_DIR = (SANDBOX_DIR / ".venv_workbench").resolve()
WORKBENCH_PYTHON = (WORKBENCH_VENV_DIR / "Scripts" / "python.exe").resolve()

RUN_ALLOWLIST = {
    "python": {"-c", "-m"},
    "python.exe": {"-c", "-m"},
    "git": {"status", "diff", "log", "pull", "branch", "rev-parse"},
    "git.exe": {"status", "diff", "log", "pull", "branch", "rev-parse"},
}


BLOCKED_TOKENS = {
    "rm", "del", "erase", "format", "shutdown", "reboot",
    "reg", "powershell", "pwsh", "cmd", "curl", "wget", "certutil","pip", "pip3"
}

MAX_STDOUT_CHARS = 4000
MAX_STDERR_CHARS = 4000
COMMAND_TIMEOUT_SEC = 120
SUMMARY_EVERY_TURNS = 12
MAX_TOOL_HOPS = 12  # max tool calls per user message


# =========================
# Utilities
# =========================
def ensure_workbench_venv_interactive() -> tuple[bool, str]:
    ensure_sandbox()
    if WORKBENCH_PYTHON.exists():
        return True, "ok"

    print("\n=== APPROVAL REQUIRED (CREATE WORKBENCH VENV) ===")
    print("Missing:", str(WORKBENCH_VENV_DIR))
    ans = input("Create now? [y/N] ").strip().lower()
    if ans != "y":
        return False, "User denied venv creation."

    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(WORKBENCH_VENV_DIR)],
            cwd=str(SANDBOX_DIR),
            capture_output=True,
            text=True,
            timeout=300,
            shell=False,
        )
        subprocess.run(
            [str(WORKBENCH_PYTHON), "-m", "pip", "install", "--upgrade", "pip"],
            cwd=str(WORKBENCH_DIR),
            capture_output=True,
            text=True,
            timeout=300,
            shell=False,
        )
        return (WORKBENCH_PYTHON.exists(), "created")
    except Exception as e:
        return False, str(e)



def progress_bar(i: int, n: int, width: int = 20) -> str:
    n = max(1, n)
    i = max(0, min(i, n))
    filled = int(width * i / n)
    return "[" + ("#" * filled) + ("-" * (width - filled)) + f"] {i}/{n}"

def ensure_sandbox() -> None:
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    WORKBENCH_DIR.mkdir(parents=True, exist_ok=True)

def is_within(base: Path, target: Path) -> bool:
    try:
        base = base.resolve()
        target = target.resolve()
        return base == target or base in target.parents
    except Exception:
        return False

def sanitize_filename(name: str) -> str:
    safe = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
    safe = safe[:80] if safe else "note"
    return safe

def tail(s: str, n: int) -> str:
    return s[-n:] if len(s) > n else s


# =========================
# SQLite Memory
# =========================

def db_connect() -> sqlite3.Connection:
    ensure_sandbox()
    conn = sqlite3.connect(DB_PATH)
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
    conn.commit()
    return conn

def db_add_message(conn: sqlite3.Connection, role: str, content: str) -> None:
    conn.execute(
        "INSERT INTO messages(ts, role, content) VALUES(?,?,?)",
        (int(time.time()), role, content),
    )
    conn.commit()

def db_get_recent_messages(conn: sqlite3.Connection, limit: int = 30) -> List[Tuple[str, str]]:
    cur = conn.execute(
        "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    rows.reverse()
    return [(r[0], r[1]) for r in rows]

def db_get_latest_summary(conn: sqlite3.Connection) -> Optional[str]:
    cur = conn.execute("SELECT summary FROM summaries ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    return row[0] if row else None

def db_add_summary(conn: sqlite3.Connection, summary: str) -> None:
    conn.execute(
        "INSERT INTO summaries(ts, summary) VALUES(?,?)",
        (int(time.time()), summary),
    )
    conn.commit()


# =========================
# Tools (safe)
# =========================
def tool_wb_write_file(filename: str, content: str) -> dict:
    ensure_sandbox()
    # nur innerhalb der Workbench
    filename = filename.strip().replace("\\", "/")
    if filename.startswith("/") or ".." in filename:
        return {"ok": False, "error": "Invalid filename."}

    path = (WORKBENCH_DIR / filename).resolve()
    if not is_within(WORKBENCH_DIR, path):
        return {"ok": False, "error": "Path must be inside workbench."}

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"ok": True, "file": str(path)}

def tool_wb_read_file(filename: str, max_chars: int = 8000) -> dict:
    ensure_sandbox()
    filename = filename.strip().replace("\\", "/")
    if filename.startswith("/") or ".." in filename:
        return {"ok": False, "error": "Invalid filename."}

    path = (WORKBENCH_DIR / filename).resolve()
    if not is_within(WORKBENCH_DIR, path) or not path.exists():
        return {"ok": False, "error": "File not found in workbench."}

    txt = path.read_text(encoding="utf-8", errors="replace")
    return {"ok": True, "file": str(path), "content": txt[:max_chars]}

def tool_wb_run_python(filename: str, args: list[str] | None = None) -> dict:
    """
    Führt ein Python-Script NUR aus agent_sandbox/workbench aus.
    Nutzt agent_sandbox/.venv_workbench, falls vorhanden.
    Immer mit User-Approval.
    """
    ensure_sandbox()
    args = args or []

    filename = filename.strip().replace("\\", "/")
    if filename.startswith("/") or ".." in filename:
        return {"ok": False, "error": "Invalid filename."}

    script_path = (WORKBENCH_DIR / filename).resolve()
    if not is_within(WORKBENCH_DIR, script_path) or not script_path.exists():
        return {"ok": False, "error": "Script not found in workbench."}

    ok, reason = ensure_workbench_venv_interactive()
    if not ok:
        return {"ok": False, "error": reason}
    py = WORKBENCH_PYTHON

    # Approval
    cmd = [str(py), str(script_path)] + args
    print("\n=== APPROVAL REQUIRED (WORKBENCH RUN) ===")
    print("Command:", cmd)
    print("CWD:", str(WORKBENCH_DIR))
    ans = input("Execute? [y/N] ").strip().lower()
    if ans != "y":
        return {"ok": False, "error": "User denied execution."}

    try:
        p = subprocess.run(
            cmd,
            cwd=str(WORKBENCH_DIR),
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SEC,
            shell=False,
        )
        return {
            "ok": p.returncode == 0,
            "returncode": p.returncode,
            "stdout": tail(p.stdout or "", MAX_STDOUT_CHARS),
            "stderr": tail(p.stderr or "", MAX_STDERR_CHARS),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timeout after {COMMAND_TIMEOUT_SEC}s."}
    except Exception as e:
        return {"ok": False, "error": str(e)}

_pkg_re = re.compile(r"^[a-zA-Z0-9_.-]+$")

def tool_wb_pip_install(packages: list[str]) -> dict:
    """
    Installiert Pakete in agent_sandbox/.venv_workbench.
    Immer mit User-Approval. Nur einfache Paketnamen (keine URLs, keine Flags).
    """
    ensure_sandbox()
    ok, reason = ensure_workbench_venv_interactive()
    if not ok:
        return {"ok": False, "error": reason}


    if not packages or any((not _pkg_re.match(p)) for p in packages):
        return {"ok": False, "error": "Invalid package list. Use simple names like 'pandas', 'seaborn'."}

    cmd = [str(WORKBENCH_PYTHON), "-m", "pip", "install"] + packages

    print("\n=== APPROVAL REQUIRED (PIP INSTALL) ===")
    print("Command:", cmd)
    ans = input("Execute? [y/N] ").strip().lower()
    if ans != "y":
        return {"ok": False, "error": "User denied installation."}

    try:
        p = subprocess.run(
            cmd,
            cwd=str(WORKBENCH_DIR),
            capture_output=True,
            text=True,
            timeout=300,
            shell=False,
        )
        return {
            "ok": p.returncode == 0,
            "returncode": p.returncode,
            "stdout": tail(p.stdout or "", MAX_STDOUT_CHARS),
            "stderr": tail(p.stderr or "", MAX_STDERR_CHARS),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

def tool_web_search(query: str, max_results: int = 5) -> dict:
    """
    Leichte Websuche (ohne Google-API) über DuckDuckGo Lite HTML.
    Reicht meistens, um Python-Fehler zu finden.
    """
    ensure_sandbox()
    max_results = max(1, min(int(max_results), 10))
    q = query.strip()
    if not q:
        return {"ok": False, "error": "Empty query."}

    url = "https://lite.duckduckgo.com/lite/?q=" + quote_plus(q)
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        html = r.text

        # DuckDuckGo lite: Links sind oft <a rel="nofollow" href="...">Title</a>
        links = []
        for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.I | re.S):
            href = m.group(1)
            title = re.sub(r"<.*?>", "", m.group(2)).strip()
            if not title:
                continue
            if "duckduckgo.com/l/?" in href and "uddg=" in href:
                # try extract real url
                m2 = re.search(r"uddg=([^&]+)", href)
                if m2:
                    href = unquote(m2.group(1))
            if href.startswith("http"):
                links.append({"title": title[:120], "url": href})
            if len(links) >= max_results:
                break

        return {"ok": True, "query": q, "results": links}
    except Exception as e:
        return {"ok": False, "error": str(e), "hint": "Internet verfügbar? DDG blockt manchmal. Alternative: manuell suchen oder später API einbauen."}


def _is_private_target(host: str) -> bool:
    host = (host or "").strip().lower()
    if host in {"localhost"} or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
    except ValueError:
        # Hostname (kein IP literal) → erlauben
        return False

def tool_web_fetch(url: str, max_chars: int = 12000) -> dict:
    ensure_sandbox()
    url = (url or "").strip()
    if not url:
        return {"ok": False, "error": "Empty url."}

    u = urlparse(url)
    if u.scheme not in {"http", "https"}:
        return {"ok": False, "error": "Only http/https allowed."}
    if _is_private_target(u.hostname or ""):
        return {"ok": False, "error": "Blocked private/local target."}

    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        text = r.text
        return {"ok": True, "url": url, "content": text[:max_chars]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def tool_save_note(title: str, text: str) -> Dict[str, Any]:
    ensure_sandbox()
    fname = sanitize_filename(title) + ".txt"
    path = (NOTES_DIR / fname).resolve()

    if not is_within(NOTES_DIR, path):
        return {"ok": False, "error": "Invalid note path."}

    path.write_text(text, encoding="utf-8")
    return {"ok": True, "file": str(path)}

def tool_list_notes() -> Dict[str, Any]:
    ensure_sandbox()
    notes = sorted([p.name for p in NOTES_DIR.glob("*.txt")])
    return {"ok": True, "notes": notes}

def _is_args_safe(program: str, args: List[str]) -> Tuple[bool, str]:
    if program.lower() in BLOCKED_TOKENS:
        return False, f"Program blocked: {program}"

    if program not in RUN_ALLOWLIST:
        return False, f"Program not in allowlist: {program}"

    joined = " ".join([program] + args).lower()
    for tok in BLOCKED_TOKENS:
        if tok in joined.split():
            return False, f"Blocked token detected: {tok}"

    allowed_first = RUN_ALLOWLIST[program]
    if not args:
        return False, "Args required for this program."
    if args[0] not in allowed_first:
        return False, f"First arg '{args[0]}' not allowed for {program}."

    return True, "OK"

def tool_run_command(program: str, args: List[str], cwd: Optional[str] = None) -> Dict[str, Any]:
    ensure_sandbox()

    workdir = SANDBOX_DIR
    if cwd:
        candidate = Path(cwd).expanduser().resolve()
        if not is_within(SANDBOX_DIR, candidate):
            return {"ok": False, "error": "cwd must be inside sandbox."}
        workdir = candidate

    ok, reason = _is_args_safe(program, args)
    if not ok:
        return {"ok": False, "error": reason}

    cmd = [program] + args

    print("\n=== APPROVAL REQUIRED ===")
    print("Proposed command:", cmd)
    print("Working directory:", str(workdir))
    ans = input("Execute? [y/N] ").strip().lower()
    if ans != "y":
        return {"ok": False, "error": "User denied execution."}

    try:
        p = subprocess.run(
            cmd,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SEC,
            shell=False,
        )
        return {
            "ok": p.returncode == 0,
            "returncode": p.returncode,
            "stdout": tail(p.stdout or "", MAX_STDOUT_CHARS),
            "stderr": tail(p.stderr or "", MAX_STDERR_CHARS),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Command timed out after {COMMAND_TIMEOUT_SEC}s."}
    except Exception as e:
        return {"ok": False, "error": str(e)}

TOOL_FUNCS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "save_note": tool_save_note,
    "list_notes": tool_list_notes,
    "run_command": tool_run_command,
    "wb_write_file": tool_wb_write_file,
    "wb_read_file": tool_wb_read_file,
    "wb_run_python": tool_wb_run_python,
    "wb_pip_install": tool_wb_pip_install,
    "web_search": tool_web_search,
    "web_fetch": tool_web_fetch,
}


# =========================
# Ollama Chat + Tool Protocol
# =========================

SYSTEM_PROMPT = (
    "You are a personal assistant running locally for the user.\n"
    "You have tools you can request.\n\n"
    "TOOL PROTOCOL (VERY IMPORTANT):\n"
    "If you want to call a tool, respond with EXACTLY ONE JSON object AND NOTHING ELSE.\n"
    "No extra text before/after. No markdown. No code fences.\n"
    "Schema:\n"
    "{\"tool\":\"<name>\",\"args\":{...}}\n\n"
    "Allowed tool names:\n"
    "- save_note (args: {\"title\": str, \"text\": str})\n"
    "- list_notes (args: {})\n"
    "- run_command (args: {\"program\": str, \"args\": [str], \"cwd\": str|null})\n"
    "- wb_write_file (args: {\"filename\": str, \"content\": str})\n"
    "- wb_read_file (args: {\"filename\": str, \"max_chars\": int})\n"
    "- wb_run_python (args: {\"filename\": str, \"args\": [str]})\n"
    "- wb_pip_install (args: {\"packages\": [str]})\n"
    "- web_search (args: {\"query\": str, \"max_results\": int})\n\n"
    "- web_fetch (args: {\"url\": str, \"max_chars\": int})\n"
    "RULES:\n"
    "- Python scripts MUST be created with wb_write_file (NOT save_note).\n"
    "- When using a tool: output ONLY the JSON object.\n"
    "Otherwise, respond normally in German.\n"
    "Never invent tool outputs.\n"
)



def ollama_chat(messages: List[Dict[str, str]]) -> str:
    r = requests.post(
        OLLAMA_URL,
        json={"model": OLLAMA_MODEL, "messages": messages, "stream": False},
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()
    return (data.get("message", {}) or {}).get("content", "") or ""

def try_parse_tool_call(text: str) -> Optional[Dict[str, Any]]:
    """
    Accepts either:
      - pure JSON reply
      - or a reply that contains a single-line JSON object (common model behavior)
    """
    text = (text or "").strip()
    if not text:
        return None

    candidates: List[str] = []

    # 1) pure JSON
    if text.startswith("{") and text.endswith("}"):
        candidates.append(text)

    # 2) JSON object on its own line (recommended)
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("{") and s.endswith("}"):
            candidates.append(s)

    # try from last to first (usually the JSON is at the end)
    for cand in reversed(candidates):
        try:
            obj = json.loads(cand)
        except Exception:
            continue

        if not isinstance(obj, dict):
            continue
        if "tool" not in obj or "args" not in obj:
            continue

        tool = obj.get("tool")
        args = obj.get("args")

        if tool not in TOOL_FUNCS or not isinstance(args, dict):
            return {"tool": tool, "args": args if isinstance(args, dict) else {}, "invalid": True}

        return obj

    return None


def build_messages(conn: sqlite3.Connection, user_text: str) -> List[Dict[str, str]]:
    latest_summary = db_get_latest_summary(conn)
    recent = db_get_recent_messages(conn, limit=20)

    messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if latest_summary:
        messages.append({"role": "system", "content": f"Memory summary:\n{latest_summary}"})

    for role, content in recent:
        # Ollama expects system/user/assistant roles
        if role not in {"system", "user", "assistant"}:
            role = "user"
        messages.append({"role": role, "content": content})

    # Verhindere Doppelung, falls user_text gerade schon in recent steht
    if not recent or recent[-1][0] != "user" or recent[-1][1].strip() != user_text.strip():
        messages.append({"role": "user", "content": user_text})
    return messages


def summarize_if_needed(conn: sqlite3.Connection, turn_count: int) -> None:
    if turn_count % SUMMARY_EVERY_TURNS != 0:
        return
    recent = db_get_recent_messages(conn, limit=50)
    prev = db_get_latest_summary(conn) or "(none)"
    msgs = [
        {"role": "system", "content": "You summarize chats for future context. Be concise and factual."},
        {"role": "user", "content":
            "Refresh a running summary: goals, preferences, current tasks, decisions. Omit fluff.\n\n"
            f"Previous summary:\n{prev}\n\nRecent messages:\n{json.dumps(recent, ensure_ascii=False)}"
        }
    ]
    summary = ollama_chat(msgs).strip()
    if summary:
        db_add_summary(conn, summary)

def run_turn_with_tools(conn: sqlite3.Connection, user_text: str, max_hops: int = MAX_TOOL_HOPS, show_progress: bool = False, force_tools: bool = False) -> str:
    messages = build_messages(conn, user_text)
    max_hops = max(1, int(max_hops))

    start_all = time.time()

    for step in range(max_hops):
        if show_progress:
            bar = progress_bar(step, max_hops)
            print(f"\n{bar} 🤔 Modell denkt...")

        t0 = time.time()
        reply = ollama_chat(messages).strip()
        t1 = time.time()

        if show_progress:
            bar = progress_bar(step + 1, max_hops)
            print(f"{bar} ✅ Modell-Antwort ({t1 - t0:.2f}s)")

        tool_call = try_parse_tool_call(reply)

        # kein Tool → fertig
        if tool_call is None:
            if force_tools and request_likely_needs_tools(user_text) and step < max_hops - 1:
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": "Du MUSST jetzt ein Tool benutzen. Antworte NUR mit EINEM JSON tool-call (wb_read_file/wb_write_file/wb_run_python/wb_pip_install/web_search/web_fetch)."})
                continue
            return reply


        # invalid tool call
        if tool_call.get("invalid"):
            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "user", "content": "Tool call invalid. Output ONLY one valid JSON tool call (no extra text)."})

            continue

        tool = tool_call["tool"]
        args = tool_call["args"]

        if show_progress:
            print(f"🔧 Tool: {tool} args={args}")

        # Execute tool
        try:
            out = TOOL_FUNCS[tool](**args)
        except Exception as e:
            out = {"ok": False, "error": str(e)}

        if show_progress:
            ok = out.get("ok", False)
            print(f"🔧 Tool-Result: ok={ok}")
            if not ok:
                err = out.get("error") or out.get("stderr")
                if err:
                    print("↳ Fehler (gekürzt):", tail(str(err), 600))

        # Feed tool output back
        messages.append({"role": "assistant", "content": reply})
        messages.append({"role": "user", "content": f"TOOL_OUTPUT {tool}: {json.dumps(out, ensure_ascii=False)}"})

    if show_progress:
        print(f"\n⚠️ Max steps erreicht ({max_hops}). Gesamtzeit: {time.time() - start_all:.1f}s")
    return "Ich habe zu viele Tool-Schritte versucht. Erhöhe das Limit (Auto-Mode) oder gib einen Selftest/Erfolgskriterium."

# =========================
# Main CLI
# =========================
def request_likely_needs_tools(user_text: str) -> bool:
    t = (user_text or "").lower()
    return any(k in t for k in ["fix", "korrig", "repar", "starte", "start", "run", "ausführ", "install", "pip", ".py", "pygame", "pong"])

def main() -> None:
    ensure_sandbox()
    conn = db_connect()

    print("Personal Agent (LOCAL / Ollama)")
    print("Type 'exit' to quit.\n")
    print(f"Sandbox: {SANDBOX_DIR}\n")
    print(f"Ollama model: {OLLAMA_MODEL}\n")

    turn_count = 0

    while True:
        user_text = input("You: ").strip()
        # Auto-mode: /auto 20 <deine Aufgabe>
        if user_text.lower().startswith("/auto"):
            parts = user_text.split(maxsplit=2)
            hops = 60
            task = ""
            if len(parts) >= 2:
                try:
                    hops = int(parts[1])
                except:
                    hops = 20
            if len(parts) == 3:
                task = parts[2].strip()

            if not task:
                print("AI: Nutzung: /auto <max_steps> <aufgabe>\n")
                continue

            db_add_message(conn, "user", task)
            turn_count += 1
            summarize_if_needed(conn, turn_count)

            answer = run_turn_with_tools(conn, task, max_hops=hops, show_progress=True, force_tools=True)

            print("AI:", answer, "\n")
            db_add_message(conn, "assistant", answer)
            continue

        if not user_text:
            continue
        if user_text.lower() in {"exit", "quit"}:
            break

        db_add_message(conn, "user", user_text)
        turn_count += 1
        summarize_if_needed(conn, turn_count)

        answer = run_turn_with_tools(conn, user_text)
        print("AI:", answer, "\n")
        db_add_message(conn, "assistant", answer)

    conn.close()

if __name__ == "__main__":
    main()
