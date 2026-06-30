import json
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_system.research import ResearchProjectManager


def test_placeholder_tautology_and_corrupt_latex_fail_lemma_admission():
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        active = {"id": "A003"}
        raw = {
            "title": "Placeholder",
            "formal_statement_latex": "Let f be related to the Riemann zeta function. If certain conditions hold, then ... ¿ 0.",
            "assumptions": ["Objects and domain specified", "Condition is checkable"],
            "conclusion": "Concrete implication for RH",
            "proof_status": "open", "testability": "high", "possible_counterexample_search": "check", "source_ids": [], "risk": "high",
        }
        lemma = manager._guard_formal_lemma(raw, active, 1)
        lemma["integrity_check"] = manager.lemma_integrity_checker.check(lemma, [])
        check = manager._lemma_admission_check(lemma, [])
        assert check["accepted"] is False
        reasons = " ".join(check["reasons"])
        assert "placeholder_language" in reasons
        assert "ellipsis_or_incomplete_statement" in reasons
        assert "corrupted_math_character" in reasons


def test_near_duplicate_lemma_is_rejected():
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        base = {"lemma_id": "L001", "formal_statement_latex": "For every real x greater than zero, x squared is nonnegative.", "conclusion": "x squared is nonnegative"}
        candidate = {
            "formal_statement_latex": "For every real x greater than zero, x squared is nonnegative.",
            "assumptions": ["x is a real number", "x is greater than zero"], "conclusion": "x squared is nonnegative",
            "tautology_status": "none", "circularity_status": "none", "integrity_check": {"issues": []},
        }
        check = manager._lemma_admission_check(candidate, [base])
        assert check["accepted"] is False
        assert any(reason.startswith("near_duplicate:L001") for reason in check["reasons"])


def test_irrelevant_web_source_is_rejected_before_registry():
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")
        project = Path(tmp) / "research" / "riemann_hypothesis"
        sources = json.loads((project / "sources.json").read_text(encoding="utf-8"))
        bad = {"title": "CKM angle in particle physics", "authors": "A. Physicist", "year": "2025", "url": "https://arxiv.org/abs/1", "summary": "A particle physics measurement.", "retrieval_mode": "web_arxiv"}
        assert manager._integrate_sources(project, [bad], sources) == 0
        rejected = json.loads((project / "rejected_sources.json").read_text(encoding="utf-8"))
        assert "topic_mismatch:riemann_hypothesis" in rejected[-1]["reasons"]


class BadJsonClient:
    model = "bad-json"
    enable_tools = True

    def set_model(self, model):
        self.model = model

    def set_tools_enabled(self, enabled):
        self.enable_tools = enabled

    def chat_with_tools(self, *args, **kwargs):
        return "this is not json at all", None


class FinalityClient(BadJsonClient):
    def chat_with_tools(self, messages, *args, **kwargs):
        if "Critique this controlled" in messages[-1]["content"]:
            return json.dumps({
                "validity": "hallucinated",
                "issues": ["Claims final proof"],
                "required_fixes": ["Remove finality"],
                "rank_delta": 2,
                "summary": "Hallucinated final proof wording detected.",
            }), None
        return json.dumps({
            "summary": "Bad finality test",
            "step_type": "proof_attempt",
            "new_definitions": [],
            "new_lemmas": [],
            "proof_steps": ["We prove the Riemann Hypothesis."],
            "new_claims": [{
                "text": "We prove the Riemann Hypothesis.",
                "type": "theorem",
                "status": "formally_verified",
                "risk": "low",
                "source_ids": [],
                "counterarguments": [],
            }],
            "open_gaps": [],
            "counterarguments": [],
            "suggested_experiments": [],
            "rank_update_suggestion": {"rank": 1, "reason": "bad"},
            "latex_patch": "We prove the Riemann Hypothesis. Therefore RH is true.",
        }), None


class RepairableJsonClient(BadJsonClient):
    def chat_with_tools(self, messages, *args, **kwargs):
        return """```json
{'summary':'Repairable step','step_type':'lemma_generation','new_lemmas':[{'title':'Open L','statement':'A small open implication remains','status':'open_gap',},],'proof_steps':['Isolate one implication',],'new_claims':[{'text':'This is a guarded heuristic only','type':'heuristic','status':'unverified','risk':'medium','source_ids':[],},],'open_gaps':['Formal proof missing',],'counterarguments':['May be equivalent to original problem',],'rank_update_suggestion':{'rank':3,'reason':'open gap',},'latex_patch':'\\\\paragraph{Attempt.} Open gap only.',}
```""", None


def run_case(client, label):
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp), proof_client=client, reasoning_model="x")
        print(f"=== {label} ===")
        print(manager.start("Riemannsche Vermutung"))
        print(manager.auto(1))
        project = Path(tmp) / "research" / "riemann_hypothesis"
        claims = json.loads((project / "claims.json").read_text(encoding="utf-8"))
        trace = (project / "trace.jsonl").read_text(encoding="utf-8")
        proof_tex = sorted((project / "proof_attempts").glob("step_*.tex"))[0].read_text(encoding="utf-8")
        checkpoint = json.loads((project / "checkpoint.json").read_text(encoding="utf-8"))
        print("CHECKPOINT", json.dumps({
            "last_completed_step": checkpoint.get("last_completed_step"),
            "active_approach_id": checkpoint.get("active_approach_id"),
            "stagnation_status": checkpoint.get("stagnation_status"),
            "next_planned_step": checkpoint.get("next_planned_step"),
        }, indent=2, ensure_ascii=False))
        print("CLAIMS", json.dumps(claims[-3:], indent=2, ensure_ascii=False))
        print("TRACE", trace)
        print("PROOF_TEX", proof_tex[:2200])
        if label == "FINALITY":
            assert "We prove the Riemann Hypothesis" not in proof_tex
            assert "therefore RH is true" not in proof_tex
            assert "HallucinationGuard" in proof_tex


if __name__ == "__main__":
    run_case(RepairableJsonClient(), "REPAIRABLE_JSON")
    run_case(BadJsonClient(), "BAD_JSON")
    run_case(FinalityClient(), "FINALITY")
