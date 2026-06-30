"""Independent formal-proof and lemma-integrity verification.

The verifier is deliberately fail-closed: only a successful Lean process over an
artifact without placeholders can produce ``formally_verified``.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional


@dataclass
class FormalVerificationResult:
    verified: bool
    backend: str
    status: str
    artifact_path: str
    artifact_sha256: str
    command: List[str]
    returncode: Optional[int]
    stdout: str
    stderr: str
    issues: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Lean4Verifier:
    """Compile Lean 4 artifacts in a project-local, auditable workspace."""

    PLACEHOLDERS = (
        r"\bsorry\b", r"\badmit\b", r"\baxiom\b", r"\bopaque\b",
        r"\bunsafe\b", r"by\s*\n?\s*exact\s+Classical\.choice",
    )
    DANGEROUS_COMMANDS = (
        r"#eval\b",
        r"\brun_tac\b",
        r"\belab\b",
        r"\bsyntax\b",
        r"\bmacro\b",
        r"\binitialize\b",
        r"\bIO\.",
        r"\bimport\s+Lean\b",
        r"\bimport\s+Lake\b",
        r"\bimport\s+Std\b",
    )
    IMPORT_ALLOWLIST = ("Mathlib",)

    def __init__(
        self,
        executable: str = "lean",
        timeout: int = 60,
        runner: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.executable = executable
        self.timeout = timeout
        self.runner = runner or subprocess.run

    def available(self) -> bool:
        return bool(shutil.which(self.executable))

    def verify(self, artifact: Path, cwd: Optional[Path] = None) -> FormalVerificationResult:
        artifact = Path(artifact).resolve()
        content = artifact.read_text(encoding="utf-8", errors="replace")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        issues = self._placeholder_issues(content)
        issues.extend(self._sandbox_policy_issues(content))
        workdir = Path(cwd or artifact.parent).resolve()
        has_lake = (workdir / "lakefile.toml").exists() or (workdir / "lakefile.lean").exists()
        elan_bin = Path.home() / ".elan" / "bin"
        lean_exe = shutil.which(self.executable) or str(elan_bin / f"{self.executable}.exe")
        lake_exe = shutil.which("lake") or str(elan_bin / "lake.exe")
        command = [lake_exe, "env", lean_exe, str(artifact)] if has_lake else [lean_exe, str(artifact)]
        if issues:
            status = "rejected_placeholder" if any("placeholder" in issue for issue in issues) else "rejected_unsafe_lean_artifact"
            return FormalVerificationResult(False, "lean4", status, str(artifact), digest, command, None, "", "", issues)
        executable_available = Path(lake_exe if has_lake else lean_exe).is_file() or shutil.which("lake" if has_lake else self.executable)
        if not executable_available and self.runner is subprocess.run:
            return FormalVerificationResult(False, "lean4", "backend_unavailable", str(artifact), digest, command, None, "", "Lean 4 executable not found.", ["lean_not_installed"])
        try:
            proc = self.runner(command, cwd=str(workdir), capture_output=True, text=True, timeout=self.timeout, shell=False)
        except Exception as exc:
            return FormalVerificationResult(False, "lean4", "backend_error", str(artifact), digest, command, None, "", str(exc), ["lean_execution_failed"])
        ok = proc.returncode == 0
        return FormalVerificationResult(
            ok, "lean4", "lean_artifact_verified" if ok else "compile_failed", str(artifact), digest,
            command, int(proc.returncode), str(proc.stdout)[-4000:], str(proc.stderr)[-4000:],
            [] if ok else ["lean_compile_failed"],
        )

    def _placeholder_issues(self, content: str) -> List[str]:
        return [f"forbidden_placeholder:{pattern}" for pattern in self.PLACEHOLDERS if re.search(pattern, content, re.I)]

    def _sandbox_policy_issues(self, content: str) -> List[str]:
        scanned = self._strip_lean_comments(content)
        issues = [
            f"forbidden_lean_command:{pattern}"
            for pattern in self.DANGEROUS_COMMANDS
            if re.search(pattern, scanned, re.I | re.M)
        ]
        for module in re.findall(r"^\s*import\s+([A-Za-z0-9_'.]+)", scanned, re.M):
            if not any(module == allowed or module.startswith(allowed + ".") for allowed in self.IMPORT_ALLOWLIST):
                issues.append(f"import_not_allowlisted:{module}")
        return issues

    def _strip_lean_comments(self, content: str) -> str:
        # Lean treats block comments as whitespace; remove them before scanning
        # so patterns like "/- comment -/ #eval ..." cannot hide commands.
        content = re.sub(r"/-.*?-/", " ", content, flags=re.S)
        content = re.sub(r"--.*?$", " ", content, flags=re.M)
        return content


class LemmaIntegrityChecker:
    """Cheap fail-closed checks before expensive model/formal verification."""

    BUILTINS = {
        "let", "if", "then", "for", "all", "real", "complex", "nat", "int",
        "zeta", "re", "im", "log", "exp", "sin", "cos", "sum", "prod", "infty",
        "mathbb", "mathcal", "mathrm", "operatorname", "frac", "left", "right",
        "geq", "leq", "forall", "exists", "to", "in", "dt", "dx", "ds",
    }

    def check(self, lemma: Dict[str, Any], claim_ids: Iterable[str]) -> Dict[str, Any]:
        statement = str(lemma.get("formal_statement_latex", ""))
        assumptions = " ".join(map(str, lemma.get("assumptions", [])))
        conclusion = str(lemma.get("conclusion", ""))
        text = " ".join((statement, assumptions, conclusion))
        issues: List[str] = []

        declared = set(re.findall(r"(?i)(?:let|for all|forall)\s+\\?([A-Za-z][A-Za-z0-9_]*)", text))
        declared.update(re.findall(r"\\(?:int|sum|prod)[^d]{0,180}d([A-Za-z])\b", statement))
        commands = set(re.findall(r"\\([A-Za-z]+)", text))
        bare = set(re.findall(r"(?<![\\A-Za-z])([A-Z]|[a-z]_[A-Za-z0-9]+)(?![A-Za-z])", text))
        undefined = sorted(x for x in commands | bare if x.lower() not in self.BUILTINS and x not in declared)
        if undefined:
            issues.append("undefined_symbols:" + ",".join(undefined[:12]))

        # A variable bound by an integral cannot simultaneously remain universally free.
        for var in re.findall(r"\\int[^\n]{0,250}?d([A-Za-z])\b", statement):
            if re.search(rf"(?i)for all\s+{re.escape(var)}\b", statement):
                issues.append(f"bound_variable_reused_as_free:{var}")

        known_claims = set(map(str, claim_ids))
        missing = sorted(set(map(str, lemma.get("depends_on_claims", []))) - known_claims)
        if missing:
            issues.append("missing_claim_dependencies:" + ",".join(missing))
        if not lemma.get("assumptions"):
            issues.append("missing_assumptions")
        if not conclusion:
            issues.append("missing_conclusion")
        if re.search(r"(?i)if\b", statement) and not re.search(r"(?i)(then|\\to|\\Rightarrow|implies)", statement):
            issues.append("malformed_conditional")
        return {"valid": not issues, "issues": issues, "declared_symbols": sorted(declared), "undefined_symbols": undefined}


def write_verification_record(path: Path, result: FormalVerificationResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
