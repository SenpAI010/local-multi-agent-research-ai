"""
Sandbox-Verwaltung: Restricted directories & path validation
"""
from pathlib import Path
from typing import Optional

class SandboxManager:
    """
    Verwaltet sichere Verzeichnisse für den Agent.
    - agent_sandbox/ (Hauptsandbox)
    - workbench/ (Python-Scripts)
    - notes/ (Text-Notizen)
    - .venv_workbench/ (Python-Venv)
    """

    def __init__(self, base_path: Optional[Path] = None):
        self.base_dir = Path(base_path or "./agent_sandbox").resolve()
        self.workbench_dir = (self.base_dir / "workbench").resolve()
        self.notes_dir = (self.base_dir / "notes").resolve()
        self.venv_dir = (self.base_dir / ".venv_workbench").resolve()
        self.db_path = (self.base_dir / "memory.sqlite3").resolve()
        self.profile_path = (self.base_dir / "user_profile.json").resolve()

    def ensure_dirs(self) -> None:
        """Erstellt alle Sandbox-Verzeichnisse."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.workbench_dir.mkdir(parents=True, exist_ok=True)
        self.notes_dir.mkdir(parents=True, exist_ok=True)

    def is_within(self, base: Path, target: Path) -> bool:
        """Validiert, dass target sich innerhalb von base befindet."""
        try:
            base = base.resolve()
            target = target.resolve()
            return base == target or base in target.parents
        except Exception:
            return False

    def validate_workbench_path(self, filename: str) -> Path:
        """
        Validiert einen Dateinamen für die Workbench.
        Wirft ValueError, wenn ungültig.
        """
        filename = filename.strip().replace("\\", "/")
        if filename.startswith("/") or ".." in filename:
            raise ValueError(f"Invalid filename: {filename}")

        path = (self.workbench_dir / filename).resolve()
        if not self.is_within(self.workbench_dir, path):
            raise ValueError(f"Path outside workbench: {path}")

        return path

    def validate_notes_path(self, filename: str) -> Path:
        """Validiert einen Dateinamen für Notes."""
        filename = filename.strip().replace("\\", "/")
        if filename.startswith("/") or ".." in filename:
            raise ValueError(f"Invalid filename: {filename}")

        path = (self.notes_dir / filename).resolve()
        if not self.is_within(self.notes_dir, path):
            raise ValueError(f"Path outside notes: {path}")

        return path
