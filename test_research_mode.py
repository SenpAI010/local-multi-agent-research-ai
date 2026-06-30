from pathlib import Path
from tempfile import TemporaryDirectory
import json

from agent_system.research import ResearchProjectManager
from agent_system.research.manager import slugify


def test_long_research_problem_gets_windows_safe_stable_slug():
    text = "Untersuche " + "eine sehr lange mathematische Forschungsfrage " * 20
    first = slugify(text)
    assert len(first) <= 64
    assert first == slugify(text)


def test_research_restart_resets_stale_autopilot_state():
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")
        project = Path(tmp) / "research" / "riemann_hypothesis"
        stale = manager._fresh_autopilot_state()
        stale["completed_actions"] = ["generate_new_lemma:A001", "verify_claims"]
        stale["exhausted_actions"] = ["generate_new_lemma:A001"]
        (project / "autopilot_state.json").write_text(json.dumps(stale), encoding="utf-8")
        manager.start("Riemannsche Vermutung mit neuem Forschungsauftrag")
        reset = json.loads((project / "autopilot_state.json").read_text(encoding="utf-8"))
        assert reset["completed_actions"] == []
        assert reset["exhausted_actions"] == []
        assert reset["completed_steps"] == 0


def test_targeted_lemma_generation_uses_requested_approach():
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")
        manager.next_step("A003")
        project = Path(tmp) / "research" / "riemann_hypothesis"
        lemmas = json.loads((project / "formal_lemmas.json").read_text(encoding="utf-8"))
        assert lemmas[-1]["approach_id"] == "A003"


REQUIRED_FILES = [
    "main.tex",
    "references.bib",
    "approaches.json",
    "approaches.csv",
    "status.json",
    "checkpoint.json",
    "trace.jsonl",
    "claims.json",
    "sources.json",
]


REQUIRED_DIRS = [
    "experiments",
    "figures",
    "code",
    "notes",
    "failed_approaches",
    "proof_attempts",
]


class FakeProofClient:
    def __init__(self):
        self.model = "fake-reasoning"
        self.enable_tools = True

    def set_model(self, model):
        self.model = model

    def set_tools_enabled(self, enabled):
        self.enable_tools = enabled

    def chat_with_tools(self, messages, system=None, **kwargs):
        text = messages[-1]["content"]
        if "Critique this controlled proof attempt" in text:
            return json.dumps({
                "validity": "partial",
                "issues": ["The implication is only sketched.", "No source proves the new lemma."],
                "required_fixes": ["Mark lemma as open.", "Search for counterarguments."],
                "rank_delta": 1,
                "summary": "Critique: partial, hidden assumptions remain.",
            }), None
        return json.dumps({
            "summary": "A guarded proof step isolates a conditional positivity lemma.",
            "step_type": "proof_attempt",
            "new_definitions": ["test function with compact support"],
            "new_lemmas": [{
                "title": "Open positivity lemma",
                "statement": "If the selected kernel is positive for all admissible tests, then this approach gains evidence.",
                "status": "open_gap",
            }],
            "proof_steps": [
                "Translate the target implication into a positivity condition.",
                "Identify the unproved positivity requirement.",
            ],
            "new_claims": [{
                "text": "The current route reduces progress to an unverified positivity lemma.",
                "type": "heuristic",
                "status": "unverified",
                "risk": "medium",
                "source_ids": [],
                "depends_on": [],
                "counterarguments": ["The positivity condition may be as hard as the original problem."],
            }],
            "open_gaps": ["The positivity lemma is not proved."],
            "counterarguments": ["This may only restate an equivalent criterion."],
            "suggested_experiments": ["Test the kernel numerically on small admissible functions."],
            "rank_update_suggestion": {"rank": 2, "reason": "Interesting but central lemma is open."},
            "latex_patch": "\\paragraph{Controlled attempt.} We isolate an open positivity lemma; this is not a proof.",
        }), None


