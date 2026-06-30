"""
Phase 3 Main CLI: Screen-Aware Agent with RAG
"""
import sys
import os
import time
import ctypes
import re
import json
import shlex
from ctypes import wintypes
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from agent_system.core import OllamaNative, MemoryManager, SandboxManager, MultimodalAgent
from agent_system.core.model_config import ModelConfig
from agent_system.tools.workbench import WorkbenchTools
from agent_system.tools.web import WebTools
from agent_system.tools.system import SystemTools
from agent_system.tools import NoteTools
from agent_system.tools.code_repair import CodeRepairTools
from agent_system.agents.orchestrator_rag import OrchestratorWithRAG
from agent_system.observers.audio_listener import AudioListener, MultiAudioListener
from agent_system.observers.code_watcher import CodeWatcher, CodeFinding
from agent_system.ui import AvatarWindow
from agent_system.vision import VisionAnalyzer
from agent_system.generation import ComfyUIClient, VideoGenerationClient
from agent_system.research import ResearchProjectManager


def create_toolset(sandbox_mgr: SandboxManager, enable_web: bool = False) -> dict:
    """Create all available tools."""
    wb = WorkbenchTools(sandbox_mgr)
    sys_tools = SystemTools(sandbox_mgr)
    notes = NoteTools(sandbox_mgr)
    repairs = CodeRepairTools(Path.cwd(), sandbox_mgr)

    tools = {
        "wb_write_file": wb.wb_write_file,
        "wb_read_file": wb.wb_read_file,
        "wb_run_python": wb.wb_run_python,
        "wb_pip_install": wb.wb_pip_install,
        "run_command": sys_tools.run_command,
        "save_note": notes.save_note,
        "list_notes": notes.list_notes,
        "propose_file_replacement": repairs.propose_file_replacement,
        "apply_file_replacement": repairs.apply_file_replacement,
    }

    if enable_web:
        web = WebTools()
        tools.update({
            "web_search": web.web_search,
            "web_fetch": web.web_fetch,
        })

    return tools


LAST_ALERT = {"signature": None, "time": 0.0}


def context_callback(context):
    """Multimodal context callback."""
    if context.detected_errors:
        if os.environ.get("LOCAL_AGENT_SCREEN_ALERTS", "0") != "1":
            return
        first = context.detected_errors[0]
        signature = (context.active_window, first.get("line"), first.get("type"))
        now = time.time()
        if signature != LAST_ALERT["signature"] or now - LAST_ALERT["time"] > 30:
            LAST_ALERT["signature"] = signature
            LAST_ALERT["time"] = now
            print(
                f"\nSTOPP: {len(context.detected_errors)} possible error(s) in active window. "
                f"Line {first.get('line', '?')}: {first.get('type', 'unknown')}"
            )


def code_feedback_callback(finding: CodeFinding) -> None:
    """Print proactive read-only code feedback."""
    prefix = "STOPP" if finding.severity == "error" else "Hinweis"
    print(
        f"\n{prefix}: {finding.file}:{finding.line} - {finding.message}\n"
        "Ich beobachte nur read-only und aendere deinen Workspace nicht."
    )


def is_professional_code_review_request(text: str) -> bool:
    """Detect natural-language requests for architecture/security code review."""
    t = text.lower()
    wants_scan = any(word in t for word in ("scan", "prüf", "pruef", "schaue", "review", "analys", "durch"))
    target_code = any(word in t for word in ("code", "workspace", "projekt", "ki agent", "agent"))
    depth = any(word in t for word in ("professionell", "architektur", "security", "sicherheit", "probleme", "lücken", "luecken", "fehler"))
    return wants_scan and target_code and depth


def professional_code_review(code_watcher: CodeWatcher, sandbox_dir: Path) -> str:
    """Run a read-only architecture/security review over the allowed code scope."""
    scope_msg = apply_code_scope(code_watcher, sandbox_dir)
    if load_avatar_permissions(sandbox_dir).get("code_scope") == "disabled":
        return scope_msg

    findings = code_watcher.scan_full_once()
    roots = [str(p) for p in code_watcher.allowed_roots]
    severity_order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (severity_order.get(f.severity, 9), f.file, f.line))

    by_severity = {"error": 0, "warning": 0, "info": 0}
    for finding in findings:
        by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1

    lines = [
        "Professioneller Read-only Code-Review",
        f"Scope: {scope_msg}",
        f"Roots: {', '.join(roots) if roots else '(keine)'}",
        f"Findings: errors={by_severity.get('error', 0)}, warnings={by_severity.get('warning', 0)}, info={by_severity.get('info', 0)}",
        "",
    ]

    if findings:
        lines.append("Konkrete Findings:")
        for finding in findings[:40]:
            lines.append(f"- {finding.severity.upper()}: {finding.file}:{finding.line} - {finding.message}")
        if len(findings) > 40:
            lines.append(f"- ... {len(findings) - 40} weitere Findings")
    else:
        lines.append("Keine Syntax-, Architektur- oder Security-Heuristik-Findings im erlaubten Scope gefunden.")

    lines.extend([
        "",
        "Architektur-Einschaetzung:",
        "- Positiv: klare Trennung in core, agents, observers, tools, memory, ui, vision und generation.",
        "- Positiv: kritische Ausfuehrungspfade laufen ueber Approval/Sandbox statt stiller Ausfuehrung.",
        "- Positiv: Screen-/Code-Scope ist inzwischen getrennt steuerbar und read-only.",
        "- Achtung: main_phase3.py ist sehr gross und enthaelt viele CLI-Commands; spaeter in command modules aufteilen.",
        "- Achtung: Heuristik-Scanner ersetzt kein vollstaendiges Security-Audit, findet aber die wichtigsten lokalen Risiken schnell.",
        "",
        "Naechste sinnvolle Haertung:",
        "- Audit-Log auch fuer Discord/Audio/Scope-Aenderungen erweitern.",
        "- Stop-/Status-Befehl fuer versteckte Hintergrundprozesse zentralisieren.",
        "- CodeWatcher-Regeln fuer weitere Sprachen je Projekt erweitern.",
    ])
    return "\n".join(lines)


def parse_research_args(user_input: str) -> list[str]:
    try:
        return shlex.split(user_input)
    except ValueError:
        return user_input.split()


def is_research_auto_command(user_input: str) -> bool:
    """Match /research_auto without catching /research_autopilot_*."""
    lowered = user_input.lower()
    return lowered == "/research_auto" or lowered.startswith("/research_auto ")


def is_internal_autopilot_action(user_input: str) -> bool:
    """Detect internal controller action names typed by the user."""
    action = user_input.strip().lower()
    return action in {
        "generate_new_lemma",
        "refine_existing_lemma",
        "disprove_lemma",
        "compare_with_known_criterion",
        "run_experiment",
        "retrieve_literature",
        "verify_claims",
        "mark_stagnated",
        "switch_approach",
        "summarize_progress",
        "export_checkpoint",
        "clean_invalid_domain_noise",
    }


def is_monitor_question(text: str) -> bool:
    """Detect simple screen-awareness status questions."""
    t = text.lower()
    screen_words = ("monitor", "bildschirm", "screen", "screenshot", "offen", "fenster", "video", "läuft", "laeuft")
    intent_words = ("siehst", "sehen", "sichtbar", "erkennst", "kannst du", "was hab", "was ist", "welches")
    return any(word in t for word in screen_words) and any(word in t for word in intent_words)


def is_external_write_request(text: str) -> bool:
    """Detect requests to type/send into external apps."""
    t = text.lower()
    app = any(word in t for word in ("discord", "dc", "zoom", "teams", "whatsapp", "telegram"))
    action = any(word in t for word in ("schreib", "schreibe", "send", "sende", "schick", "schicke", "schicken", "antwort", "poste"))
    followup_action = any(word in t for word in ("schreib", "schreibe", "schicken", "schick", "schicke", "senden", "send")) and not app
    if followup_action:
        return True
    return app and action


def is_discord_summary_request(text: str) -> bool:
    """Detect requests to summarize visible Discord/meeting context."""
    t = text.lower()
    wants_summary = any(word in t for word in ("zusammenfassung", "zusammenfassen", "notizen", "mitschrift"))
    target_discord = any(word in t for word in ("discord", "dc", "chat", "gespraech", "gespräch"))
    send_it = any(word in t for word in ("schick", "schicke", "sende", "send", "post", "schreib"))
    return wants_summary and (target_discord or send_it)


def is_listen_start_request(text: str) -> bool:
    t = text.lower()
    return any(phrase in t for phrase in (
        "starte mithören", "starte mithoeren", "hör live zu", "hoer live zu",
        "youtube mithören", "youtube mithoeren", "hör mir zu", "hoer mir zu",
        "hör mich", "hoer mich", "ich rede mit mikro", "ich rede mit dem mikro",
        "mikro aktivieren", "mikrofon aktivieren", "aktiviere mein mikro",
    ))


def is_listen_all_request(text: str) -> bool:
    t = text.lower()
    return any(phrase in t for phrase in ("alle audio", "alles audio", "alle quellen", "browser und discord", "youtube und discord"))


def is_voice_to_agent_request(text: str) -> bool:
    t = text.lower()
    return any(phrase in t for phrase in (
        "hör mir zu", "hoer mir zu", "hör mich", "hoer mich",
        "ich rede mit mikro", "ich rede mit dem mikro", "ich spreche",
        "mikro aktivieren", "mikrofon aktivieren", "aktiviere mein mikro",
    ))


def is_listen_stop_request(text: str) -> bool:
    t = text.lower()
    return any(phrase in t for phrase in ("stop mithören", "stopp mithören", "stop mithoeren", "stopp mithoeren", "hör auf mitzuhören", "hoer auf mitzuhoeren"))


