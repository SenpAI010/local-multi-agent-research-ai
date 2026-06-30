"""
Tools Module: System operations
"""
import subprocess
from typing import Any, Dict, Optional, List, Tuple
from pathlib import Path

class SystemTools:
    """
    Tools für Systembefehle (STARK EINGESCHRÄNKT).
    - run_command (mit Allowlist)
    """

    def __init__(self, sandbox_mgr, timeout_sec: int = 120):
        self.sandbox = sandbox_mgr
        self.timeout_sec = timeout_sec
        
        # Allowlist: program -> allowed first args
        self.allowlist = {
            "python": {"-m"},
            "python.exe": {"-m"},
            "git": {"status", "diff", "log", "pull", "branch", "rev-parse"},
            "git.exe": {"status", "diff", "log", "pull", "branch", "rev-parse"},
        }
        self.allowed_python_modules = {"py_compile", "pytest"}
        
        # Blockierte Token
        self.blocked_tokens = {
            "rm", "del", "erase", "format", "shutdown", "reboot",
            "reg", "powershell", "pwsh", "cmd", "curl", "wget", "certutil", "pip", "pip3"
        }

    def run_command(
        self,
        program: str,
        args: Optional[List[str]] = None,
        cwd: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Führt einen Shell-Command aus (STARK EINGESCHRÄNKT).
        
        - program muss in Allowlist sein
        - First arg muss in allowed set sein
        - Keine blocked tokens
        - cwd muss in Sandbox sein
        """
        args = args or []

        try:
            ok, reason = self._validate_command(program, args)
            if not ok:
                return {"ok": False, "error": reason}

            # CWD validieren
            workdir = self.sandbox.base_dir
            if cwd:
                candidate = Path(cwd).expanduser().resolve()
                if not self.sandbox.is_within(self.sandbox.base_dir, candidate):
                    return {"ok": False, "error": "cwd must be inside sandbox."}
                workdir = candidate

            cmd = [program] + args

            print("\n=== APPROVAL REQUIRED (RUN COMMAND) ===")
            print("Command:", cmd)
            print("Working directory:", str(workdir))
            ans = input("Execute? [y/N] ").strip().lower()
            if ans != "y":
                return {"ok": False, "error": "User denied execution."}

            p = subprocess.run(
                cmd,
                cwd=str(workdir),
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
            return {"ok": False, "error": f"Command timed out after {self.timeout_sec}s"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _validate_command(self, program: str, args: List[str]) -> Tuple[bool, str]:
        """Validiert einen Command gegen Allowlist."""
        
        if program.lower() in self.blocked_tokens:
            return False, f"Program blocked: {program}"

        if program not in self.allowlist:
            return False, f"Program not in allowlist: {program}"

        joined = " ".join([program] + args).lower()
        for tok in self.blocked_tokens:
            if tok in joined.split():
                return False, f"Blocked token detected: {tok}"

        allowed_first = self.allowlist[program]
        if not args:
            return False, "Args required for this program."
        
        if args[0] not in allowed_first:
            return False, f"First arg '{args[0]}' not allowed for {program}."

        if program.lower() in {"python", "python.exe"}:
            if len(args) < 2 or args[1] not in self.allowed_python_modules:
                return False, "Only python -m py_compile or python -m pytest are allowed."

        return True, "OK"
