"""Research infrastructure: full text, Mathlib workspaces and reports."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class PDFCorpus:
    def __init__(self, chunk_chars: int = 1800, overlap: int = 250) -> None:
        self.chunk_chars = max(500, chunk_chars)
        self.overlap = max(0, min(overlap, self.chunk_chars // 2))

    def ingest(self, pdf_path: Path, project_dir: Path) -> Dict[str, Any]:
        pdf_path = Path(pdf_path).resolve()
        if not pdf_path.is_file() or pdf_path.suffix.lower() != ".pdf":
            raise ValueError(f"PDF not found: {pdf_path}")
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("pypdf is required; install project requirements.") from exc
        digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        reader = PdfReader(str(pdf_path))
        chunks: List[Dict[str, Any]] = []
        page_stats = []
        for page_no, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").replace("\x00", " ").strip()
            page_stats.append({"page": page_no, "characters": len(text)})
            start = 0
            while start < len(text):
                body = text[start:start + self.chunk_chars].strip()
                if body:
                    chunks.append({
                        "chunk_id": f"P{page_no:04d}C{len(chunks)+1:05d}",
                        "page": page_no,
                        "start_char": start,
                        "text": body,
                        "citation": f"{pdf_path.name}, p. {page_no}",
                    })
                if start + self.chunk_chars >= len(text):
                    break
                start += self.chunk_chars - self.overlap
        corpus_dir = project_dir / "fulltext"
        corpus_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "document_id": "PDF-" + digest[:16],
            "file_name": pdf_path.name,
            "source_path": str(pdf_path),
            "sha256": digest,
            "pages": len(reader.pages),
            "page_stats": page_stats,
            "chunks": chunks,
            "extraction_status": "ok" if chunks else "no_extractable_text",
        }
        target = corpus_dir / f"{record['document_id']}.json"
        target.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        record["corpus_path"] = str(target)
        return record


class MathlibWorkspace:
    def __init__(self, runner: Optional[Callable[..., Any]] = None) -> None:
        self.runner = runner or subprocess.run

    def setup(self, project_dir: Path, update: bool = False, timeout: int = 900) -> Dict[str, Any]:
        if project_dir.parent.name == "research":
            workspace_base = project_dir.parent.parent / "mathlib_workspaces"
            existing = []
            if workspace_base.exists():
                existing = [p for p in workspace_base.iterdir() if (p / "lakefile.toml").exists() or (p / "lakefile.lean").exists()]
            root = sorted(existing)[0] if existing else workspace_base / "shared"
        else:
            root = project_dir / "formal_proofs" / "mathlib_workspace"
        root.parent.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        elan_bin = str(Path.home() / ".elan" / "bin")
        env["PATH"] = elan_bin + os.pathsep + env.get("PATH", "")
        lake_exe = shutil.which("lake", path=env["PATH"]) or str(Path(elan_bin) / "lake.exe")
        actions = []
        if not (root / "lakefile.toml").exists() and not (root / "lakefile.lean").exists():
            if root.exists() and any(root.iterdir()):
                return {"ready": False, "status": "nonempty_workspace_without_lakefile", "workspace": str(root), "actions": actions}
            root.parent.mkdir(parents=True, exist_ok=True)
            proc = self.runner([lake_exe, "new", root.name, "math-lax"], cwd=str(root.parent), capture_output=True, text=True, timeout=timeout, shell=False, env=env)
            actions.append(self._action("lake_new_math_lax", proc))
            if proc.returncode != 0:
                return {"ready": False, "status": "setup_failed", "workspace": str(root), "actions": actions}
        if update:
            proc = self.runner([lake_exe, "update"], cwd=str(root), capture_output=True, text=True, timeout=timeout, shell=False, env=env)
            actions.append(self._action("lake_update", proc))
            if proc.returncode != 0:
                return {"ready": False, "status": "update_failed", "workspace": str(root), "actions": actions}
        mathlib_olean = root / ".lake" / "packages" / "mathlib" / ".lake" / "build" / "lib" / "lean" / "Mathlib.olean"
        if not mathlib_olean.exists():
            proc = self.runner([lake_exe, "build", "Mathlib"], cwd=str(root), capture_output=True, text=True, timeout=timeout, shell=False, env=env)
            actions.append(self._action("lake_build_mathlib", proc))
            if proc.returncode != 0:
                return {"ready": False, "status": "mathlib_build_failed", "workspace": str(root), "actions": actions}
        return {"ready": True, "status": "ready", "workspace": str(root), "actions": actions, "mathlib_dependency": True}

    @staticmethod
    def _action(name: str, proc: Any) -> Dict[str, Any]:
        return {"action": name, "returncode": int(proc.returncode), "stdout": str(proc.stdout)[-3000:], "stderr": str(proc.stderr)[-3000:]}


class ExperimentProtocolValidator:
    REQUIRED = ("hypothesis", "independent_variables", "dependent_variables", "controls", "sample_size_or_power", "analysis_plan", "failure_criteria", "reproduction_steps")

    def validate(self, protocol: Dict[str, Any]) -> Dict[str, Any]:
        missing = [key for key in self.REQUIRED if not protocol.get(key)]
        issues = [f"missing:{key}" for key in missing]
        if protocol.get("analysis_plan") and not protocol.get("uncertainty_method"):
            issues.append("missing:uncertainty_method")
        if protocol.get("human_or_sensitive_data") and not protocol.get("ethics_approval"):
            issues.append("missing:ethics_approval")
        return {"valid": not issues, "issues": issues, "required_fields": list(self.REQUIRED)}


class ResearchReportExporter:
    def export(self, project_dir: Path) -> Dict[str, str]:
        def load(name: str, default: Any) -> Any:
            path = project_dir / name
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return default
        data = {
            "status": load("status.json", {}),
            "checkpoint": load("checkpoint.json", {}),
            "claims": load("claims.json", []),
            "formal_lemmas": load("formal_lemmas.json", []),
            "sources": load("sources.json", []),
            "fulltext_documents": [],
        }
        for path in sorted((project_dir / "fulltext").glob("*.json")) if (project_dir / "fulltext").exists() else []:
            doc = load(str(path.relative_to(project_dir)), {})
            data["fulltext_documents"].append({k: doc.get(k) for k in ("document_id", "file_name", "sha256", "pages", "extraction_status")})
        reports = project_dir / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        json_path = reports / "research_report.json"
        json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        lines = [f"# Research report: {data['status'].get('problem', project_dir.name)}", "", f"Status: {data['status'].get('current_status', 'unknown')}", "", "## Claims", ""]
        for c in data["claims"]:
            lines.append(f"- **{c.get('claim_id')} [{c.get('status')}]** {c.get('text')}")
        lines.extend(["", "## Formal lemmas", ""])
        for l in data["formal_lemmas"]:
            lines.append(f"- **{l.get('lemma_id')} [{l.get('proof_status')}]** {l.get('title')}: {l.get('conclusion')}")
        lines.extend(["", "## Sources", ""])
        for s in data["sources"]:
            lines.append(f"- {s.get('source_id', '?')}: {s.get('title')} — {s.get('url', '')}")
        lines.extend(["", "## Reproducibility", "", "Formal verification records and SHA-256-bound artifacts are stored under `formal_proofs/`. Experiment artifacts remain evidence unless independently reproduced."])
        md_path = reports / "research_report.md"
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"json": str(json_path), "markdown": str(md_path)}