def build_audio_summary(agent: OrchestratorWithRAG, transcript: str) -> str:
    previous_tools = getattr(agent.ollama, "enable_tools", True)
    previous_model = agent.ollama.model
    summary_model = agent.worker_router.registry.get("audio_meeting").model
    agent.ollama.set_model(summary_model)
    agent.ollama.set_tools_enabled(False)

    messages = [{
        "role": "user",
        "content": (
        "[AUDIO TRANSCRIPT]\n"
        f"{transcript}\n\n"
        "[TASK]\n"
        "Fasse das gehoerte Audio auf Deutsch zusammen. Gruppiere nach Quelle, falls Labels "
        "wie Browser/YouTube oder Discord sichtbar sind. Gib nur die wichtigsten Infos aus: "
        "Thema, Kernaussagen, konkrete Fakten, To-dos/Empfehlungen und offene Fragen. "
        "Wenn das Transkript kaum Text enthaelt, sage das knapp."
        )
    }]

    try:
        summary, _ = agent.ollama.chat_with_tools(messages=messages)
        return summary or "(keine Zusammenfassung erzeugt)"
    except Exception as e:
        return f"Audio-Zusammenfassung fehlgeschlagen: {e}"
    finally:
        agent.ollama.set_model(previous_model)
        agent.ollama.set_tools_enabled(previous_tools)


def load_audio_config(sandbox_dir: Path) -> dict:
    path = Path(sandbox_dir) / "audio_config.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_audio_config(sandbox_dir: Path, config: dict) -> None:
    path = Path(sandbox_dir) / "audio_config.json"
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def load_avatar_permissions(sandbox_dir: Path) -> dict:
    path = Path(sandbox_dir) / "avatar_permissions.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def screen_context_allowed(multimodal: MultimodalAgent, sandbox_dir: Path) -> bool:
    """Return whether the current window may be sent to the model."""
    permissions = load_avatar_permissions(sandbox_dir)
    if not permissions.get("screen_context", True):
        return False

    scope = permissions.get("screen_scope", "active")
    if scope == "off":
        return False
    if scope in {"active", "all"}:
        return True

    category = multimodal.get_context().active_window_category
    category_map = {
        "vs_code": "vs code",
        "unity": "unity",
        "browser": "browser",
        "discord": "discord",
    }
    return category == category_map.get(scope)


def screen_title_allowed(window_title: str, multimodal: MultimodalAgent, sandbox_dir: Path) -> bool:
    """Return whether screenshots/OCR may be captured for this window title."""
    permissions = load_avatar_permissions(sandbox_dir)
    if not permissions.get("screen_context", True):
        return False

    scope = permissions.get("screen_scope", "active")
    if scope == "off":
        return False
    if scope in {"active", "all"}:
        return True

    category = multimodal.window_tracker.classify_window(window_title)
    category_map = {
        "vs_code": "vs code",
        "unity": "unity",
        "browser": "browser",
        "discord": "discord",
    }
    return category == category_map.get(scope)


def filtered_context_string(multimodal: MultimodalAgent, sandbox_dir: Path) -> str:
    """Return visual context only if the user-selected scope allows it."""
    if not screen_context_allowed(multimodal, sandbox_dir):
        permissions = load_avatar_permissions(sandbox_dir)
        scope = permissions.get("screen_scope", "active")
        active = multimodal.get_context().active_window
        return (
            "Screen-Kontext ist fuer dieses Fenster blockiert.\n"
            f"Aktives Fenster: {active}\n"
            f"Scope: {scope}"
        )
    return multimodal.get_context_string()


def apply_code_scope(code_watcher: CodeWatcher, sandbox_dir: Path) -> str:
    """Apply read-only code scope from avatar trust settings."""
    permissions = load_avatar_permissions(sandbox_dir)
    scope = permissions.get("code_scope", "agent_workspace")

    if scope == "disabled":
        code_watcher.set_allowed_roots([])
        code_watcher.stop()
        return "Code-Lesezugriff ist deaktiviert."

    if scope == "custom_project":
        raw_path = str(permissions.get("code_project_path", "")).strip()
        if raw_path:
            project = Path(raw_path).expanduser()
            if project.exists() and project.is_dir():
                code_watcher.set_allowed_roots([project])
                return f"Code-Scope: custom_project -> {project.resolve()}"
            return f"Custom-Projektpfad ist ungueltig: {raw_path}"

    code_watcher.set_allowed_roots([Path.cwd()])
    return f"Code-Scope: agent_workspace -> {Path.cwd()}"


def scope_status(multimodal: Optional[MultimodalAgent], code_watcher: CodeWatcher, sandbox_dir: Path) -> str:
    permissions = load_avatar_permissions(sandbox_dir)
    lines = ["Scope / Berechtigungen:"]
    lines.append(f"  screen_context: {permissions.get('screen_context', True)}")
    lines.append(f"  screen_scope: {permissions.get('screen_scope', 'active')}")
    if multimodal:
        ctx = multimodal.get_context()
        lines.append(f"  active_window: {ctx.active_window}")
        lines.append(f"  active_category: {ctx.active_window_category}")
        lines.append(f"  current_window_allowed: {screen_context_allowed(multimodal, sandbox_dir)}")
    lines.append(f"  code_scope: {permissions.get('code_scope', 'agent_workspace')}")
    lines.append(f"  code_project_path: {permissions.get('code_project_path', '')}")
    lines.append(f"  code_roots: {', '.join(str(p) for p in code_watcher.allowed_roots)}")
    return "\n".join(lines)


def run_audio_setup(audio_listener: AudioListener, sandbox_dir: Path) -> None:
    """Interactive setup that lets the agent ask which audio interface to use."""
    result = audio_listener.list_devices()
    if not result.get("ok"):
        print(f"\nAudio not ready: {result.get('error')}\n")
        return

    print("\nIch teste jetzt alle offenen Audio-Schnittstellen.")
    print("Starte kurz YouTube/Discord/Zoom-Audio, damit ich Signal erkennen kann.\n")

    candidates = []
    for dev in result.get("devices", []):
        idx = dev["index"]
        level = audio_listener.measure_level(device=idx, seconds=0.7)
        if not level.get("ok"):
            print(f"  {idx}: {dev['name']} -> nicht nutzbar ({level.get('error')})")
            continue

        signal = "YES" if level["has_signal"] else "NO"
        print(f"  {idx}: {dev['name']} -> signal={signal} peak={level['peak']:.4f}")
        if level["has_signal"]:
            candidates.append((idx, dev["name"], level["peak"]))

    if not candidates:
        print("\nIch habe kein Audio-Signal gefunden. Pruefe Windows/Sonar/Stereomix-Routing.\n")
        return

    best = max(candidates, key=lambda item: item[2])
    print(f"\nVorschlag: Geraet {best[0]} ({best[1]})")
    choice = input(f"Dieses Geraet als Default speichern? [Y/n] ").strip().lower()
    if choice in {"", "y", "yes", "j", "ja"}:
        config = {"default_device": best[0], "default_name": best[1]}
        save_audio_config(sandbox_dir, config)
        print(f"Gespeichert: /listen_default nutzt jetzt Geraet {best[0]}.\n")
        return

    manual = input("Andere Geraete-ID eingeben oder leer abbrechen: ").strip()
    if not manual:
        print("Audio-Setup abgebrochen.\n")
        return
    try:
        device = int(manual)
    except ValueError:
        print("Ungueltige ID.\n")
        return
    name = next((dev["name"] for dev in result.get("devices", []) if dev["index"] == device), "unknown")
    save_audio_config(sandbox_dir, {"default_device": device, "default_name": name})
    print(f"Gespeichert: /listen_default nutzt jetzt Geraet {device}.\n")


def auto_find_audio_device(audio_listener: AudioListener, prefer_microphone: bool = True) -> dict:
    """Find an open audio input automatically, preferring live signal."""
    result = audio_listener.list_devices()
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error", "audio devices unavailable")}

    devices = result.get("devices", [])
    scored = []
    for dev in devices:
        idx = dev["index"]
        level = audio_listener.measure_level(device=idx, seconds=0.5)
        if not level.get("ok"):
            continue

        name = dev.get("name", "")
        lower = name.lower()
        score = level.get("peak", 0.0)
        if level.get("has_signal"):
            score += 10.0
        if prefer_microphone and any(word in lower for word in ("mikro", "microphone", "mic")):
            score += 2.0
        if any(word in lower for word in ("soundmapper", "primärer", "primaerer")):
            score += 1.0
        scored.append({
            "index": idx,
            "name": name,
            "score": score,
            "peak": level.get("peak", 0.0),
            "has_signal": level.get("has_signal", False),
        })

    if not scored:
        return {"ok": False, "error": "No open audio input device found"}

    scored.sort(key=lambda item: item["score"], reverse=True)
    best = scored[0]
    return {"ok": True, "device": best["index"], "name": best["name"], "peak": best["peak"], "has_signal": best["has_signal"]}


def start_voice_to_agent(audio_listener: AudioListener, sandbox_dir: Path) -> str:
    """Natural-language entry point for microphone listening."""
    config = load_audio_config(sandbox_dir)
    device = config.get("default_mic_device") or config.get("default_device")
    name = config.get("default_mic_name") or config.get("default_name", "")

    if device is None:
        print("\nIch suche automatisch ein nutzbares Mikrofon. Sprich jetzt kurz etwas...")
        found = auto_find_audio_device(audio_listener, prefer_microphone=True)
        if not found.get("ok"):
            return (
                "Ich konnte kein offenes Mikrofon finden. Nutze einmal /audio_setup "
                "oder pruefe Windows Mikrofon-Berechtigungen."
            )
        device = found["device"]
        name = found["name"]
        config["default_mic_device"] = device
        config["default_mic_name"] = name
        save_audio_config(sandbox_dir, config)

    if audio_listener.is_running:
        audio_listener.stop()

    result = audio_listener.start(device=int(device), live_print=True)
    if not result.get("ok"):
        return f"Mikrofon konnte nicht gestartet werden: {result.get('error')}"

    return (
        f"Ich hoere dir jetzt ueber Mikrofon/Geraet {device} ({name}) zu. "
        "Sag oder schreibe spaeter: stop mithören. "
        f"Temp-Notizen: {audio_listener.session_dir}"
    )


