import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from agent_system.research.formal_verifier import Lean4Verifier, LemmaIntegrityChecker, FormalVerificationResult
from agent_system.research.manager import ResearchProjectManager


def _runner(returncode=0, stderr=""):
    def run(*_args, **_kwargs):
        return SimpleNamespace(returncode=returncode, stdout="compiled" if returncode == 0 else "", stderr=stderr)
    return run


def _valid_lemma(code="theorem identity (n : Nat) : n = n := by rfl"):
    return {
        "lemma_id": "L001",
        "approach_id": "A001",
        "title": "Identity",
        "formal_statement_latex": "Let n be a natural number. If n = n then n = n.",
        "assumptions": ["n is a natural number"],
        "conclusion": "n = n",
        "depends_on_claims": [],
        "proof_status": "open",
        "source_ids": [],
        "risk": "medium",
        "lean_code": code,
    }


def test_lean_success_is_only_formal_status_gate():
    with tempfile.TemporaryDirectory() as tmp:
        verifier = Lean4Verifier(runner=_runner(0))
        manager = ResearchProjectManager(Path(tmp), formal_verifier=verifier)
        manager.start("Finite identity test")
        project = Path(tmp) / "research" / "finite_identity_test"
        (project / "formal_lemmas.json").write_text(json.dumps([_valid_lemma()]), encoding="utf-8")
        output = manager.verify_lemma_formally("L001")
        saved = json.loads((project / "formal_lemmas.json").read_text(encoding="utf-8"))[0]
        assert "proof_status=formally_verified" in output
        assert saved["formal_verification"]["verified"] is True
        assert saved["proof_status"] == "formally_verified"


def test_subtle_type_error_never_becomes_verified():
    with tempfile.TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp), formal_verifier=Lean4Verifier(runner=_runner(1, "application type mismatch")))
        manager.start("Finite identity test")
        project = Path(tmp) / "research" / "finite_identity_test"
        lemma = _valid_lemma("theorem bad (n : Nat) : n + 1 = True := by rfl")
        lemma["proof_status"] = "formally_verified"  # hostile model output
        (project / "formal_lemmas.json").write_text(json.dumps([lemma]), encoding="utf-8")
        manager.verify_lemma_formally("L001")
        saved = json.loads((project / "formal_lemmas.json").read_text(encoding="utf-8"))[0]
        assert saved["proof_status"] == "open"
        assert saved["formal_verification"]["status"] == "compile_failed"


def test_tampered_artifact_invalidates_formal_status_on_next_save():
    with tempfile.TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp), formal_verifier=Lean4Verifier(runner=_runner(0)))
        manager.start("Finite identity test")
        project = Path(tmp) / "research" / "finite_identity_test"
        (project / "formal_lemmas.json").write_text(json.dumps([_valid_lemma()]), encoding="utf-8")
        manager.verify_lemma_formally("L001")
        lemmas = json.loads((project / "formal_lemmas.json").read_text(encoding="utf-8"))
        artifact = Path(lemmas[0]["formal_verification"]["artifact_path"])
        artifact.write_text("theorem changed : True := by trivial", encoding="utf-8")
        manager._save_all(project, formal_lemmas=lemmas)
        saved = json.loads((project / "formal_lemmas.json").read_text(encoding="utf-8"))[0]
        assert saved["proof_status"] == "open"
        assert saved["formal_verification"]["status"] == "stale_or_invalid_artifact"


def test_sorry_axiom_and_admit_are_rejected_even_if_compiler_accepts():
    for placeholder in ("by sorry", "by admit", "axiom magic : False"):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Bad.lean"
            path.write_text(f"theorem bad : True := {placeholder}\n", encoding="utf-8")
            result = Lean4Verifier(runner=_runner(0)).verify(path)
            assert result.verified is False
            assert result.status == "rejected_placeholder"


def test_block_comment_cannot_hide_eval():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "Eval.lean"
        path.write_text("import Mathlib\n/- harmless looking comment -/ #eval 1 + 1\n", encoding="utf-8")
        result = Lean4Verifier(runner=_runner(0)).verify(path)
        assert result.verified is False
        assert result.status == "rejected_unsafe_lean_artifact"
        assert any("#eval" in issue for issue in result.issues)


def test_integrity_checker_finds_undefined_symbol_dependency_and_bound_reuse():
    checker = LemmaIntegrityChecker()
    lemma = {
        "formal_statement_latex": r"Let f be real. If \int_0^1 \Phi(t) dt > 0 for all t then Q(t) > 0.",
        "assumptions": ["f is real"],
        "conclusion": "Q(t) > 0",
        "depends_on_claims": ["C999"],
    }
    result = checker.check(lemma, ["C001"])
    joined = " ".join(result["issues"])
    assert result["valid"] is False
    assert "undefined_symbols" in joined
    assert "missing_claim_dependencies:C999" in joined
    assert "bound_variable_reused_as_free:t" in joined