def test_research_workspace_lifecycle() -> None:
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))

        started = manager.start("Riemannsche Vermutung")
        assert "Research-Projekt gestartet" in started

        project_dir = Path(tmp) / "research" / "riemann_hypothesis"
        assert project_dir.exists()
        for name in REQUIRED_FILES:
            assert (project_dir / name).exists(), name
        for name in REQUIRED_DIRS:
            assert (project_dir / name).is_dir(), name

        latex = manager.show_latex()
        assert "\\section{Problem Statement}" in latex
        assert "\\section{Ranked Approach Table}" in latex
        assert "does not claim a solution" in latex

        table = manager.table()
        assert "A001" in table
        assert "Equivalent formulations" in table

        step = manager.next_step()
        assert "Research-Step 1" in step
        assert "unverified" in manager.show_latex()

        literature = manager.literature_retrieve()
        assert "LiteratureRetriever" in literature
        assert "sources.json" not in literature

        verified = manager.verify_claims()
        assert "ClaimVerifier" in verified

        added = manager.add_idea("Teste eine Spurformel-Variante als Heuristik.")
        assert "A004" in added
        assert "A004" in manager.table()

        ranked = manager.rank("A002", 4, "Numerische Evidenz reicht nicht als Beweis.")
        assert "Rank 4" in ranked

        manager.mark_failed("A001", "Literaturstruktur-Test abgeschlossen; fuer Experiment-Test wechseln.")
        manager.rank("A002", 1, "Priorisiere Experiment-Test.")
        experiment_step = manager.next_step()
        assert "Experiment-Artefakte" in experiment_step
        assert list((project_dir / "experiments").glob("experiment_*.json"))
        assert list((project_dir / "figures").glob("experiment_*.png"))
        assert "not a proof" in manager.show_latex()

        auto = manager.auto(2)
        assert "Research-Step" in auto or "Stagnation" in auto

        failed = manager.mark_failed("A004", "Fuehrt ohne neues Lemma in eine Sackgasse.")
        assert "gescheitert" in failed
        assert "A004" in manager.table()

        checkpoint = manager.checkpoint()
        assert "last_completed_step" in checkpoint

        trace = manager.trace()
        assert "research_start" in trace
        assert "mark_failed" in trace

        resumed = manager.resume()
        assert "Research wiederaufgenommen" in resumed


def test_llm_proof_attempt_runner_acceptance() -> None:
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp), proof_client=FakeProofClient(), reasoning_model="fake-reasoning")
        manager.start("Riemannsche Vermutung")
        out = manager.auto(3)
        assert "LLMProofAttemptRunner" in out

        project_dir = Path(tmp) / "research" / "riemann_hypothesis"
        latex = (project_dir / "main.tex").read_text(encoding="utf-8")
        proof_tex = "\n".join(path.read_text(encoding="utf-8") for path in (project_dir / "proof_attempts").glob("step_*.tex"))
        claims = json.loads((project_dir / "claims.json").read_text(encoding="utf-8"))
        trace = (project_dir / "trace.jsonl").read_text(encoding="utf-8")
        checkpoint = json.loads((project_dir / "checkpoint.json").read_text(encoding="utf-8"))

        assert "\\input{proof_attempts/step_0001.tex}" in latex
        assert "Controlled attempt" in proof_tex
        assert "this is not a proof" in proof_tex
        assert "Riemann hypothesis is proved" not in latex
        assert "riemannsche vermutung ist bewiesen" not in latex.lower()
        assert any("positivity lemma" in c["text"].lower() for c in claims)
        assert all("status" in c and "risk" in c and "formal_status" in c for c in claims)
        assert "proof_attempt" in trace
        assert "claim_verify" in trace
        assert "critique_pass" in trace
        assert "latex_patch_validated" in trace
        assert checkpoint.get("next_planned_step")
        assert checkpoint.get("stagnation_status") in {"none", "risk_detected"}


def test_start_new_epoch_with_no_viable_target_pauses() -> None:
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Epoch guard test")
        project_dir = Path(tmp) / "research" / "epoch_guard_test"
        approaches = json.loads((project_dir / "approaches.json").read_text(encoding="utf-8"))
        for approach in approaches:
            approach["status"] = "stagnation_limited"
            approach["rank"] = 6
        (project_dir / "approaches.json").write_text(json.dumps(approaches), encoding="utf-8")

        result = manager._execute_autopilot_action(
            project_dir,
            {"action": "start_new_epoch", "target": "", "reason": "regression"},
        )

        checkpoint = json.loads((project_dir / "checkpoint.json").read_text(encoding="utf-8"))
        assert "Autopilot pausiert" in result
        assert checkpoint["stagnation_status"] == "autopilot_paused_no_high_value_action"


def test_latex_patch_blocks_file_input_and_verbatim_escape() -> None:
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        patch, issues = manager._validate_latex_patch(
            r"\paragraph{Bad.}\input{../../secret}\end{verbatim}\write18{whoami}",
            {"new_lemmas": []},
        )
        assert "unsafe_latex_commands_escaped" in " ".join(issues)
        assert r"\input" not in patch
        escaped = manager._safe_verbatim(r'{"x":"\end{verbatim}\input{secret}"}')
        assert r"\end{verbatim}" not in escaped


def test_quick_review_reads_workspace_and_writes_notes() -> None:
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")
        out = manager.quick_review()
        project = Path(tmp) / "research" / "riemann_hypothesis"
        reviews = list((project / "notes").glob("quick_review_*.md"))
        status = json.loads((project / "status.json").read_text(encoding="utf-8"))
        assert "Quick Review geschrieben" in out
        assert reviews
        assert "quick_review_completed" == status["current_status"]
        assert "Keine aktuell Lean-verifizierten" in reviews[-1].read_text(encoding="utf-8")


if __name__ == "__main__":
    test_research_workspace_lifecycle()
    test_llm_proof_attempt_runner_acceptance()
    test_start_new_epoch_with_no_viable_target_pauses()
    test_latex_patch_blocks_file_input_and_verbatim_escape()
    test_quick_review_reads_workspace_and_writes_notes()
    print("research mode tests passed")