def answer_external_write_request(text: str) -> str:
    """Keep the agent read-only and provide a copyable draft instead."""
    message = extract_external_message(text)
    return (
        "Ich darf externe Apps nur nach deiner ausdruecklichen Freigabe bedienen. "
        "Kopierfertiger Vorschlag:\n\n"
        f"{message}"
    )


def extract_external_message(text: str) -> str:
    """Extract the likely message body from a natural Discord send request."""
    original = text.strip()
    lower = original.lower()

    # Prefer text after an explicit app target: "auf discord hallo ..."
    for marker in (" auf discord ", " auf dc ", " in discord ", " in dc "):
        idx = lower.find(marker)
        if idx >= 0:
            after = original[idx + len(marker):].strip()
            if after:
                return polish_discord_message(after)

    # Prefer text after "dass/das": "schreib onini dass er ..."
    match = re.search(r"\b(?:dass|das)\b(.+)$", original, flags=re.IGNORECASE)
    if match:
        return polish_discord_message(match.group(1).strip())

    # Common greeting starts.
    for marker in ("hallo", "hi", "hey", "guten"):
        idx = lower.find(marker)
        if idx >= 0:
            return polish_discord_message(original[idx:].strip())

    # Remove the command part and likely recipient.
    msg = re.sub(
        r"^\s*(schreib|schreibe|send|sende|schick|schicke|schicken)\s+",
        "",
        original,
        flags=re.IGNORECASE,
    ).strip()
    parts = msg.split(maxsplit=1)
    if len(parts) == 2 and parts[0].lower() not in {"hallo", "hi", "hey"}:
        msg = parts[1]

    return polish_discord_message(msg)


def polish_discord_message(message: str) -> str:
    """Small German cleanup for dictated Discord messages."""
    msg = " ".join(message.strip().split())
    if not msg:
        return msg

    replacements = {
        "wie gehts es dir": "wie geht es dir",
        "sit": "bist",
        "nciht": "nicht",
        "schiock": "schick",
    }
    low = msg.lower()
    for wrong, right in replacements.items():
        low = low.replace(wrong, right)
    msg = low

    # "er ist/bist ..." is usually meant as direct message to the recipient.
    msg = re.sub(r"^er\s+(ist|bist)\s+", "du bist ", msg, flags=re.IGNORECASE)
    msg = re.sub(r"^er\s+ein\s+(.+)\s+(ist|bist)$", r"du bist ein \1", msg, flags=re.IGNORECASE)

    if msg:
        msg = msg[0].upper() + msg[1:]
    return msg


