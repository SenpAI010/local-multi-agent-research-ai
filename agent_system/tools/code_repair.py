"""
Approval-based repair tools for the real workspace.

These tools are intentionally separate from the normal sandbox workbench. They
only operate after explicit user approval and never execute code automatically.
"""
from pathlib import Path
from typing import Dict, Any
import difflib
import time


class CodeRepairTools:
    """Safe, approval-based file replacement for workspace repairs."""

    def __init__(self, workspace_dir: Path, sandbox_mgr):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.sandbox = sandbox_mgr
        self.patch_dir = self.sandbox.base_dir / "proposed_repairs"
        self.backup_dir = self.sandbox.base_dir / "repair_backups"
        self.patch_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def propose_file_replacement(self, relative_path: str, new_content: str) -> Dict[str, Any]:
        """Save a proposed replacement in the agent sandbox."""
        target = self._validate_workspace_path(relative_path)
        proposal = self.patch_dir / (relative_path.replace("\\", "__").replace("/", "__") + ".proposal")
        proposal.parent.mkdir(parents=True, exist_ok=True)
        proposal.write_text(new_content, encoding="utf-8")
        return {
            "ok": True,
            "target": str(target),
            "proposal": str(proposal),
            "message": "Proposal saved. Use apply_file_replacement with approval to modify the real file.",
        }

    def apply_file_replacement(self, relative_path: str, proposal_path: str) -> Dict[str, Any]:
        """Apply a proposed replacement after explicit user approval."""
        target = self._validate_workspace_path(relative_path)
        proposal = Path(proposal_path).resolve()
        if not self.sandbox.is_within(self.patch_dir, proposal):
            return {"ok": False, "error": "Proposal must be inside agent_sandbox/proposed_repairs."}
        if not proposal.exists():
            return {"ok": False, "error": "Proposal file not found."}

        old_text = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
        new_text = proposal.read_text(encoding="utf-8")
        diff = "\n".join(difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile=str(target),
            tofile=str(proposal),
            lineterm="",
        ))
        preview = diff[:6000] + ("\n...diff truncated..." if len(diff) > 6000 else "")

        print("\n=== APPROVAL REQUIRED (REAL WORKSPACE REPAIR) ===")
        print(f"Target: {target}")
        print(f"Proposal: {proposal}")
        print("\nDiff preview:")
        print(preview if preview else "(no diff)")
        ans = input("Apply this replacement to the real workspace file? [y/N] ").strip().lower()
        if ans not in {"y", "yes", "j", "ja"}:
            return {"ok": False, "error": "User denied repair."}

        backup = None
        if target.exists():
            backup = self.backup_dir / f"{relative_path.replace('\\', '__').replace('/', '__')}.{int(time.time())}.bak"
            backup.write_text(old_text, encoding="utf-8")

        target.write_text(new_text, encoding="utf-8")
        return {"ok": True, "file": str(target), "backup": str(backup) if backup else None}

    def _validate_workspace_path(self, relative_path: str) -> Path:
        rel = relative_path.strip().replace("\\", "/")
        if rel.startswith("/") or ".." in rel:
            raise ValueError("Invalid workspace path")
        target = (self.workspace_dir / rel).resolve()
        if not self.sandbox.is_within(self.workspace_dir, target):
            raise ValueError("Path outside workspace")
        if self.sandbox.is_within(self.sandbox.base_dir, target):
            raise ValueError("Use sandbox tools for agent_sandbox files")
        return target


__all__ = ["CodeRepairTools"]
