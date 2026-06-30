"""
Tools Module: Workbench operations
"""
import subprocess
import sys
import os
from pathlib import Path
from typing import Any, Dict, Optional, List

class WorkbenchTools:
    """
    Tools für die Workbench (Python-Script-Sandbox).
    - wb_write_file
    - wb_read_file
    - wb_run_python
    - wb_pip_install
    """

    def __init__(self, sandbox_mgr, max_chars: int = 8000, timeout_sec: int = 120):
        self.sandbox = sandbox_mgr
        self.max_chars = max_chars
        self.timeout_sec = timeout_sec
        self.venv_python = (self.sandbox.venv_dir / "Scripts" / "python.exe").resolve()
        allowed = os.environ.get("LOCAL_AGENT_ALLOWED_PIP_PACKAGES", "")
        self.allowed_packages = {p.strip().lower() for p in allowed.split(",") if p.strip()}
        self.allow_any_pip = os.environ.get("LOCAL_AGENT_ALLOW_ANY_PIP", "0") == "1"

    def ensure_venv_interactive(self) -> tuple[bool, str]:
        """Erstellt Virtual Environment auf Anfrage."""
        if self.venv_python.exists():
            return True, "ok"

        print("\n=== APPROVAL REQUIRED (CREATE VENV) ===")
        print("Missing:", str(self.sandbox.venv_dir))
        ans = input("Create venv now? [y/N] ").strip().lower()
        if ans != "y":
            return False, "User denied venv creation."

        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(self.sandbox.venv_dir)],
                cwd=str(self.sandbox.base_dir),
                capture_output=True,
                text=True,
                timeout=300,
                shell=False,
            )
            subprocess.run(
                [str(self.venv_python), "-m", "pip", "install", "--upgrade", "pip"],
                cwd=str(self.sandbox.workbench_dir),
                capture_output=True,
                text=True,
                timeout=300,
                shell=False,
            )
            return self.venv_python.exists(), "created"
        except Exception as e:
            return False, str(e)

    def wb_write_file(self, filename: str, content: str) -> Dict[str, Any]:
        """Schreibt Datei in Workbench."""
        try:
            path = self.sandbox.validate_workbench_path(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return {"ok": True, "file": str(path)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def wb_read_file(self, filename: str, max_chars: Optional[int] = None) -> Dict[str, Any]:
        """Liest Datei aus Workbench."""
        try:
            path = self.sandbox.validate_workbench_path(filename)
            if not path.exists():
                return {"ok": False, "error": f"File not found: {filename}"}

            content = path.read_text(encoding="utf-8", errors="replace")
            max_c = max_chars or self.max_chars
            return {"ok": True, "file": str(path), "content": content[:max_c]}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def wb_run_python(self, filename: str, args: Optional[List[str]] = None) -> Dict[str, Any]:
        """Führt Python-Script in Workbench-Venv aus."""
        args = args or []

        try:
            path = self.sandbox.validate_workbench_path(filename)
            if not path.exists():
                return {"ok": False, "error": f"Script not found: {filename}"}

            ok, reason = self.ensure_venv_interactive()
            if not ok:
                return {"ok": False, "error": reason}

            cmd = [str(self.venv_python), str(path)] + args

            print("\n=== APPROVAL REQUIRED (RUN PYTHON) ===")
            print("Command:", cmd)
            print("CWD:", str(self.sandbox.workbench_dir))
            ans = input("Execute? [y/N] ").strip().lower()
            if ans != "y":
                return {"ok": False, "error": "User denied execution."}

            p = subprocess.run(
                cmd,
                cwd=str(self.sandbox.workbench_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                shell=False,
            )
            
            stdout = p.stdout or ""
            stderr = p.stderr or ""
            
            return {
                "ok": p.returncode == 0,
                "returncode": p.returncode,
                "stdout": stdout[-4000:] if len(stdout) > 4000 else stdout,
                "stderr": stderr[-4000:] if len(stderr) > 4000 else stderr,
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"Timeout after {self.timeout_sec}s"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def wb_pip_install(self, packages: List[str]) -> Dict[str, Any]:
        """Installiert Pakete in Workbench-Venv."""
        import re
        pkg_re = re.compile(r"^[a-zA-Z0-9_.-]+$")

        try:
            if not packages or any((not pkg_re.match(p)) for p in packages):
                return {"ok": False, "error": "Invalid package list. Use simple names like 'pandas'."}

            normalized = [p.lower() for p in packages]
            if not self.allow_any_pip:
                blocked = [p for p in normalized if p not in self.allowed_packages]
                if blocked:
                    return {
                        "ok": False,
                        "error": (
                            "Pip install blocked by policy. Set LOCAL_AGENT_ALLOWED_PIP_PACKAGES "
                            "or LOCAL_AGENT_ALLOW_ANY_PIP=1 if you intentionally trust this install. "
                            f"Blocked: {blocked}"
                        ),
                    }

            ok, reason = self.ensure_venv_interactive()
            if not ok:
                return {"ok": False, "error": reason}

            cmd = [str(self.venv_python), "-m", "pip", "install"] + packages

            print("\n=== APPROVAL REQUIRED (PIP INSTALL) ===")
            print("Command:", cmd)
            print("Packages:", ", ".join(packages))
            print("Index: default pip index")
            ans = input("Execute? [y/N] ").strip().lower()
            if ans != "y":
                return {"ok": False, "error": "User denied installation."}

            p = subprocess.run(
                cmd,
                cwd=str(self.sandbox.workbench_dir),
                capture_output=True,
                text=True,
                timeout=300,
                shell=False,
            )

            stdout = p.stdout or ""
            stderr = p.stderr or ""

            return {
                "ok": p.returncode == 0,
                "returncode": p.returncode,
                "stdout": stdout[-4000:] if len(stdout) > 4000 else stdout,
                "stderr": stderr[-4000:] if len(stderr) > 4000 else stderr,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