def set_windows_clipboard(text: str) -> None:
    """Set Windows clipboard to Unicode text using Win32 APIs."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.restype = wintypes.BOOL

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    data = (text + "\0").encode("utf-16-le")
    hglobal = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not hglobal:
        raise RuntimeError("Could not allocate clipboard memory")

    locked = kernel32.GlobalLock(hglobal)
    if not locked:
        raise RuntimeError("Could not lock clipboard memory")

    ctypes.memmove(locked, data, len(data))
    kernel32.GlobalUnlock(hglobal)

    if not user32.OpenClipboard(None):
        raise RuntimeError("Could not open clipboard")

    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, hglobal):
            raise RuntimeError("Could not set clipboard data")
    finally:
        user32.CloseClipboard()


def press_paste() -> None:
    """Paste clipboard via keyboard events."""
    user32 = ctypes.windll.user32
    KEYUP = 0x0002
    VK_CONTROL = 0x11
    VK_V = 0x56

    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_V, 0, 0, 0)
    user32.keybd_event(VK_V, 0, KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYUP, 0)


def press_enter() -> None:
    """Press Enter via keyboard events."""
    user32 = ctypes.windll.user32
    KEYUP = 0x0002
    VK_RETURN = 0x0D
    user32.keybd_event(VK_RETURN, 0, 0, 0)
    user32.keybd_event(VK_RETURN, 0, KEYUP, 0)


def send_text_to_discord(multimodal: MultimodalAgent, message: str) -> str:
    """Send prepared text to the currently focused Discord window after approval."""
    print("\n=== DISCORD SEND APPROVAL ===")
    print("Ich wuerde senden:")
    print(message)
    ans = input("Diese Nachricht in Discord senden? [y/N] ").strip().lower()
    if ans not in {"y", "yes", "j", "ja"}:
        return "Nicht gesendet. Kopierfertiger Vorschlag:\n\n" + message

    print("Fokussiere jetzt das Discord-Eingabefeld. Ich sende in 5 Sekunden...")
    time.sleep(5)

    current = multimodal.window_tracker.get_active_window()
    category = multimodal.window_tracker.classify_window(current)
    if category != "discord":
        return (
            "Abgebrochen: Das aktive Fenster ist nicht Discord "
            f"(aktuell: {current}). Kopierfertiger Vorschlag:\n\n{message}"
        )

    try:
        set_windows_clipboard(message)
        press_paste()
        print("Nachricht wurde nur eingefuegt, noch nicht gesendet.")
        ans2 = input("Jetzt Enter druecken und wirklich senden? [y/N] ").strip().lower()
        if ans2 not in {"y", "yes", "j", "ja"}:
            return "Eingefuegt, aber nicht gesendet."
        current = multimodal.window_tracker.get_active_window()
        category = multimodal.window_tracker.classify_window(current)
        if category != "discord":
            return f"Abgebrochen vor Enter: aktives Fenster ist nicht Discord (aktuell: {current})."
        press_enter()
        return "Gesendet via Discord-Fenster nach deiner Freigabe."
    except Exception as e:
        return f"Senden fehlgeschlagen: {e}\n\nKopierfertiger Vorschlag:\n\n{message}"


def maybe_send_to_discord(multimodal: MultimodalAgent, text: str) -> str:
    """Draft and send a Discord message after approval."""
    return send_text_to_discord(multimodal, extract_external_message(text))


def answer_monitor_question(multimodal: MultimodalAgent) -> str:
    """Answer from local visual context without asking the LLM."""
    ctx = multimodal.get_context()
    parts = []

    if ctx.latest_metadata:
        parts.append(f"Ja, ich bekomme Screenshots deines Monitors ({ctx.latest_metadata.width}x{ctx.latest_metadata.height}).")
    else:
        parts.append("Noch nicht: ich habe bisher keinen Screenshot-Kontext empfangen.")

    if ctx.active_window and ctx.active_window not in {"(unknown)", "(unavailable)"}:
        parts.append(f"Aktives Fenster: {ctx.active_window}.")

    if ctx.active_window_category:
        parts.append(f"Kategorie: {ctx.active_window_category}.")

    if ctx.ocr_text:
        snippet = ctx.ocr_text[:700].replace("\n", " ")
        parts.append(f"Ich kann auch Text daraus lesen. Sichtbarer Text-Auszug: {snippet}")
    else:
        parts.append("Text auf dem Bildschirm kann ich aktuell noch nicht lesen, weil EasyOCR/Tesseract fehlt.")

    return " ".join(parts)


def main():
    print("=" * 70)
    print("Ollama Multi-Agent System (Phase 3: Screen-Aware + RAG)")
    print("=" * 70)
    print()

    # Setup
    sandbox_dir = Path("./agent_sandbox")
    sandbox = SandboxManager(sandbox_dir)
    sandbox.ensure_dirs()
    print(f"✅ Sandbox: {sandbox.base_dir}")

    memory = MemoryManager(sandbox.db_path)
    print(f"✅ Memory: {sandbox.db_path}")

    model_config = ModelConfig()
    ollama = OllamaNative(model=model_config.primary("coding"), base_url="http://127.0.0.1:11434")

    role_models = {}
    try:
        for role, choice in model_config.roles.items():
            selected, installed = ollama.choose_available_model(choice.candidates())
            if selected:
                role_models[role] = selected
            else:
                role_models[role] = choice.primary
                print(f"⚠️  Missing model for {role}: wanted {choice.candidates()}. Installed: {installed}")
    except Exception as e:
        print(f"❌ Cannot query Ollama models: {e}")
        return

    print(f"✅ Chef model: {role_models['chief']}")
    print(f"✅ Reasoning model: {role_models['reasoning']}")
    print(f"✅ Coding model: {role_models['coding']}")
    print(f"✅ Vision model: {role_models['vision']}")
    print(f"✅ Vision backup: {role_models['vision_backup']}")

    ollama.set_model(role_models["coding"])
    ok, msg = ollama.health_check()
    if not ok:
        print(f"❌ {msg}")
        return
    print(f"✅ {msg}")

    enable_web = os.environ.get("LOCAL_AGENT_ENABLE_WEB", "0") == "1"
    toolset = create_toolset(sandbox, enable_web=enable_web)
    ollama.register_tools(toolset)
    print(f"✅ Registered {len(toolset)} tools")
    if not enable_web:
        print("✅ Web tools disabled (fully local mode)")

    # Phase 3: RAG-Enabled Orchestrator
    print("\n🧠 Initializing RAG Engine (Phase 3)...")
    agent = OrchestratorWithRAG(ollama, memory, sandbox)
    agent.worker_router = agent.worker_router.__class__(
        chief_model=role_models["chief"],
        coding_model=role_models["coding"],
        reasoning_model=role_models["reasoning"],
        vision_model=role_models["vision"],
        vision_backup_model=role_models["vision_backup"],
    )
    agent.register_tools(toolset)
    print("✅ RAG Orchestrator ready")

    # Multimodal
    print("\n🔭 Initializing Multimodal Agent...")
    try:
        multimodal = MultimodalAgent(
            sandbox_dir=sandbox_dir,
            screenshot_interval_sec=3.0,
            enable_ocr=True,
            enable_errors=True,
        )
        multimodal.add_context_callback(context_callback)
        print("✅ Screen-Awareness ready")
    except Exception as e:
        print(f"⚠️  Multimodal setup failed: {e}")
        multimodal = None

    # Optional local audio listener for meetings/Discord voice.
    audio_listener = AudioListener(
        sandbox_dir=sandbox_dir,
        model_name=os.environ.get("LOCAL_AGENT_WHISPER_MODEL", "base"),
        source_provider=lambda: multimodal.get_context().active_window if multimodal else "",
    )
    multi_audio_listener = MultiAudioListener(
        sandbox_dir=sandbox_dir,
        model_name=os.environ.get("LOCAL_AGENT_WHISPER_MODEL", "base"),
        source_provider=lambda: multimodal.get_context().active_window if multimodal else "",
    )
    avatar = AvatarWindow(agent=agent, sandbox_dir=sandbox_dir)
    vision = VisionAnalyzer(
        model=role_models["vision"],
        fallback_model=role_models["vision_backup"],
    )
    comfyui = ComfyUIClient(output_dir=sandbox.base_dir / "generated_images")
    video_gen = VideoGenerationClient(output_dir=sandbox.base_dir / "generated_videos")
    research = ResearchProjectManager(
        sandbox.base_dir,
        web_enabled=enable_web,
        proof_client=ollama,
        reasoning_model=role_models["reasoning"],
        research_step_model=os.environ.get("LOCAL_AGENT_RESEARCH_STEP_MODEL", "qwen2.5:7b-instruct"),
        research_critic_model=os.environ.get("LOCAL_AGENT_RESEARCH_CRITIC_MODEL", "qwen3:30b"),
        research_claim_verifier_model=os.environ.get("LOCAL_AGENT_RESEARCH_CLAIM_VERIFIER_MODEL", "deepseek-r1:32b"),
        research_formalizer_model=os.environ.get("LOCAL_AGENT_RESEARCH_FORMALIZER_MODEL", "qwen3-coder:30b"),
        research_novelty_model=os.environ.get("LOCAL_AGENT_RESEARCH_NOVELTY_MODEL", "deepseek-r1:32b"),
        research_peer_reviewer_model=os.environ.get("LOCAL_AGENT_RESEARCH_PEER_REVIEWER_MODEL", "deepseek-r1:70b"),
        research_fast_model=os.environ.get("LOCAL_AGENT_RESEARCH_FAST_MODEL", "qwen2.5:7b-instruct"),
        deep_research_model=os.environ.get("LOCAL_AGENT_DEEP_RESEARCH_MODEL", role_models["reasoning"]),
    )

    def avatar_context_callback(context):
        if avatar:
            avatar.set_context(filtered_context_string(multimodal, sandbox_dir) if multimodal else "")
            avatar.set_status(context.active_window)

    if multimodal:
        multimodal.add_context_callback(avatar_context_callback)

    code_watcher = CodeWatcher(Path.cwd(), poll_interval_sec=5.0)
    code_watcher.add_callback(code_feedback_callback)
    print(f"✅ {apply_code_scope(code_watcher, sandbox_dir)}")
    code_watch_enabled = os.environ.get("LOCAL_AGENT_CODE_WATCH", "1") == "1"
    if code_watch_enabled:
        code_watcher.start()
        print("✅ Read-only code watcher active")

    # User setup
    profile = memory.get_profile()
    if not profile:
        profile = memory.setup_user_profile()
    print()

    # Start monitoring
    if multimodal:
        multimodal.screenshot_monitor.should_capture = (
            lambda title: screen_title_allowed(title, multimodal, sandbox_dir)
        )
        print("Starting background monitoring...")
        multimodal.start_monitoring()
        print()

    # Main loop
    print("Type 'exit' to quit.")
    print("Type '/help' for available commands.")
    print()

    try:
        while True:
            try:
                user_input = input("You: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye!")
                break

            if not user_input:
                continue

            if user_input.lower() in {"exit", "quit"}:
                print("Goodbye!")
                break

            if multimodal and is_monitor_question(user_input):
                print(f"\nAI: {answer_monitor_question(multimodal)}\n")
                continue

            if is_voice_to_agent_request(user_input):
                print(f"\nAI: {start_voice_to_agent(audio_listener, sandbox_dir)}\n")
                continue

            if is_listen_start_request(user_input) or is_listen_all_request(user_input):
                if is_listen_all_request(user_input):
                    result = multi_audio_listener.start(live_print=True)
                else:
                    result = audio_listener.start(live_print=True)
                if not result.get("ok"):
                    print(f"\nAudio not ready: {result.get('error')}")
                    print(f"Missing: {', '.join(result.get('missing', []))}")
                    print("Install: .\\.venv_personal_agent\\Scripts\\python.exe -m pip install sounddevice numpy faster-whisper\n")
                else:
                    if result.get("started"):
                        print(f"\nLive-Mithoeren fuer Audioquellen gestartet: {result.get('started')}")
                    else:
                        print("\nLive-Mithoeren gestartet.")
                    print("Sage/schreibe: stop mithören\n")
                continue

            if is_listen_stop_request(user_input):
                audio_listener.stop()
                multi_audio_listener.stop()
                transcript = "\n".join(
                    part for part in [
                        audio_listener.get_transcript_text(),
                        multi_audio_listener.get_transcript_text(),
                    ]
                    if part.strip()
                )
                if not transcript.strip():
                    print("\nAI: Mithoeren gestoppt. Es wurde noch kein Transkript erkannt.\n")
                    continue
                summary = build_audio_summary(agent, transcript)
                print(f"\nZusammenfassung:\n{summary}\n")
                continue

            if multimodal and is_discord_summary_request(user_input):
                ctx = filtered_context_string(multimodal, sandbox_dir)
                if not ctx.strip():
                    print("\nAI: Ich habe gerade keinen sichtbaren Kontext fuer eine Zusammenfassung.\n")
                    continue
                prompt = (
                    "[SCREEN CONTEXT]\n"
                    f"{ctx}\n\n"
                    "[TASK]\n"
                    "Fasse den sichtbar erkannten Discord-/Chat-Kontext kurz auf Deutsch zusammen. "
                    "Schreibe nur die Zusammenfassung, keine Meta-Erklaerung. "
                    "Falls kaum Gespraechstext sichtbar ist, sage knapp, was sichtbar ist."
                )
                summary = agent.run_turn_with_rag(prompt, use_rag=True, store_response=False)
                print(f"\nZusammenfassung:\n{summary}\n")
                print(f"\nAI: {send_text_to_discord(multimodal, summary)}\n")
                continue

            if multimodal and is_external_write_request(user_input):
                print(f"\nAI: {maybe_send_to_discord(multimodal, user_input)}\n")
                continue

            if is_external_write_request(user_input):
                print(f"\nAI: {answer_external_write_request(user_input)}\n")
                continue

            if is_professional_code_review_request(user_input):
                print(f"\nAI:\n{professional_code_review(code_watcher, sandbox_dir)}\n")
                continue

            # === Special Commands ===

            if user_input.lower() == "/help":
                print("""
Available Commands:
  /screenshot          Take screenshot + analyze
  /context             Show visual context
  /assist              Draft answer from current screen context
  /discord_summary     Summarize visible chat and optionally send to Discord
  /audio_devices       List microphone/loopback input devices
  /audio_test <id>     Check whether an audio device has signal
  /audio_scan          Test all input devices for open/signal
  /audio_setup         Let the agent pick and save a default audio device
  /listen_start [id]   Start local audio transcription
  /listen_live [id]    Start local audio transcription with live output
  /listen_default      Listen live using saved default audio device
  /listen_all          Auto-listen on likely PC/Discord audio devices
  /listen_stop         Stop audio transcription
  /listen_stop_summary Stop audio and print summary
  /transcript          Show current audio transcript
  /audio_status        Show audio listener status
  /audio_summary       Summarize transcript and optionally send to Discord
  /avatar_start        Open small local avatar/status window
  /avatar_stop         Close avatar window
  /vision_screen       Analyze current screenshot with vision model
  /comfy_status        Check local ComfyUI status
  /image_request       Save local image generation request
  /video_request       Save local video generation request
  /research_start      Start persistent research project
  /research_status     Show active research status
  /research_next       Run next guarded research step
  /research_auto       Run multiple guarded research steps
  /research_model      Show current research model config
  /research_model_set  Set proof-step model
  /research_model_test Test current proof-step model
  /research_model_benchmark Benchmark local research models
  /research_fast_mode  Use short prompts and fast model
  /research_deep_mode  Use stronger model with runtime warning
  /research_deep_once  Use deep model once for next step
  /research_literature Retrieve curated/web literature sources
  /research_verify_claims Verify claims against source registry
  /research_run_experiment Run latest research experiment script
  /research_web_on/off Toggle research web retrieval at runtime
  /research_web_status Show safe web proxy status
  /research_web_allowlist Show research domain allowlist
  /research_web_add_domain <domain> Add allowed research domain
  /research_web_remove_domain <domain> Remove allowed research domain
  /research_web_search <query> Search safe research sources
  /research_web_sources Show web-added sources
  /research_web_audit Show web access audit
  /research_clean_noise Remove invalid-domain gaps from status/checkpoint
  /research_pause      Pause research and save status
  /research_resume     Resume active research project
  /research_stop       Stop active research without deleting workspace
  /research_table      Show ranked approach table
  /research_open_latex Open main.tex in the default editor
  /research_show_latex Show full main.tex
  /research_tail_latex Show tail of main.tex
  /research_render_pdf Render main.tex if pdflatex exists
  /research_add_idea   Add a new unverified approach
  /research_mark_failed Mark an approach failed without deleting it
  /research_rank       Change approach rank with reason
  /research_sources    Show source registry
