"""
Read-only code watcher for proactive IDE/workspace feedback.

The watcher never writes to the observed workspace. It scans source files for
cheap, local issues and reports findings through callbacks.
"""
import ast
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional


@dataclass
class CodeFinding:
    file: str
    line: int
    severity: str
    message: str


class CodeWatcher:
    """Polls a workspace read-only and reports code findings."""

    DEFAULT_EXTENSIONS = {".py", ".ps1", ".js", ".html", ".css", ".json", ".md"}
    EXCLUDED_DIRS = {
        ".git", ".venv", ".venv_personal_agent", ".venv_workbench",
        "__pycache__", "agent_sandbox", ".mypy_cache", ".pytest_cache",
        "Main",
    }

    def __init__(
        self,
        workspace_dir: Path,
        poll_interval_sec: float = 5.0,
        max_file_bytes: int = 500_000,
    ):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.poll_interval_sec = poll_interval_sec
        self.max_file_bytes = max_file_bytes
        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        self.callbacks: List[Callable[[CodeFinding], None]] = []
        self._seen_mtimes: Dict[Path, float] = {}
        self._last_reported: Dict[str, float] = {}
        self.live_severities = {"error"}
        self.allowed_roots: List[Path] = [self.workspace_dir]

    def add_callback(self, callback: Callable[[CodeFinding], None]) -> None:
        self.callbacks.append(callback)

    def set_allowed_roots(self, roots: List[Path]) -> None:
        """Set read-only roots that may be scanned."""
        if not roots:
            self.allowed_roots = []
            self._seen_mtimes.clear()
            return

        resolved = []
        for root in roots:
            try:
                path = Path(root).expanduser().resolve()
            except OSError:
                continue
            if path.exists() and path.is_dir():
                resolved.append(path)
        self.allowed_roots = resolved or [self.workspace_dir]
        self._seen_mtimes.clear()

    def start(self) -> None:
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2)

    def _run_loop(self) -> None:
        while self.is_running:
            try:
                self.scan_once()
            except Exception:
                pass
            time.sleep(self.poll_interval_sec)

    def scan_once(self) -> List[CodeFinding]:
        findings: List[CodeFinding] = []
        for path in self._iter_files():
            try:
                stat = path.stat()
            except OSError:
                continue

            if stat.st_size > self.max_file_bytes:
                continue

            old_mtime = self._seen_mtimes.get(path)
            if old_mtime == stat.st_mtime:
                continue

            self._seen_mtimes[path] = stat.st_mtime
            findings.extend(self._scan_file(path, include_style=False))

        for finding in findings:
            self._emit(finding)

        return findings

    def _iter_files(self):
        for root in self.allowed_roots:
            for path in root.rglob("*"):
                if path.is_symlink():
                    continue
                if not path.is_file():
                    continue
                try:
                    resolved = path.resolve()
                    root_resolved = root.resolve()
                except OSError:
                    continue
                if not (resolved == root_resolved or root_resolved in resolved.parents):
                    continue
                if path.suffix.lower() not in self.DEFAULT_EXTENSIONS:
                    continue
                if any(part in self.EXCLUDED_DIRS for part in path.parts):
                    continue
                yield path

    def scan_full_once(self) -> List[CodeFinding]:
        findings: List[CodeFinding] = []
        for path in self._iter_files():
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_size > self.max_file_bytes:
                continue
            findings.extend(self._scan_file(path, include_style=True))
        return findings

    def _scan_file(self, path: Path, include_style: bool = False) -> List[CodeFinding]:
        rel = self._display_path(path)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return [CodeFinding(rel, 1, "warning", f"Could not read file: {e}")]

        findings: List[CodeFinding] = []

        if path.suffix.lower() == ".py":
            try:
                ast.parse(text, filename=rel)
            except SyntaxError as e:
                findings.append(CodeFinding(
                    file=rel,
                    line=e.lineno or 1,
                    severity="error",
                    message=e.msg,
                ))
                return findings

        if not include_style:
            return findings

        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            lowered = stripped.lower()
            is_scanner_rule = path.name == "code_watcher.py" and (
                "findings.append" in stripped
                or '"shell=true"' in lowered
                or '"0.0.0.0"' in lowered
                or '"global_allow"' in lowered
                or '"allow_any"' in lowered
                or '"start-process"' in lowered
                or '"input("' in lowered
            )
            if path.suffix.lower() == ".py" and "pring(" in stripped and "print(" not in stripped:
                findings.append(CodeFinding(rel, i, "warning", "Possible typo: did you mean print(...)?"))
            if path.suffix.lower() == ".py" and stripped.startswith("except:"):
                findings.append(CodeFinding(rel, i, "warning", "Bare except catches too much; prefer except Exception."))
            if stripped.startswith("#") and ("TODO" in stripped or "FIXME" in stripped):
                findings.append(CodeFinding(rel, i, "info", stripped[:120]))
            if is_scanner_rule:
                continue
            if "shell=true" in lowered:
                findings.append(CodeFinding(rel, i, "warning", "Security: shell=True increases command-injection risk."))
            if "0.0.0.0" in lowered:
                findings.append(CodeFinding(rel, i, "warning", "Security: binds/listens on 0.0.0.0; prefer 127.0.0.1 for local agent."))
            if "http://" in lowered and "127.0.0.1" not in lowered and "localhost" not in lowered:
                findings.append(CodeFinding(rel, i, "info", "Network: non-local HTTP URL appears in code. Verify this is intentional."))
            if "global_allow" in lowered or "allow_any" in lowered:
                findings.append(CodeFinding(rel, i, "warning", "Security: broad allow flag detected; keep disabled by default."))
            if "start-process" in lowered and "windowstyle hidden" in lowered:
                findings.append(CodeFinding(rel, i, "info", "Process: hidden background process start; ensure user-visible stop path exists."))
            if "input(" in stripped and path.name != "main_phase3.py":
                findings.append(CodeFinding(rel, i, "info", "Architecture: direct input() outside main CLI can block orchestration."))

        return findings

    def _display_path(self, path: Path) -> str:
        for root in self.allowed_roots:
            try:
                return str(path.relative_to(root))
            except ValueError:
                continue
        try:
            return str(path.relative_to(self.workspace_dir))
        except ValueError:
            return str(path)

    def _emit(self, finding: CodeFinding) -> None:
        if finding.severity not in self.live_severities:
            return

        key = f"{finding.file}:{finding.line}:{finding.message}"
        now = time.time()
        if now - self._last_reported.get(key, 0) < 30:
            return
        self._last_reported[key] = now

        for callback in self.callbacks:
            try:
                callback(finding)
            except Exception:
                pass


__all__ = ["CodeWatcher", "CodeFinding"]
