"""
Local desktop dashboard/avatar for the agent.

The window is deliberately local-only. It gives the agent a visible presence,
chat input, thinking/status feedback, screen context preview and persistent
trust settings without granting unsafe permissions by itself.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path
from typing import Any, Optional


DEFAULT_PERMISSIONS = {
    "screen_context": True,
    "screen_scope": "active",
    "code_scope": "agent_workspace",
    "code_project_path": "",
    "audio_listen_after_signal": True,
    "auto_memory": False,
    "discord_send_after_approval": True,
    "code_repair_after_approval": True,
    "web_access": False,
    "external_app_control": False,
    "deep_thinking_auto": False,
    "debug_observability": False,
    "creativity": 35,
    "detail_level": 55,
    "initiative": 45,
}


class AvatarWindow:
    """Tkinter-based dashboard window running in a background thread."""

    def __init__(self, agent: Any = None, sandbox_dir: Optional[Path] = None):
        self.agent = agent
        self.sandbox_dir = Path(sandbox_dir or "./agent_sandbox")
        self.permissions_path = self.sandbox_dir / "avatar_permissions.json"
        self._queue: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._chat_lock = threading.Lock()
        self.permissions = self._load_permissions()

    def start(self) -> bool:
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False
        self._queue.put(("stop", ""))

    def log(self, text: str) -> None:
        self._queue.put(("log", text))

    def set_status(self, text: str) -> None:
        self._queue.put(("status", text))

    def set_context(self, text: str) -> None:
        self._queue.put(("context", text))

    def set_agent(self, agent: Any) -> None:
        self.agent = agent

    def _load_permissions(self) -> dict:
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        if not self.permissions_path.exists():
            return dict(DEFAULT_PERMISSIONS)
        try:
            loaded = json.loads(self.permissions_path.read_text(encoding="utf-8"))
            merged = dict(DEFAULT_PERMISSIONS)
            merged.update({k: loaded.get(k, v) for k, v in DEFAULT_PERMISSIONS.items()})
            return merged
        except Exception:
            return dict(DEFAULT_PERMISSIONS)

    def _save_permissions(self) -> None:
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        self.permissions_path.write_text(
            json.dumps(self.permissions, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _chat_direct(self, user_text: str) -> str:
        if not self.agent:
            return "Avatar-Chat ist noch nicht mit dem Agenten verbunden."

        with self._chat_lock:
            previous_model = getattr(self.agent.ollama, "model", None)
            previous_tools = getattr(self.agent.ollama, "enable_tools", True)
            try:
                worker = self.agent.worker_router.route(user_text)
                if worker.name in {"deep_reasoning", "chief_reasoning"}:
                    chief = self.agent.worker_router.registry.get("chief_reasoning")
                    if chief:
                        worker = chief

                system_prompt = self.agent.memory.build_system_prompt()
                system_prompt += (
                    "\n\nAVATAR DASHBOARD MODE:\n"
                    "- Answer in German unless the user asks otherwise.\n"
                    "- Do not execute tools from this GUI chat.\n"
                    "- If a file/app/tool action is needed, tell the exact CLI command or ask the user to use the main CLI.\n"
                    "- Be concise for simple chat and deeper for planning/debugging.\n"
                )
                system_prompt += f"\nCURRENT AVATAR SETTINGS:\n{json.dumps(self.permissions, ensure_ascii=False)}"

                self.agent.ollama.set_model(worker.model)
                self.agent.ollama.set_tools_enabled(False)
                response, _tool = self.agent.ollama.chat_with_tools(
                    messages=[{"role": "user", "content": user_text}],
                    system=system_prompt,
                    max_retries=1,
                )
                return response or "(keine Antwort)"
            except Exception as exc:
                return f"Avatar-Chat fehlgeschlagen: {exc}"
            finally:
                if previous_model:
                    self.agent.ollama.set_model(previous_model)
                self.agent.ollama.set_tools_enabled(previous_tools)

    def _run(self) -> None:
        try:
            import tkinter as tk
            from tkinter import ttk
        except Exception:
            self._running = False
            return

        root = tk.Tk()
        root.title("Umut Agent Dashboard")
        root.geometry("1040x720")
        root.minsize(900, 620)
        root.attributes("-topmost", True)
        root.configure(bg="#101217")

        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background="#101217")
        style.configure("Panel.TFrame", background="#171b22", borderwidth=1, relief="solid")
        style.configure("TLabel", background="#101217", foreground="#eef2f7", font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background="#171b22", foreground="#9aa7b6", font=("Segoe UI", 9))
        style.configure("Title.TLabel", background="#171b22", foreground="#f6f8fb", font=("Segoe UI", 16, "bold"))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Horizontal.TProgressbar", troughcolor="#232a34", background="#4cc9f0")

        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=0)
        root.rowconfigure(0, weight=1)

        left = ttk.Frame(root, style="TFrame", padding=14)
        left.grid(row=0, column=0, sticky="nsew")
        left.rowconfigure(2, weight=1)
        left.columnconfigure(0, weight=1)

        header = ttk.Frame(left, style="Panel.TFrame", padding=14)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        avatar_canvas = tk.Canvas(header, width=86, height=86, bg="#171b22", highlightthickness=0)
        avatar_canvas.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 14))
        avatar_canvas.create_oval(8, 8, 78, 78, fill="#243447", outline="#58a6ff", width=3)
        avatar_canvas.create_oval(28, 34, 34, 40, fill="#d6f3ff", outline="")
        avatar_canvas.create_oval(52, 34, 58, 40, fill="#d6f3ff", outline="")
        mouth = avatar_canvas.create_line(30, 56, 56, 56, fill="#37d67a", width=3, smooth=True)

        title = ttk.Label(header, text="Lokaler Agent", style="Title.TLabel")
        title.grid(row=0, column=1, sticky="sw")
        status = ttk.Label(header, text="Bereit", style="Muted.TLabel")
        status.grid(row=1, column=1, sticky="nw")

        progress = ttk.Progressbar(header, mode="indeterminate", length=190)
        progress.grid(row=0, column=2, rowspan=2, sticky="e", padx=(12, 0))

        context_box = ttk.Frame(left, style="Panel.TFrame", padding=10)
        context_box.grid(row=1, column=0, sticky="ew", pady=(12, 12))
        context_box.columnconfigure(0, weight=1)
        ttk.Label(context_box, text="Aktueller Kontext", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        context_text = tk.Text(
            context_box,
            height=5,
            wrap="word",
            bg="#0f131a",
            fg="#dfe7f1",
            insertbackground="#dfe7f1",
            relief="flat",
            padx=10,
            pady=8,
        )
        context_text.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        chat_box = ttk.Frame(left, style="Panel.TFrame", padding=10)
        chat_box.grid(row=2, column=0, sticky="nsew")
        chat_box.rowconfigure(1, weight=1)
        chat_box.columnconfigure(0, weight=1)
        ttk.Label(chat_box, text="Chat", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        chat_text = tk.Text(
            chat_box,
            wrap="word",
            bg="#0f131a",
            fg="#f3f6fb",
            insertbackground="#f3f6fb",
            relief="flat",
            padx=12,
            pady=10,
        )
        chat_text.grid(row=1, column=0, sticky="nsew", pady=(6, 8))
        chat_text.tag_configure("user", foreground="#37d67a")
        chat_text.tag_configure("agent", foreground="#58a6ff")
        chat_text.tag_configure("system", foreground="#ffd166")

        input_row = ttk.Frame(chat_box, style="Panel.TFrame")
        input_row.grid(row=2, column=0, sticky="ew")
        input_row.columnconfigure(0, weight=1)
        entry = ttk.Entry(input_row)
        entry.grid(row=0, column=0, sticky="ew", ipady=5)

        def append_chat(prefix: str, text: str, tag: str) -> None:
            chat_text.insert("end", f"{prefix}: ", tag)
            chat_text.insert("end", text.strip() + "\n\n")
            chat_text.see("end")

        def set_thinking(active: bool, text: str = "") -> None:
            if active:
                status.config(text=text or "Denke nach...")
                progress.start(12)
                avatar_canvas.itemconfig(mouth, fill="#ffd166")
            else:
                status.config(text=text or "Bereit")
                progress.stop()
                avatar_canvas.itemconfig(mouth, fill="#37d67a")

        def send_message() -> None:
            value = entry.get().strip()
            if not value:
                return
            entry.delete(0, "end")
            append_chat("Du", value, "user")
            set_thinking(True, "Denke nach...")

            def worker() -> None:
                started = time.time()
                response = self._chat_direct(value)
                elapsed = time.time() - started
                self._queue.put(("chat_response", json.dumps({"text": response, "elapsed": elapsed}, ensure_ascii=False)))

            threading.Thread(target=worker, daemon=True).start()

        send_btn = ttk.Button(input_row, text="Senden", style="Accent.TButton", command=send_message)
        send_btn.grid(row=0, column=1, padx=(8, 0), ipadx=12, ipady=3)
        entry.bind("<Return>", lambda _event: send_message())

        right = ttk.Frame(root, style="Panel.TFrame", padding=14)
        right.grid(row=0, column=1, sticky="ns", padx=(0, 14), pady=14)
        right.columnconfigure(0, weight=1)

        ttk.Label(right, text="Trust Center", style="Title.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))
        ttk.Label(
            right,
            text="Speichert nur lokale Regeln. Kritische Aktionen bleiben geschuetzt.",
            style="Muted.TLabel",
            wraplength=280,
        ).grid(row=1, column=0, sticky="ew", pady=(0, 12))

        bool_vars: dict[str, Any] = {}

        def save_from_ui() -> None:
            for key, var in bool_vars.items():
                self.permissions[key] = bool(var.get())
            for key, var in slider_vars.items():
                self.permissions[key] = int(float(var.get()))
            self.permissions["screen_scope"] = scope_var.get()
            self.permissions["code_scope"] = code_scope_var.get()
            self.permissions["code_project_path"] = project_var.get().strip()
            self._save_permissions()
            self._queue.put(("log", f"Trust-Profil gespeichert: {self.permissions_path}"))

        checks = [
            ("screen_context", "Bildschirmkontext erlauben"),
            ("audio_listen_after_signal", "Mikro nach Startsignal"),
            ("auto_memory", "Memory ohne Nachfrage"),
            ("discord_send_after_approval", "Discord nach Freigabe"),
            ("code_repair_after_approval", "Code-Reparatur nach Freigabe"),
            ("web_access", "Webzugriff erlauben"),
            ("external_app_control", "Externe Apps steuern"),
            ("deep_thinking_auto", "Tiefes Denken automatisch"),
            ("debug_observability", "Debug / Observability anzeigen"),
        ]
        row = 2
        for key, label in checks:
            var = tk.BooleanVar(value=bool(self.permissions.get(key)))
            bool_vars[key] = var
            ttk.Checkbutton(right, text=label, variable=var, command=save_from_ui).grid(
                row=row, column=0, sticky="w", pady=4
            )
            row += 1

        ttk.Separator(right).grid(row=row, column=0, sticky="ew", pady=12)
        row += 1

        ttk.Label(right, text="Was darf er sehen?", style="Muted.TLabel").grid(row=row, column=0, sticky="w")
        row += 1
        scope_var = tk.StringVar(value=str(self.permissions.get("screen_scope", "active")))
        screen_scope = ttk.Combobox(
            right,
            textvariable=scope_var,
            state="readonly",
            values=("active", "vs_code", "unity", "browser", "discord", "all", "off"),
        )
        screen_scope.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        screen_scope.bind("<<ComboboxSelected>>", lambda _event: save_from_ui())
        row += 1

        ttk.Label(right, text="Code-Lesezugriff", style="Muted.TLabel").grid(row=row, column=0, sticky="w")
        row += 1
        code_scope_var = tk.StringVar(value=str(self.permissions.get("code_scope", "agent_workspace")))
        code_scope = ttk.Combobox(
            right,
            textvariable=code_scope_var,
            state="readonly",
            values=("disabled", "agent_workspace", "custom_project"),
        )
        code_scope.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        code_scope.bind("<<ComboboxSelected>>", lambda _event: save_from_ui())
        row += 1

        ttk.Label(right, text="Projektpfad fuer custom_project", style="Muted.TLabel").grid(row=row, column=0, sticky="w")
        row += 1
        project_var = tk.StringVar(value=str(self.permissions.get("code_project_path", "")))
        project_entry = ttk.Entry(right, textvariable=project_var)
        project_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        project_entry.bind("<FocusOut>", lambda _event: save_from_ui())
        project_entry.bind("<Return>", lambda _event: save_from_ui())
        row += 1

        slider_vars: dict[str, Any] = {}
        sliders = [
            ("creativity", "Kreativitaet"),
            ("detail_level", "Antwort-Tiefe"),
            ("initiative", "Eigeninitiative"),
        ]
        for key, label in sliders:
            ttk.Label(right, text=label, style="Muted.TLabel").grid(row=row, column=0, sticky="w")
            row += 1
            var = tk.DoubleVar(value=float(self.permissions.get(key, 50)))
            slider_vars[key] = var
            ttk.Scale(right, from_=0, to=100, orient="horizontal", variable=var, command=lambda _v: save_from_ui()).grid(
                row=row, column=0, sticky="ew", pady=(0, 10)
            )
            row += 1

        ttk.Button(right, text="Trust-Profil speichern", command=save_from_ui).grid(row=row, column=0, sticky="ew", pady=(8, 0))
        row += 1
        ttk.Button(right, text="Chat leeren", command=lambda: chat_text.delete("1.0", "end")).grid(row=row, column=0, sticky="ew", pady=(8, 0))

        append_chat("System", "Avatar bereit. Du kannst hier direkt mit der KI schreiben.", "system")

        def pump() -> None:
            while True:
                try:
                    kind, value = self._queue.get_nowait()
                except queue.Empty:
                    break

                if kind == "stop":
                    root.destroy()
                    return
                if kind == "status":
                    status.config(text=value[:120])
                elif kind == "context":
                    context_text.delete("1.0", "end")
                    context_text.insert("end", value)
                elif kind == "log":
                    append_chat("Log", value, "system")
                elif kind == "chat_response":
                    try:
                        data = json.loads(value)
                        append_chat("KI", data.get("text", ""), "agent")
                        set_thinking(False, f"Bereit ({data.get('elapsed', 0):.1f}s)")
                    except Exception:
                        append_chat("KI", value, "agent")
                        set_thinking(False)

            if self._running:
                root.after(150, pump)
            else:
                root.destroy()

        root.after(150, pump)
        root.protocol("WM_DELETE_WINDOW", self.stop)
        root.mainloop()
        self._running = False