/research_focus A002
/research_run_experiment A002
/research_tail_latex  /research_lemmas     Show FormalLemma registry
  /research_analyze_lemma <id> Analyze one FormalLemma
  /research_refine_lemma <id> Refine a FormalLemma
  /research_verify_lemma <id> Compile its stored Lean 4 artifact
  /research_formalize_lemma <id> Generate, repair and compile Lean 4
  /research_novelty <id> Compare lemma against stored literature
  /research_peer_review <id> Run two independent reviewer roles
  /research_full_cycle <id> Run formalization, novelty, review and claim audit
  /research_pdf "path.pdf" Ingest a local PDF with page citations
  /research_source_trust S001 <level> Set reviewed source trust
  /research_mathlib_setup Initialize Mathlib workspace
  /research_mathlib_update Download/update Mathlib dependencies
  /research_replicate L001 Generate and compile an independent proof
  /research_export_report Export Markdown and JSON research report
  /research_quick_review Read current files, summarize weaknesses, write review
  /research_quality_audit Recheck stored lemmas and sources with hard filters
  /research_background_start <steps> [minutes] Start checkpointed background research
  /research_background_stop Stop background research
  /research_background_resume Resume from last checkpoint
  /research_background_status Show background state
  /research_validate_protocol "protocol.json" Validate experiment design
  /research_live_start [port] Start local live dashboard
  /research_live_status Show live dashboard status
  /research_live_stop Stop live dashboard
  /research_disprove_lemma <id> Search counterarguments for a FormalLemma
  /research_compare_lemma <id> "criterion" Compare lemma with known criterion
  /research_lemma_quality Analyze all FormalLemmas
  /research_focus <id> Lock auto-run to one approach
  /research_unfocus    Clear approach focus lock
  /research_current_focus Show active focus lock
  /research_autopilot_start <n> Run autonomous research controller
  /research_autopilot_stop Stop autonomous controller
  /research_autopilot_status Show controller state
  /research_autopilot_plan Show next planned action
  /research_autopilot_next Execute one controller decision
  /research_autopilot_report Show controller report
  /research_trace      Show research trace tail
  /research_checkpoint Show checkpoint.json
  /research_export     Export active research workspace as zip
  /research_autosave_on/off Toggle research autosave flag
  /code_watch_on       Enable proactive read-only code feedback
  /code_watch_off      Disable proactive code feedback
  /code_scan           Scan workspace once for code issues
  /scope               Show current screen/code observation scope
  /scope_screen <mode> Set screen scope: off|active|vs_code|unity|browser|discord|all
  /scope_project <dir> Set read-only custom code project path
  /scope_code <mode>   Set code scope: disabled|agent_workspace|custom_project
  /windows             List visible open windows/categories
  /meeting_summary     Summarize current meeting/screen text
  /suggestions <topic> Get suggestions from history
  /agents              Show specialist agents and models
  /resources           Show CPU/RAM/GPU pressure used for routing
  /interpret <text>    Show normalized meaning, intent and confidence
  /trace               Show last structured turn trace
  /feedback_yes        Confirm last input interpretation
  /feedback_no [fix]   Reject/correct last input interpretation
  /user_model          Show personalized user model summary
  /audit               Show recent audit events
  /learning            Show personal learning profile status
  /learn typo=correct  Add a personal typo correction
  /stats               Show RAG statistics
  /log_decision        Log current decision
  /auto <steps> <task> Auto mode
  /exit                Quit