def test_source_id_without_traceable_entailment_is_not_support():
    with tempfile.TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Source entailment test")
        project = Path(tmp) / "research" / "source_entailment_test"
        sources = [{
            "source_id": "S001", "title": "Arithmetic", "summary": "Every even integer is divisible by two.",
            "relevance": "elementary arithmetic", "trust_level": "trusted_primary",
        }]
        claims = [{
            "claim_id": "C001", "text": "Every prime number is odd.", "type": "theorem",
            "status": "source_supported", "source_ids": ["S001"], "counterarguments": [], "risk": "low",
        }]
        (project / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
        (project / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
        manager.verify_claims()
        saved = json.loads((project / "claims.json").read_text(encoding="utf-8"))[0]
        assert saved["status"] == "unverified"
        assert saved["source_verification"]["supported"] is False


def test_traceable_matching_evidence_can_support_known_theorem():
    with tempfile.TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Source entailment test")
        project = Path(tmp) / "research" / "source_entailment_test"
        evidence = "Every even integer is divisible by two."
        sources = [{"source_id": "S001", "title": "Arithmetic", "summary": evidence, "relevance": "", "trust_level": "trusted_primary"}]
        claims = [{
            "claim_id": "C001", "text": evidence, "type": "known_theorem", "status": "unverified",
            "source_ids": ["S001"], "source_evidence": [{"source_id": "S001", "quote": evidence}],
            "counterarguments": [], "risk": "medium",
        }]
        (project / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
        (project / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
        manager.verify_claims()
        saved = json.loads((project / "claims.json").read_text(encoding="utf-8"))[0]
        assert saved["status"] == "source_supported"


def test_model_roles_cannot_collapse_to_same_model():
    manager = ResearchProjectManager(Path(tempfile.mkdtemp()), research_step_model="same", research_critic_model="same", research_claim_verifier_model="same")
    models = manager.model_config
    assert models["research_step_model"] != models["research_critic_model"]
    assert models["research_step_model"] != models["research_claim_verifier_model"]


class _RepairVerifier:
    def __init__(self):
        self.calls = 0

    def verify(self, artifact, cwd=None):
        self.calls += 1
        content = Path(artifact).read_text(encoding="utf-8")
        import hashlib
        digest = hashlib.sha256(content.encode()).hexdigest()
        ok = self.calls >= 2
        return FormalVerificationResult(ok, "lean4", "verified" if ok else "compile_failed", str(Path(artifact).resolve()), digest, ["lean", str(artifact)], 0 if ok else 1, "" if not ok else "compiled", "type mismatch" if not ok else "", [] if ok else ["lean_compile_failed"])


class _ResearchClient:
    def __init__(self, reject_second_review=False):
        self.model = "base"
        self.enable_tools = True
        self.timeout = 90
        self.formalizer_calls = 0
        self.review_calls = 0
        self.reject_second_review = reject_second_review

    def set_model(self, model):
        self.model = model

    def set_tools_enabled(self, enabled):
        self.enable_tools = enabled

    def chat_with_tools(self, messages, **_kwargs):
        if "coder" in self.model:
            self.formalizer_calls += 1
            code = "theorem first (n : Nat) : n = n := by rfl" if self.formalizer_calls == 1 else "theorem repaired (n : Nat) : n = n := by rfl"
            return json.dumps({"lean_code": code, "mapping_notes": "exact identity", "assumptions_preserved": True}), None
        if self.model in {"qwen3:30b", "deepseek-r1:70b"}:
            self.review_calls += 1
            verdict = "reject" if self.reject_second_review and self.review_calls == 2 else "accept"
            return json.dumps({"verdict": verdict, "issues": [], "hidden_assumptions": [], "counterexample_strategy": "none", "confidence": 0.9}), None
        return json.dumps({"verdict": "unknown", "closest_sources": [], "reason": "no corpus", "confidence": 0.2}), None


def test_formalizer_repairs_failed_lean_attempt_then_verifies():
    with tempfile.TemporaryDirectory() as tmp:
        verifier = _RepairVerifier()
        client = _ResearchClient()
        manager = ResearchProjectManager(Path(tmp), proof_client=client, formal_verifier=verifier)
        manager.start("Finite identity test")
        project = Path(tmp) / "research" / "finite_identity_test"
        (project / "formal_lemmas.json").write_text(json.dumps([_valid_lemma("")]), encoding="utf-8")
        output = manager.formalize_and_verify_lemma("L001", 3)
        saved = json.loads((project / "formal_lemmas.json").read_text(encoding="utf-8"))[0]
        assert "durch Lean formal verifiziert" in output
        assert verifier.calls == 2
        assert saved["proof_status"] == "formally_verified"
        assert [x["status"] for x in saved["formalization_history"]] == ["compile_failed", "verified"]


def test_peer_review_requires_unanimous_independent_acceptance():
    with tempfile.TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp), proof_client=_ResearchClient(reject_second_review=True), formal_verifier=Lean4Verifier(runner=_runner(0)))
        manager.start("Finite identity test")
        project = Path(tmp) / "research" / "finite_identity_test"
        (project / "formal_lemmas.json").write_text(json.dumps([_valid_lemma()]), encoding="utf-8")
        manager.verify_lemma_formally("L001")
        report = json.loads(manager.peer_review_lemma("L001"))
        saved = json.loads((project / "formal_lemmas.json").read_text(encoding="utf-8"))[0]
        assert report["accepted_by_all"] is False
        assert saved["scientific_status"] == "provisional"


def test_novelty_without_literature_is_never_claimed():
    with tempfile.TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Finite identity test")
        project = Path(tmp) / "research" / "finite_identity_test"
        (project / "formal_lemmas.json").write_text(json.dumps([_valid_lemma()]), encoding="utf-8")
        (project / "sources.json").write_text("[]", encoding="utf-8")
        report = json.loads(manager.assess_lemma_novelty("L001"))
        assert report["verdict"] == "unknown"
        assert "cannot be assessed" in report["reason"]


def test_latex_backslashes_do_not_emit_python_syntax_warning():
    import warnings
    manager = ResearchProjectManager(Path(tempfile.mkdtemp()))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        data, repaired = manager._loads_json_or_python_dict(r"{'latex_patch':'\int_0^1 f(x) dx'}")
    assert repaired is True
    assert data["latex_patch"].startswith("\\int")
    assert not [w for w in caught if issubclass(w.category, SyntaxWarning)]


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("formal verification adversarial tests passed")