""")
                continue

            if user_input.lower() == "/screenshot":
                if multimodal:
                    if not screen_context_allowed(multimodal, sandbox_dir):
                        print("\nScreenshot blockiert: Der aktuelle Screen-Scope erlaubt dieses Fenster nicht.\n")
                        continue
                    result = multimodal.take_screenshot()
                    if result.get("ok"):
                        print(f"📸 Analyzed: {result.get('window')}")
                    else:
                        print(f"❌ {result.get('error')}")
                continue

            if user_input.lower() == "/context":
                if multimodal:
                    print(f"\n📊 {filtered_context_string(multimodal, sandbox_dir)}\n")
                continue

            if user_input.lower() == "/scope":
                print(f"\n{scope_status(multimodal, code_watcher, sandbox_dir)}\n")
                continue

            if user_input.lower() == "/windows":
                if not multimodal:
                    print("\nWindow tracker is not available.\n")
                    continue
                windows = multimodal.window_tracker.list_open_windows()
                if not windows:
                    print("\nKeine offenen Fenster erkannt.\n")
                    continue
                print("\nOffene sichtbare Fenster:")
                for item in windows[:80]:
                    print(f"  [{item['category']}] {item['title']}")
                if len(windows) > 80:
                    print(f"  ... {len(windows) - 80} weitere")
                print()
                continue

            if user_input.lower().startswith("/scope_screen"):
                parts = user_input.split(maxsplit=1)
                if len(parts) < 2 or parts[1].strip() not in {"off", "active", "vs_code", "unity", "browser", "discord", "all"}:
                    print("\nUsage: /scope_screen off|active|vs_code|unity|browser|discord|all\n")
                    continue
                permissions = load_avatar_permissions(sandbox_dir)
                permissions["screen_context"] = parts[1].strip() != "off"
                permissions["screen_scope"] = parts[1].strip()
                (sandbox_dir / "avatar_permissions.json").write_text(
                    json.dumps(permissions, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                print(f"\nScreen-Scope gespeichert: {parts[1].strip()}\n")
                continue

            if user_input.lower().startswith("/scope_code"):
                parts = user_input.split(maxsplit=1)
                if len(parts) < 2 or parts[1].strip() not in {"disabled", "agent_workspace", "custom_project"}:
                    print("\nUsage: /scope_code disabled|agent_workspace|custom_project\n")
                    continue
                permissions = load_avatar_permissions(sandbox_dir)
                permissions["code_scope"] = parts[1].strip()
                (sandbox_dir / "avatar_permissions.json").write_text(
                    json.dumps(permissions, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                print(f"\n{apply_code_scope(code_watcher, sandbox_dir)}\n")
                continue

            if user_input.lower().startswith("/scope_project"):
                parts = user_input.split(maxsplit=1)
                if len(parts) < 2:
                    print("\nUsage: /scope_project <ordnerpfad>\n")
                    continue
                project = Path(parts[1].strip().strip('"')).expanduser()
                if not project.exists() or not project.is_dir():
                    print(f"\nProjektpfad nicht gefunden: {project}\n")
                    continue
                permissions = load_avatar_permissions(sandbox_dir)
                permissions["code_scope"] = "custom_project"
                permissions["code_project_path"] = str(project.resolve())
                (sandbox_dir / "avatar_permissions.json").write_text(
                    json.dumps(permissions, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                print(f"\n{apply_code_scope(code_watcher, sandbox_dir)}\n")
                continue

            if user_input.lower() == "/audio_devices":
                result = audio_listener.list_devices()
                if not result.get("ok"):
                    print(f"\nAudio not ready: {result.get('error')}")
                    print("Install: .\\.venv_personal_agent\\Scripts\\python.exe -m pip install sounddevice numpy faster-whisper\n")
                    continue
                print("\nAudio input devices:")
                for dev in result.get("devices", []):
                    print(f"  {dev['index']}: {dev['name']} ({dev['inputs']} input channels)")
                print()
                continue

            if user_input.lower().startswith("/audio_test"):
                parts = user_input.split()
                if len(parts) < 2:
                    print("Usage: /audio_test <device_id>")
                    continue
                try:
                    device = int(parts[1])
                except ValueError:
                    print("Usage: /audio_test <device_id>")
                    continue
                print(f"\nTesting audio device {device} for 3 seconds. Play YouTube/Discord audio now...")
                result = audio_listener.measure_level(device=device, seconds=3.0)
                if not result.get("ok"):
                    print(f"Audio test failed: {result.get('error')}\n")
                else:
                    print(
                        f"Audio level device {device}: "
                        f"rms={result['rms']:.5f}, peak={result['peak']:.5f}, "
                        f"signal={'YES' if result['has_signal'] else 'NO'}\n"
                    )
                continue

            if user_input.lower() == "/audio_scan":
                result = audio_listener.list_devices()
                if not result.get("ok"):
                    print(f"\nAudio not ready: {result.get('error')}\n")
                    continue
                print("\nScanning audio devices. Spiele jetzt kurz YouTube/Discord-Audio ab...")
                for dev in result.get("devices", []):
                    idx = dev["index"]
                    level = audio_listener.measure_level(device=idx, seconds=0.7)
                    if not level.get("ok"):
                        print(f"  {idx}: {dev['name']} -> cannot open ({level.get('error')})")
                    else:
                        signal = "YES" if level["has_signal"] else "NO"
                        print(f"  {idx}: {dev['name']} -> signal={signal} peak={level['peak']:.4f}")
                print()
                continue

            if user_input.lower() == "/audio_setup":
                run_audio_setup(audio_listener, sandbox_dir)
                continue

            if user_input.lower().startswith("/listen_start"):
                parts = user_input.split()
                device = None
                if len(parts) > 1:
                    try:
                        device = int(parts[1])
                    except ValueError:
                        print("Usage: /listen_start [device_id]")
                        continue
                result = audio_listener.start(device=device)
                if not result.get("ok"):
                    print(f"\nAudio not ready: {result.get('error')}")
                    print(f"Missing: {', '.join(result.get('missing', []))}")
                    print("Install: .\\.venv_personal_agent\\Scripts\\python.exe -m pip install sounddevice numpy faster-whisper\n")
                else:
                    print("\nAudio listener started. Use /listen_stop to stop.\n")
                continue

            if user_input.lower().startswith("/listen_live"):
                parts = user_input.split()
                device = None
                if len(parts) > 1:
                    try:
                        device = int(parts[1])
                    except ValueError:
                        print("Usage: /listen_live [device_id]")
                        continue
                if audio_listener.is_running:
                    audio_listener.stop()
                result = audio_listener.start(device=device, live_print=True)
                if not result.get("ok"):
                    print(f"\nAudio not ready: {result.get('error')}")
                    print(f"Missing: {', '.join(result.get('missing', []))}")
                    print("Install: .\\.venv_personal_agent\\Scripts\\python.exe -m pip install sounddevice numpy faster-whisper\n")
                else:
                    print("\nLive audio listener started. Use /listen_stop_summary to stop and summarize.\n")
                    print(f"Temp notes: {audio_listener.session_dir}\n")
                continue

            if user_input.lower() == "/listen_default":
                config = load_audio_config(sandbox_dir)
                device = config.get("default_device")
                if device is None:
                    print("\nKein Default-Audiogeraet gespeichert. Starte zuerst /audio_setup.\n")
                    continue
                if audio_listener.is_running:
                    audio_listener.stop()
                result = audio_listener.start(device=int(device), live_print=True)
                if not result.get("ok"):
                    print(f"\nAudio not ready: {result.get('error')}")
                    print(f"Missing: {', '.join(result.get('missing', []))}\n")
                else:
                    print(f"\nLive-Mithoeren gestartet mit Default-Geraet {device} ({config.get('default_name', '')}).")
                    print(f"Temp notes: {audio_listener.session_dir}")
                    print("Nutze /listen_stop_summary fuer Stop + Zusammenfassung.\n")
                continue

            if user_input.lower() == "/listen_all":
                result = multi_audio_listener.start(live_print=True)
                if not result.get("ok"):
                    print(f"\nAudio not ready: {result.get('error')}")
                    print(f"Missing: {', '.join(result.get('missing', []))}")
                    print("Install: .\\.venv_personal_agent\\Scripts\\python.exe -m pip install sounddevice numpy faster-whisper\n")
                else:
                    print(f"\nLive multi-audio listener started on devices: {result.get('started')}")
                    print(f"Temp notes: {multi_audio_listener.session_path()}")
                    print("Use /listen_stop_summary to stop and summarize.\n")
                continue

            if user_input.lower() == "/listen_stop":
                result = audio_listener.stop()
                multi = multi_audio_listener.stop()
                total = int(result.get("transcripts", 0)) + int(multi.get("transcripts", 0))
                print(f"\nAudio listener stopped ({total} transcript chunks)\n")
                continue

            if user_input.lower() == "/listen_stop_summary":
                result = audio_listener.stop()
                multi = multi_audio_listener.stop()
                transcript = "\n".join(
                    part for part in [
                        audio_listener.get_transcript_text(),
                        multi_audio_listener.get_transcript_text(),
                    ]
                    if part.strip()
                )
                total = int(result.get("transcripts", 0)) + int(multi.get("transcripts", 0))
                print(f"\nAudio listener stopped ({total} transcript chunks)\n")
                if not transcript.strip():
                    print("No transcript available yet.\n")
                    continue
                summary = build_audio_summary(agent, transcript)
                print(f"\nZusammenfassung:\n{summary}\n")
                avatar.log(f"Audio-Zusammenfassung: {summary}")
                audio_listener.clear()
                multi_audio_listener.cleanup_temp_files()
                print("Temporaere Audio-Notizen wurden geleert.\n")
                continue

            if user_input.lower() == "/transcript":
                text = "\n".join(
                    part for part in [
                        audio_listener.get_transcript_text(),
                        multi_audio_listener.get_transcript_text(),
                    ]
                    if part.strip()
                )
                print(f"\nTranscript:\n{text if text else '(empty)'}\n")
                continue

            if user_input.lower() == "/audio_status":
                single = audio_listener.status()
                multi_running = multi_audio_listener.is_running()
                print("\nAudio status:")
                print(f"  single running: {single.get('running')} device={single.get('device')} chunks={single.get('transcripts')}")
                print(f"  multi running: {multi_running}")
                if single.get("last_error"):
                    print(f"  last error: {single.get('last_error')}")
                print()
                continue

            if user_input.lower() == "/avatar_start":
                avatar.start()
                avatar.log("Avatar gestartet. Du kannst hier spaeter schreiben/sprechen/zeigen.")
                if multimodal:
                    avatar.set_context(filtered_context_string(multimodal, sandbox_dir))
                print("\nAvatar-Fenster gestartet.\n")
                continue

            if user_input.lower() == "/avatar_stop":
                avatar.stop()
                print("\nAvatar-Fenster geschlossen.\n")
                continue

            if user_input.lower() == "/vision_screen":
                if not multimodal:
                    print("Screen context is not available.")
                    continue
                if not screen_context_allowed(multimodal, sandbox_dir):
                    print("\nVision blockiert: Der aktuelle Screen-Scope erlaubt dieses Fenster nicht.\n")
                    continue
                latest = multimodal.screenshot_monitor.get_latest_screenshot()
                if not latest:
                    result = multimodal.take_screenshot()
                    latest = multimodal.screenshot_monitor.get_latest_screenshot()
                if not latest:
                    print("No screenshot available.")
                    continue
                img, _meta = latest
                prompt = (
                    "Analysiere diesen Screenshot professionell auf Deutsch. "
                    "Beschreibe sichtbare App, relevante Inhalte, Fehler/Risiken, "
                    "und konkrete hilfreiche Hinweise. Behaupte nichts, was nicht sichtbar ist."
                )
                result = vision.analyze_image(img, prompt)
                if result.get("ok"):
                    print(f"\nVision ({result.get('model')}):\n{result.get('text')}\n")
                    avatar.log(f"Vision: {result.get('text')[:1000]}")
                else:
                    print(f"\nVision failed ({result.get('model')}): {result.get('error')}\n")
                continue

            if user_input.lower() == "/comfy_status":
                result = comfyui.health_check()
                if result.get("ok"):
                    print("\nComfyUI reachable on 127.0.0.1:8188\n")
                else:
                    print(f"\nComfyUI not reachable: {result.get('error')}\n")
                continue

            if user_input.lower().startswith("/image_request"):
                prompt = user_input[len("/image_request"):].strip()
                if not prompt:
                    print("Usage: /image_request <prompt>")
                    continue
                result = comfyui.save_prompt_request(prompt)
                print(f"\nImage generation request saved: {result.get('file')}\n")
                continue

            if user_input.lower().startswith("/video_request"):
                prompt = user_input[len("/video_request"):].strip()
                if not prompt:
                    print("Usage: /video_request <prompt>")
                    continue
                result = video_gen.save_request(prompt)
                print(f"\nVideo generation request saved: {result.get('file')}\n")
                continue

            if user_input.lower().startswith("/research_start"):
                args = parse_research_args(user_input)
                problem = " ".join(args[1:]).strip() if len(args) > 1 else ""
                if not problem:
                    print('Usage: /research_start "Problem Name"\n')
                    continue
                try:
                    print(f"\n{research.start(problem)}\n")
                except Exception as e:
                    print(f"\nResearch start failed: {e}\n")
                continue

            if user_input.lower() == "/research_status":
                try:
                    print(f"\n{research.status()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_next":
                try:
                    print(f"\n{research.next_step()}\n")
                except Exception as e:
                    print(f"\nResearch step failed: {e}\n")
                continue

            if user_input.lower().startswith("/research_autopilot_start"):
                args = parse_research_args(user_input)
                if len(args) < 2:
                    print("Usage: /research_autopilot_start <max_steps>\n")
                    continue
                try:
                    print(f"\n{research.autopilot_start(int(args[1]))}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_autopilot_stop":
                try:
                    print(f"\n{research.autopilot_stop()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_autopilot_status":
                try:
                    print(f"\n{research.autopilot_status()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_autopilot_plan":
                try:
                    print(f"\n{research.autopilot_plan()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_autopilot_next":
                try:
                    print(f"\n{research.autopilot_next()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_autopilot_report":
                try:
                    print(f"\n{research.autopilot_report()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if is_research_auto_command(user_input):
                args = parse_research_args(user_input)
                if len(args) < 2:
                    print("Usage: /research_auto <n_steps>\n")
                    continue
                try:
                    print(f"\n{research.auto(int(args[1]))}\n")
                except Exception as e:
                    print(f"\nResearch auto failed: {e}\n")
                continue

            if user_input.lower() == "/research_model":
                print(f"\n{research.model_status()}\n")
                continue

            if user_input.lower().startswith("/research_model_set"):
                args = parse_research_args(user_input)
                if len(args) < 2:
                    print("Usage: /research_model_set <model>\n")
                    continue
                print(f"\n{research.set_research_model(args[1])}\n")
                continue

            if user_input.lower() == "/research_model_test":
                print(f"\n{research.model_test()}\n")
                continue

            if user_input.lower() == "/research_model_benchmark":
                print(f"\n{research.model_benchmark()}\n")
                continue

            if user_input.lower() == "/research_fast_mode":
                print(f"\n{research.fast_mode()}\n")
                continue

            if user_input.lower() == "/research_deep_mode":
                print(f"\n{research.deep_mode()}\n")
                continue

            if user_input.lower() == "/research_deep_once":
                print(f"\n{research.deep_once()}\n")
                continue

            if user_input.lower().startswith("/research_literature"):
                args = parse_research_args(user_input)
                query = " ".join(args[1:]).strip() if len(args) > 1 else None
                try:
                    print(f"\n{research.literature_retrieve(query)}\n")
                except Exception as e:
                    print(f"\nLiterature retrieval failed: {e}\n")
                continue

            if user_input.lower() == "/research_verify_claims":
                try:
                    print(f"\n{research.verify_claims()}\n")
                except Exception as e:
                    print(f"\nClaim verification failed: {e}\n")
                continue

            if user_input.lower().startswith("/research_run_experiment"):
                args = parse_research_args(user_input)
                approach_id = args[1] if len(args) > 1 else None
                try:
                    print(f"\n{research.run_experiment(approach_id)}\n")
                except Exception as e:
                    print(f"\nExperiment failed: {e}\n")
                continue

            if user_input.lower() == "/research_web_on":
                print(f"\n{research.set_web_enabled(True)}\n")
                continue

            if user_input.lower() == "/research_web_off":
                print(f"\n{research.set_web_enabled(False)}\n")
                continue

            if user_input.lower() == "/research_web_status":
                print(f"\n{research.web_status()}\n")
                continue

            if user_input.lower() == "/research_web_allowlist":
                print(f"\n{research.web_allowlist()}\n")
                continue

            if user_input.lower().startswith("/research_web_add_domain"):
                args = parse_research_args(user_input)
                if len(args) < 2:
                    print("Usage: /research_web_add_domain <domain>\n")
                    continue
                try:
                    print(f"\n{research.web_add_domain(args[1])}\n")
                except Exception as e:
                    print(f"\nDomain nicht erlaubt: {e}\n")
                continue

            if user_input.lower().startswith("/research_web_remove_domain"):
                args = parse_research_args(user_input)
                if len(args) < 2:
                    print("Usage: /research_web_remove_domain <domain>\n")
                    continue
                print(f"\n{research.web_remove_domain(args[1])}\n")
                continue

            if user_input.lower().startswith("/research_web_search"):
                args = parse_research_args(user_input)
                query = " ".join(args[1:]).strip()
                if not query:
                    print("Usage: /research_web_search <query>\n")
                    continue
                print(f"\n{research.web_search(query)}\n")
                continue

            if user_input.lower() == "/research_web_sources":
                print(f"\n{research.web_sources()}\n")
                continue

            if user_input.lower() == "/research_web_audit":
                print(f"\n{research.web_audit()}\n")
                continue

            if user_input.lower() == "/research_clean_noise":
                try:
                    print(f"\n{research.clean_noise()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_pause":
                try:
                    print(f"\n{research.pause()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_resume":
                print(f"\n{research.resume()}\n")
                continue

            if user_input.lower() == "/research_stop":
                print(f"\n{research.stop()}\n")
                continue

            if user_input.lower() == "/research_table":
                try:
                    print(f"\n{research.table()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_open_latex":
                try:
                    print(f"\n{research.open_latex()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_show_latex":
                try:
                    print(f"\n{research.show_latex()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_tail_latex":
                try:
                    print(f"\n{research.tail_latex()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_render_pdf":
                try:
                    print(f"\n{research.render_pdf()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower().startswith("/research_add_idea"):
                args = parse_research_args(user_input)
                idea = " ".join(args[1:]).strip() if len(args) > 1 else ""
                if not idea:
                    print('Usage: /research_add_idea "idea"\n')
                    continue
                try:
                    print(f"\n{research.add_idea(idea)}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower().startswith("/research_mark_failed"):
                args = parse_research_args(user_input)
                if len(args) < 3:
                    print('Usage: /research_mark_failed A001 "reason"\n')
                    continue
                try:
                    print(f"\n{research.mark_failed(args[1], ' '.join(args[2:]))}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower().startswith("/research_rank"):
                args = parse_research_args(user_input)
                if len(args) < 4:
                    print('Usage: /research_rank A002 3 "reason"\n')
                    continue
                try:
                    print(f"\n{research.rank(args[1], int(args[2]), ' '.join(args[3:]))}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_sources":
                try:
                    print(f"\n{research.sources()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_lemmas":
                try:
                    print(f"\n{research.lemmas()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower().startswith("/research_analyze_lemma"):
                args = parse_research_args(user_input)
                if len(args) < 2:
                    print("Usage: /research_analyze_lemma L001\n")
                    continue
                try:
                    print(f"\n{research.analyze_lemma(args[1])}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower().startswith("/research_refine_lemma"):
                args = parse_research_args(user_input)
                if len(args) < 2:
                    print("Usage: /research_refine_lemma L001\n")
                    continue
                try:
                    print(f"\n{research.refine_lemma(args[1])}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower().startswith("/research_verify_lemma"):
                args = parse_research_args(user_input)
                if len(args) < 2:
                    print("Usage: /research_verify_lemma L001\n")
                    continue
                try:
                    print(f"\n{research.verify_lemma_formally(args[1])}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower().startswith("/research_formalize_lemma"):
                args = parse_research_args(user_input)
                if len(args) < 2:
                    print("Usage: /research_formalize_lemma L001\n")
                    continue
                try:
                    print(f"\n{research.formalize_and_verify_lemma(args[1])}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower().startswith("/research_novelty"):
                args = parse_research_args(user_input)
                if len(args) < 2:
                    print("Usage: /research_novelty L001\n")
                    continue
                try:
                    print(f"\n{research.assess_lemma_novelty(args[1])}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower().startswith("/research_peer_review"):
                args = parse_research_args(user_input)
                if len(args) < 2:
                    print("Usage: /research_peer_review L001\n")
                    continue
                try:
                    print(f"\n{research.peer_review_lemma(args[1])}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower().startswith("/research_full_cycle"):
                args = parse_research_args(user_input)
                if len(args) < 2:
                    print("Usage: /research_full_cycle L001\n")
                    continue
                try:
                    print(f"\n{research.full_research_cycle(args[1])}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower().startswith("/research_pdf"):
                args = parse_research_args(user_input)
                if len(args) < 2:
                    print('Usage: /research_pdf "C:\\path\\paper.pdf"\n')
                    continue
                try:
                    print(f"\n{research.ingest_pdf(args[1])}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower().startswith("/research_source_trust"):
                args = parse_research_args(user_input)
                if len(args) < 3:
                    print("Usage: /research_source_trust S001 trusted_reference\n")
                    continue
                try:
                    print(f"\n{research.set_source_trust(args[1], args[2])}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_mathlib_setup":
                try:
                    print(f"\n{research.setup_mathlib(False)}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_mathlib_update":
                try:
                    print(f"\n{research.setup_mathlib(True)}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower().startswith("/research_replicate"):
                args = parse_research_args(user_input)
                if len(args) < 2:
                    print("Usage: /research_replicate L001\n")
                    continue
                try:
                    print(f"\n{research.replicate_formal_proof(args[1])}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_export_report":
                try:
                    print(f"\n{research.export_research_report()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_quick_review":
                try:
                    print(f"\n{research.quick_review(apply_improvements=True)}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_quality_audit":
                try:
                    print(f"\n{research.quality_audit()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower().startswith("/research_background_start"):
                args = parse_research_args(user_input)
                if len(args) < 2:
                    print("Usage: /research_background_start <steps> [minutes]\n")
                    continue
                try:
                    minutes = int(args[2]) if len(args) > 2 else 60
                    print(f"\n{research.background_research_start(int(args[1]), max_minutes=minutes)}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_background_stop":
                print(f"\n{research.background_research_stop()}\n")
                continue

            if user_input.lower() == "/research_background_resume":
                print(f"\n{research.background_research_resume()}\n")
                continue

            if user_input.lower() == "/research_background_status":
                print(f"\n{research.background_research_status()}\n")
                continue

            if user_input.lower().startswith("/research_validate_protocol"):
                args = parse_research_args(user_input)
                if len(args) < 2:
                    print('Usage: /research_validate_protocol "protocol.json"\n')
                    continue
                try:
                    print(f"\n{research.validate_experiment_protocol_file(args[1])}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower().startswith("/research_live_start"):
                args = parse_research_args(user_input)
                try:
                    port = int(args[1]) if len(args) > 1 else 8766
                    print(f"\n{research.live_start(port)}\nÖffne diese Adresse im Browser.\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_live_status":
                print(f"\n{research.live_status()}\n")
                continue

            if user_input.lower() == "/research_live_stop":
                print(f"\n{research.live_stop()}\n")
                continue

            if user_input.lower().startswith("/research_disprove_lemma"):
                args = parse_research_args(user_input)
                if len(args) < 2:
                    print("Usage: /research_disprove_lemma L001\n")
                    continue
                try:
                    print(f"\n{research.disprove_lemma(args[1])}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower().startswith("/research_compare_lemma"):
                args = parse_research_args(user_input)
                if len(args) < 3:
                    print('Usage: /research_compare_lemma L001 "Li criterion"\n')
                    continue
                try:
                    print(f"\n{research.compare_lemma(args[1], ' '.join(args[2:]))}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_lemma_quality":
                try:
                    print(f"\n{research.lemma_quality()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower().startswith("/research_focus"):
                args = parse_research_args(user_input)
                if len(args) < 2:
                    print("Usage: /research_focus A003\n")
                    continue
                try:
                    print(f"\n{research.focus(args[1])}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_unfocus":
                try:
                    print(f"\n{research.unfocus()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_current_focus":
                try:
                    print(f"\n{research.current_focus()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_trace":
                try:
                    print(f"\n{research.trace()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_checkpoint":
                try:
                    print(f"\n{research.checkpoint()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_export":
                try:
                    print(f"\n{research.export()}\n")
                except Exception as e:
                    print(f"\n{e}\n")
                continue

            if user_input.lower() == "/research_autosave_on":
                print(f"\n{research.autosave_on()}\n")
                continue

            if user_input.lower() == "/research_autosave_off":
                print(f"\n{research.autosave_off()}\n")
                continue

            if user_input.lower().startswith("/research_"):
                print("\nUnbekannter Research-Befehl. Nutze /help fuer die verfuegbaren /research_* Commands.\n")
                continue

            if is_internal_autopilot_action(user_input):
                print("\nDas ist eine interne Autopilot-Aktion. Nutze /research_autopilot_next oder /research_autopilot_start.\n")
                continue

            if user_input.lower() == "/code_watch_on":
                scope_msg = apply_code_scope(code_watcher, sandbox_dir)
                if load_avatar_permissions(sandbox_dir).get("code_scope") == "disabled":
                    print(f"\n{scope_msg}\n")
                    continue
                code_watcher.start()
                print(f"\nRead-only Code-Watcher ist aktiv. {scope_msg}\n")
                continue

            if user_input.lower() == "/code_watch_off":
                code_watcher.stop()
                print("\nRead-only Code-Watcher ist pausiert.\n")
                continue

            if user_input.lower() == "/code_scan":
                scope_msg = apply_code_scope(code_watcher, sandbox_dir)
                if load_avatar_permissions(sandbox_dir).get("code_scope") == "disabled":
                    print(f"\n{scope_msg}\n")
                    continue
                findings = code_watcher.scan_full_once()
                if not findings:
                    print(f"\nKeine neuen Code-Probleme gefunden. {scope_msg}\n")
                else:
                    print(f"\n{len(findings)} Finding(s) gefunden. {scope_msg}")
                    for finding in findings[:30]:
                        print(f"  {finding.severity.upper()}: {finding.file}:{finding.line} - {finding.message}")
                    if len(findings) > 30:
                        print(f"  ... {len(findings) - 30} weitere")
                    print()
                continue

            if user_input.lower() == "/audio_summary":
                transcript = "\n".join(
                    part for part in [
                        audio_listener.get_transcript_text(),
                        multi_audio_listener.get_transcript_text(),
                    ]
                    if part.strip()
                )
                if not transcript.strip():
                    print("\nAI: Noch kein Audio-Transkript vorhanden. Starte zuerst /listen_start.\n")
                    continue
                summary = build_audio_summary(agent, transcript)
                print(f"\nAudio-Zusammenfassung:\n{summary}\n")
                avatar.log(f"Audio-Zusammenfassung: {summary}")
                if multimodal:
                    print(f"\nAI: {send_text_to_discord(multimodal, summary)}\n")
                audio_listener.clear()
                multi_audio_listener.cleanup_temp_files()
                print("Temporaere Audio-Notizen wurden geleert.\n")
                continue

            if user_input.lower() == "/assist":
                if not multimodal:
                    print("Screen context is not available.")
                    continue
                ctx = filtered_context_string(multimodal, sandbox_dir)
                if not ctx.strip():
                    print("No screen context available yet.")
                    continue
                prompt = (
                    "[SCREEN CONTEXT]\n"
                    f"{ctx}\n\n"
                    "[TASK]\n"
                    "If a question or request is visible in Discord, Zoom, a browser, "
                    "or the IDE, draft the best concise answer for the user to copy. "
                    "Do not claim you sent it."
                )
                response = agent.run_turn_with_rag(prompt, use_rag=True)
                print(f"\nDraft:\n{response}\n")
                continue

            if user_input.lower() == "/discord_summary":
                if not multimodal:
                    print("Screen context is not available.")
                    continue
                ctx = filtered_context_string(multimodal, sandbox_dir)
                prompt = (
                    "[SCREEN CONTEXT]\n"
                    f"{ctx}\n\n"
                    "[TASK]\n"
                    "Fasse den sichtbar erkannten Discord-/Chat-Kontext kurz auf Deutsch zusammen. "
                    "Schreibe nur die Zusammenfassung, keine Meta-Erklaerung."
                )
                summary = agent.run_turn_with_rag(prompt, use_rag=True, store_response=False)
                print(f"\nZusammenfassung:\n{summary}\n")
                print(f"\nAI: {send_text_to_discord(multimodal, summary)}\n")
                continue

            if user_input.lower() == "/meeting_summary":
                if not multimodal:
                    print("Screen context is not available.")
                    continue
                if not memory.ask_yes_no("Summarize the currently visible meeting/screen text?"):
                    continue
                ctx = filtered_context_string(multimodal, sandbox_dir)
                prompt = (
                    "[SCREEN CONTEXT]\n"
                    f"{ctx}\n\n"
                    "[TASK]\n"
                    "Create a structured meeting summary with decisions, open questions, "
                    "action items, and risks. Use only visible/transcribed text."
                )
                response = agent.run_turn_with_rag(prompt, use_rag=True)
                print(f"\nMeeting summary:\n{response}\n")
                continue

            if user_input.lower().startswith("/suggestions"):
                parts = user_input.split(maxsplit=1)
                topic = parts[1] if len(parts) > 1 else "help"
                agent.show_suggestions(topic)
                continue

            if user_input.lower() == "/agents":
                print("\nSpecialist agents:")
                for specialist in agent.worker_router.registry.list_agents():
                    tools = ", ".join(specialist.tools) if specialist.tools else "none"
                    print(f"  {specialist.name}: model={specialist.model}, tools={tools}")
                    print(f"    {specialist.purpose}")
                print()
                continue

            if user_input.lower() == "/resources":
                snap = agent.system_monitor.snapshot()
                print("\nResources:")
                print(f"  CPU: {snap.cpu_percent}")
                print(f"  RAM: {snap.ram_percent}")
                print(f"  GPU: {snap.gpu_percent}")
                print(f"  VRAM: {snap.vram_percent}")
                print(f"  pressure: {snap.pressure}\n")
                continue

            if user_input.lower().startswith("/interpret"):
                text = user_input[len("/interpret"):].strip()
                if not text:
                    print("\nUsage: /interpret <text>\n")
                    continue
                item = agent.interpret_text(text)
                print("\nInterpretation:")
                print(json.dumps(item.to_dict(), indent=2, ensure_ascii=False))
                print()
                continue

            if user_input.lower() == "/trace":
                trace = agent.turn_pipeline.latest_trace_dict()
                if not trace:
                    print("\nNoch kein Turn-Trace vorhanden.\n")
                else:
                    print("\nLast Turn Trace:")
                    print(json.dumps(trace, indent=2, ensure_ascii=False))
                    print()
                continue

            if user_input.lower() in {"/feedback_yes", "/ja_genau", "ja genau"}:
                print(f"\n{agent.confirm_last_interpretation()}\n")
                continue

            if user_input.lower().startswith("/feedback_no") or user_input.lower().startswith("nein ich meine"):
                if user_input.lower().startswith("/feedback_no"):
                    correction = user_input[len("/feedback_no"):].strip()
                else:
                    correction = user_input.strip()
                print(f"\n{agent.reject_last_interpretation(correction)}\n")
                continue

            if user_input.lower() == "/user_model":
                print(f"\n{agent.user_model.summary()}\n")
                continue

            if user_input.lower() == "/audit":
                events = agent.audit.tail(limit=30)
                print("\nAudit events:")
                for event in events:
                    print(json.dumps(event, ensure_ascii=False)[:1000])
                print()
                continue

            if user_input.lower() == "/learning":
                print(f"\n{agent.learning.summary()}\n")
                continue

            if user_input.lower().startswith("/learn "):
                payload = user_input[7:].strip()
                if "=" not in payload:
                    print("Usage: /learn typo=correct")
                    continue
                wrong, correct = payload.split("=", 1)
                agent.learning.add_correction(wrong, correct)
                print(f"Learned correction: {wrong.strip()} -> {correct.strip()}\n")
                continue

            if user_input.lower() == "/stats":
                agent.show_rag_stats()
                continue

            if user_input.lower() == "/log_decision":
                agent.log_decision_interactive()
                continue

            if user_input.lower().startswith("/auto"):
                parts = user_input.split(maxsplit=2)
                max_steps = 10
                task = ""

                try:
                    if len(parts) >= 2:
                        max_steps = int(parts[1])
                    if len(parts) >= 3:
                        task = parts[2]
                except ValueError:
                    pass

                if not task:
                    print("Usage: /auto <max_steps> <task>\n")
                    continue

                # Add visual context
                if multimodal and screen_context_allowed(multimodal, sandbox_dir):
                    ctx = filtered_context_string(multimodal, sandbox_dir)
                    task = f"[VISUAL CONTEXT]\n{ctx}\n\n[TASK]\n{task}"

                response = agent.run_turn_with_rag(task, auto_mode=True, use_rag=True)
                print(f"\nAI: {response}\n")
                continue

            # Normal mode with RAG
            if multimodal and screen_context_allowed(multimodal, sandbox_dir):
                ctx = filtered_context_string(multimodal, sandbox_dir)
                if ctx.strip():
                    user_input = f"[VISUAL CONTEXT]\n{ctx}\n\n[USER]\n{user_input}"

            response = agent.run_turn_with_rag(user_input, use_rag=True)
            print(f"\nAI: {response}\n")

    except KeyboardInterrupt:
        print("\nInterrupted")
    
    finally:
        if multimodal:
            multimodal.stop_monitoring()
        audio_listener.stop()
        multi_audio_listener.stop()
        avatar.stop()
        code_watcher.stop()


if __name__ == "__main__":
    main()
