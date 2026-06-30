from pathlib import Path
from tempfile import TemporaryDirectory
import json

from main_phase3 import is_internal_autopilot_action, is_research_auto_command
from agent_system.research import ResearchProjectManager


def test_research_auto_does_not_catch_autopilot_commands():
    assert is_research_auto_command("/research_auto")
    assert is_research_auto_command("/research_auto 3")
    assert not is_research_auto_command("/research_autopilot_plan")
    assert not is_research_auto_command("/research_autopilot_next")
    assert not is_research_auto_command("/research_autopilot_report")


def test_internal_autopilot_actions_are_detected():
    assert is_internal_autopilot_action("retrieve_literature")
    assert is_internal_autopilot_action("refine_existing_lemma")
    assert is_internal_autopilot_action("disprove_lemma")
    assert not is_internal_autopilot_action("hi")


def test_autopilot_plan_next_report():
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")

        plan = manager.autopilot_plan()
        assert "Usage: /research_auto" not in plan
        assert "action" in plan

        result = manager.autopilot_next()
        event = json.loads(result)
        assert event["action"]
        assert event["step"] == 1

        report = manager.autopilot_report()
        assert "Usage: /research_auto" not in report
        assert "research_auto" not in report
        assert "action" in report


def test_autopilot_marks_duplicate_once_then_moves_to_best_lemma():
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")
        project = Path(tmp) / "research" / "riemann_hypothesis"

        approaches = json.loads((project / "approaches.json").read_text(encoding="utf-8"))
        for item in approaches:
            if item["id"] == "A003":
                item["status"] = "stagnation_limited"
        status = json.loads((project / "status.json").read_text(encoding="utf-8"))
        status.update({"active_approach_id": "A003", "focused_approach_id": "A003"})
        checkpoint = json.loads((project / "checkpoint.json").read_text(encoding="utf-8"))
        checkpoint.update({"active_approach_id": "A003", "stagnation_status": "limit_reached:repetition"})
        lemmas = [
            {
                "lemma_id": "L008",
                "approach_id": "A003",
                "title": "Duplicate positivity idea",
                "formal_statement_latex": "A repeated positivity idea.",
                "assumptions": ["positivity"],
                "conclusion": "conditional implication",
                "proof_status": "open",
                "risk": "high",
                "lemma_quality_score": 2,
            },
            {
                "lemma_id": "L010",
                "approach_id": "A003",
                "title": "Duplicate positivity idea",
                "formal_statement_latex": "A repeated positivity idea.",
                "assumptions": ["positivity"],
                "conclusion": "conditional implication",
                "proof_status": "open",
                "risk": "high",
                "lemma_quality_score": 2,
            },
            {
                "lemma_id": "L011",
                "approach_id": "A003",
                "title": "Positivity kernel candidate",
                "formal_statement_latex": "Let K be a positive definite kernel on a Hilbert function space associated with the explicit formula for zeta.",
                "assumptions": ["K is an explicit-formula kernel", "K is positive definite on a Hilbert function space"],
                "conclusion": "The route gives a conditional implication toward critical-line zeros.",
                "related_known_criteria": ["Weil criterion"],
                "proof_status": "open",
                "testability": "high",
                "possible_counterexample_search": "Search for test functions where positive definiteness fails.",
                "source_ids": [],
                "risk": "medium",
                "lemma_quality_score": 4,
                "source_grounding_score": 1,
                "testability_score": 5,
                "novelty_score": 4,
                "tautology_status": "none",
                "circularity_status": "none",
            },
        ]
        (project / "approaches.json").write_text(json.dumps(approaches, indent=2), encoding="utf-8")
        (project / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        (project / "checkpoint.json").write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
        (project / "formal_lemmas.json").write_text(json.dumps(lemmas, indent=2), encoding="utf-8")
        sources = manager._curated_sources("Riemannsche Vermutung")
        for idx, source in enumerate(sources, start=1):
            source["source_id"] = f"S{idx:03d}"
        (project / "sources.json").write_text(json.dumps(sources, indent=2), encoding="utf-8")

        first_plan = json.loads(manager.autopilot_plan())
        assert first_plan["action"] == "mark_stagnated"
        assert "L008" in first_plan["target"]
        assert "L010" in first_plan["target"]

        first_next = json.loads(manager.autopilot_next())
        assert first_next["action"] == "mark_stagnated"
        state = json.loads((project / "autopilot_state.json").read_text(encoding="utf-8"))
        assert "mark_stagnated:L008" in state["completed_actions"]
        assert "mark_stagnated:L010" in state["completed_actions"]

        second_plan = json.loads(manager.autopilot_plan())
        assert second_plan["action"] in {"compare_with_known_criterion", "retrieve_literature"}
        assert second_plan.get("target") == "L011"


def test_autopilot_exhausts_zero_result_literature_once():
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")
        project = Path(tmp) / "research" / "riemann_hypothesis"

        approaches = json.loads((project / "approaches.json").read_text(encoding="utf-8"))
        for item in approaches:
            if item["id"] == "A003":
                item["status"] = "stagnation_limited"
        status = json.loads((project / "status.json").read_text(encoding="utf-8"))
        status.update({"active_approach_id": "A003", "focused_approach_id": "A003"})
        checkpoint = json.loads((project / "checkpoint.json").read_text(encoding="utf-8"))
        checkpoint.update({"active_approach_id": "A003", "stagnation_status": "limit_reached:repetition"})
        lemmas = [{
            "lemma_id": "L011",
            "approach_id": "A003",
            "title": "Positivity kernel candidate",
            "formal_statement_latex": "Let K be a positive definite kernel on a Hilbert function space associated with the explicit formula for zeta.",
            "assumptions": ["K is an explicit-formula kernel", "K is positive definite on a Hilbert function space"],
            "conclusion": "The route gives a conditional implication toward critical-line zeros.",
            "related_known_criteria": ["Weil criterion"],
            "compared_criteria": ["Weil criterion"],
            "proof_status": "open",
            "testability": "high",
            "possible_counterexample_search": "Search for test functions where positive definiteness fails.",
            "source_ids": [],
            "risk": "medium",
            "lemma_quality_score": 4,
            "source_grounding_score": 1,
            "testability_score": 5,
            "novelty_score": 4,
            "tautology_status": "none",
            "circularity_status": "none",
        }]
        (project / "approaches.json").write_text(json.dumps(approaches, indent=2), encoding="utf-8")
        (project / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        (project / "checkpoint.json").write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
        (project / "formal_lemmas.json").write_text(json.dumps(lemmas, indent=2), encoding="utf-8")
        sources = manager._curated_sources("Riemannsche Vermutung")
        for idx, source in enumerate(sources, start=1):
            source["source_id"] = f"S{idx:03d}"
        (project / "sources.json").write_text(json.dumps(sources, indent=2), encoding="utf-8")

        first_plan = json.loads(manager.autopilot_plan())
        assert first_plan["action"] == "retrieve_literature"
        first_next = json.loads(manager.autopilot_next())
        assert first_next["action"] == "retrieve_literature"
        assert not first_next["progress"]["progress_made"]

        state = json.loads((project / "autopilot_state.json").read_text(encoding="utf-8"))
        exhausted = "\n".join(state["exhausted_actions"])
        assert "retrieve_literature:L011:Weil criterion Riemann hypothesis positivity" in exhausted

        second_plan = json.loads(manager.autopilot_plan())
        assert second_plan["action"] != "retrieve_literature"
        assert second_plan["action"] in {"ask_enable_web_research", "refine_existing_lemma", "disprove_lemma", "switch_approach"}


def test_autopilot_asks_enable_web_once_and_stops():
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")
        project = Path(tmp) / "research" / "riemann_hypothesis"

        approaches = json.loads((project / "approaches.json").read_text(encoding="utf-8"))
        for item in approaches:
            if item["id"] == "A003":
                item["status"] = "stagnation_limited"
        status = json.loads((project / "status.json").read_text(encoding="utf-8"))
        status.update({"active_approach_id": "A003", "focused_approach_id": "A003"})
        checkpoint = json.loads((project / "checkpoint.json").read_text(encoding="utf-8"))
        checkpoint.update({"active_approach_id": "A003", "stagnation_status": "limit_reached:repetition"})
        lemmas = [{
            "lemma_id": "L011",
            "approach_id": "A003",
            "title": "Positivity kernel candidate",
            "formal_statement_latex": "Let K be a positive definite kernel on a Hilbert function space associated with the explicit formula for zeta.",
            "assumptions": ["K is an explicit-formula kernel", "K is positive definite on a Hilbert function space"],
            "conclusion": "The route gives a conditional implication toward critical-line zeros.",
            "related_known_criteria": ["Weil criterion"],
            "compared_criteria": ["Weil criterion"],
            "proof_status": "open",
            "testability": "high",
            "possible_counterexample_search": "Search for test functions where positive definiteness fails.",
            "source_ids": [],
            "risk": "medium",
            "lemma_quality_score": 4,
            "source_grounding_score": 1,
            "testability_score": 5,
            "novelty_score": 4,
            "tautology_status": "none",
            "circularity_status": "none",
        }]
        sources = manager._curated_sources("Riemannsche Vermutung")
        for idx, source in enumerate(sources, start=1):
            source["source_id"] = f"S{idx:03d}"
        exhausted_key = "retrieve_literature:L011:Weil criterion Riemann hypothesis positivity"
        state = {
            "running": False,
            "max_steps": 0,
            "completed_steps": 0,
            "last_plan": None,
            "last_result": None,
            "report": [],
            "completed_actions": [exhausted_key],
            "exhausted_actions": [exhausted_key],
            "failed_actions": [],
            "action_attempt_counts": {exhausted_key: 1},
            "waiting_for_user": None,
            "status": "idle",
        }
        (project / "approaches.json").write_text(json.dumps(approaches, indent=2), encoding="utf-8")
        (project / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        (project / "checkpoint.json").write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
        (project / "formal_lemmas.json").write_text(json.dumps(lemmas, indent=2), encoding="utf-8")
        (project / "sources.json").write_text(json.dumps(sources, indent=2), encoding="utf-8")
        (project / "autopilot_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

        output = manager.autopilot_start(5)
        assert output.count('"action": "ask_enable_web_research"') == 1
        new_state = json.loads((project / "autopilot_state.json").read_text(encoding="utf-8"))
        assert new_state["status"] == "waiting_for_user_decision"
        assert new_state["running"] is False
        assert new_state["completed_steps"] == 1
        assert new_state["waiting_for_user"]["type"] == "enable_web_or_switch"
        assert "ask_enable_web_research:L011" in new_state["completed_actions"]

        next_plan = json.loads(manager.autopilot_plan())
        assert next_plan["action"] != "ask_enable_web_research"


def test_autopilot_does_not_repeat_exhausted_refine():
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")
        project = Path(tmp) / "research" / "riemann_hypothesis"

        approaches = json.loads((project / "approaches.json").read_text(encoding="utf-8"))
        for item in approaches:
            if item["id"] == "A003":
                item["status"] = "stagnation_limited"
        status = json.loads((project / "status.json").read_text(encoding="utf-8"))
        status.update({"active_approach_id": "A003", "focused_approach_id": "A003"})
        checkpoint = json.loads((project / "checkpoint.json").read_text(encoding="utf-8"))
        checkpoint.update({"active_approach_id": "A003", "stagnation_status": "limit_reached:repetition"})
        lemmas = [{
            "lemma_id": "L011",
            "approach_id": "A003",
            "title": "Vague positivity candidate",
            "formal_statement_latex": "A positivity condition may imply a critical-line conclusion.",
            "assumptions": ["positivity condition"],
            "conclusion": "conditional implication",
            "related_known_criteria": ["Weil criterion"],
            "compared_criteria": ["Weil criterion"],
            "proof_status": "open",
            "testability": "medium",
            "possible_counterexample_search": "Clarify before testing.",
            "source_ids": ["S001"],
            "risk": "high",
            "lemma_quality_score": 4,
            "source_grounding_score": 3,
            "testability_score": 3,
            "novelty_score": 3,
            "tautology_status": "none",
            "circularity_status": "none",
        }]
        state = {
            "running": False,
            "max_steps": 0,
            "completed_steps": 0,
            "last_plan": None,
            "last_result": None,
            "report": [],
            "completed_actions": ["refine_existing_lemma:L011"],
            "exhausted_actions": ["refine_existing_lemma:L011"],
            "failed_actions": [],
            "action_attempt_counts": {"refine_existing_lemma:L011": 1},
            "waiting_for_user": None,
            "status": "idle",
        }
        (project / "approaches.json").write_text(json.dumps(approaches, indent=2), encoding="utf-8")
        (project / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        (project / "checkpoint.json").write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
        (project / "formal_lemmas.json").write_text(json.dumps(lemmas, indent=2), encoding="utf-8")
        (project / "autopilot_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

        plan = json.loads(manager.autopilot_plan())
        assert plan["action"] != "refine_existing_lemma"
        assert plan["action"] in {"retrieve_literature", "disprove_lemma", "switch_approach", "run_experiment", "clean_invalid_domain_noise"}


def test_research_clean_noise_removes_invalid_domain_gaps():
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")
        project = Path(tmp) / "research" / "riemann_hypothesis"
        status = json.loads((project / "status.json").read_text(encoding="utf-8"))
        checkpoint = json.loads((project / "checkpoint.json").read_text(encoding="utf-8"))
        status["known_gaps"] = [
            "Quantum entanglement gap for the Riemann hypothesis.",
            "Current step has no formal proof yet.",
        ]
        status["open_lemmas"] = ["Minecraft unrelated lemma", "Open positivity lemma"]
        checkpoint["active_hypotheses"] = ["Quantum physics side path", "Weil criterion path"]
        (project / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        (project / "checkpoint.json").write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")

        plan = json.loads(manager.autopilot_plan())
        assert plan["action"] == "clean_invalid_domain_noise"
        result = manager.clean_noise()
        assert "bereinigt" in result
        cleaned_status = json.loads((project / "status.json").read_text(encoding="utf-8"))
        cleaned_checkpoint = json.loads((project / "checkpoint.json").read_text(encoding="utf-8"))
        assert all("quantum" not in str(g).lower() for g in cleaned_status["known_gaps"])
        assert all("minecraft" not in str(g).lower() for g in cleaned_status["open_lemmas"])
        assert all("quantum" not in str(g).lower() for g in cleaned_checkpoint["active_hypotheses"])
        assert "Current step has no formal proof yet." in cleaned_status["known_gaps"]


def test_autopilot_exhausts_disprove_then_switches_to_a002():
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")
        project = Path(tmp) / "research" / "riemann_hypothesis"

        approaches = json.loads((project / "approaches.json").read_text(encoding="utf-8"))
        for item in approaches:
            if item["id"] == "A003":
                item["status"] = "stagnation_limited"
            if item["id"] == "A002":
                item["status"] = "open"
                item["rank"] = 3
        status = json.loads((project / "status.json").read_text(encoding="utf-8"))
        status.update({"active_approach_id": "A003", "focused_approach_id": "A003"})
        checkpoint = json.loads((project / "checkpoint.json").read_text(encoding="utf-8"))
        checkpoint.update({"active_approach_id": "A003", "stagnation_status": "limit_reached:repetition"})

        check_text = (
            "Check whether assumptions are stronger than known Weil criterion; "
            "search for cases where positivity/domain conditions fail; "
            "verify that the conclusion is not merely equivalent to RH without a new implication."
        )
        lemmas = [{
            "lemma_id": "L011",
            "approach_id": "A003",
            "title": "Grounded positivity kernel candidate",
            "formal_statement_latex": "Let K be a positive definite kernel on a Hilbert function space associated with the explicit formula for zeta.",
            "assumptions": ["K is an explicit-formula kernel", "K is positive definite on a Hilbert function space"],
            "conclusion": "The route gives a conditional implication toward critical-line zeros.",
            "related_known_criteria": ["Weil criterion"],
            "compared_criteria": ["Weil criterion"],
            "proof_status": "open",
            "testability": "high",
            "possible_counterexample_search": check_text,
            "source_ids": ["S001", "S002"],
            "risk": "medium",
            "lemma_quality_score": 4,
            "source_grounding_score": 4,
            "testability_score": 5,
            "novelty_score": 4,
            "tautology_status": "none",
            "circularity_status": "none",
        }]
        sources = manager._curated_sources("Riemannsche Vermutung")
        while len(sources) < 11:
            source = dict(sources[-1])
            source["bibtex_key"] = f"{source['bibtex_key']}_{len(sources)}"
            source["title"] = f"{source['title']} {len(sources)}"
            sources.append(source)
        for idx, source in enumerate(sources, start=1):
            source["source_id"] = f"S{idx:03d}"

        state = {
            "running": False,
            "max_steps": 0,
            "completed_steps": 0,
            "last_plan": None,
            "last_result": None,
            "report": [],
            "completed_actions": ["refine_existing_lemma:L011"],
            "exhausted_actions": ["refine_existing_lemma:L011"],
            "failed_actions": [],
            "action_attempt_counts": {"refine_existing_lemma:L011": 1},
            "waiting_for_user": None,
            "status": "idle",
        }
        (project / "approaches.json").write_text(json.dumps(approaches, indent=2), encoding="utf-8")
        (project / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        (project / "checkpoint.json").write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
        (project / "formal_lemmas.json").write_text(json.dumps(lemmas, indent=2), encoding="utf-8")
        (project / "sources.json").write_text(json.dumps(sources, indent=2), encoding="utf-8")
        (project / "autopilot_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

        first_plan = json.loads(manager.autopilot_plan())
        assert first_plan["action"] == "disprove_lemma"
        first_next = json.loads(manager.autopilot_next())
        assert first_next["action"] == "disprove_lemma"
        assert not first_next["progress"]["progress_made"]
        new_state = json.loads((project / "autopilot_state.json").read_text(encoding="utf-8"))
        assert "disprove_lemma:L011" in new_state["exhausted_actions"]

        second_plan = json.loads(manager.autopilot_plan())
        assert second_plan["action"] == "switch_approach"
        assert second_plan["target"] == "A002"


def test_autopilot_switch_cooldown_runs_a002_experiment_next():
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")
        project = Path(tmp) / "research" / "riemann_hypothesis"

        approaches = json.loads((project / "approaches.json").read_text(encoding="utf-8"))
        for item in approaches:
            if item["id"] == "A003":
                item["status"] = "stagnation_limited"
            if item["id"] == "A002":
                item["status"] = "open"
                item["rank"] = 3
        status = json.loads((project / "status.json").read_text(encoding="utf-8"))
        status.update({"active_approach_id": "A003", "focused_approach_id": "A003"})
        checkpoint = json.loads((project / "checkpoint.json").read_text(encoding="utf-8"))
        checkpoint.update({"active_approach_id": "A003", "stagnation_status": "limit_reached:repetition"})

        lemmas = [{
            "lemma_id": "L011",
            "approach_id": "A003",
            "title": "Grounded positivity kernel candidate",
            "formal_statement_latex": "Let K be a positive definite kernel on a Hilbert function space associated with the explicit formula for zeta.",
            "assumptions": ["K is an explicit-formula kernel", "K is positive definite on a Hilbert function space"],
            "conclusion": "The route gives a conditional implication toward critical-line zeros.",
            "related_known_criteria": ["Weil criterion"],
            "compared_criteria": ["Weil criterion"],
            "proof_status": "open",
            "testability": "high",
            "possible_counterexample_search": "Counterargument search already exhausted.",
            "source_ids": ["S001", "S002"],
            "risk": "medium",
            "lemma_quality_score": 4,
            "source_grounding_score": 4,
            "testability_score": 5,
            "novelty_score": 4,
            "tautology_status": "none",
            "circularity_status": "none",
        }]
        sources = manager._curated_sources("Riemannsche Vermutung")
        while len(sources) < 11:
            source = dict(sources[-1])
            source["bibtex_key"] = f"{source['bibtex_key']}_{len(sources)}"
            source["title"] = f"{source['title']} {len(sources)}"
            sources.append(source)
        for idx, source in enumerate(sources, start=1):
            source["source_id"] = f"S{idx:03d}"

        state = {
            "running": False,
            "max_steps": 0,
            "completed_steps": 0,
            "last_plan": None,
            "last_result": None,
            "report": [],
            "completed_actions": ["refine_existing_lemma:L011", "disprove_lemma:L011"],
            "exhausted_actions": ["refine_existing_lemma:L011", "disprove_lemma:L011"],
            "failed_actions": [],
            "action_attempt_counts": {"refine_existing_lemma:L011": 1, "disprove_lemma:L011": 1},
            "waiting_for_user": None,
            "last_action": "disprove_lemma",
            "last_active_approach_id": "A003",
            "switch_cooldown": 0,
            "approach_visit_count": {},
            "status": "idle",
        }
        (project / "approaches.json").write_text(json.dumps(approaches, indent=2), encoding="utf-8")
        (project / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        (project / "checkpoint.json").write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
        (project / "formal_lemmas.json").write_text(json.dumps(lemmas, indent=2), encoding="utf-8")
        (project / "sources.json").write_text(json.dumps(sources, indent=2), encoding="utf-8")
        (project / "autopilot_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

        manager.autopilot_start(5)
        report = json.loads(manager.autopilot_report())
        actions = [item["action"] for item in report]
        targets = [item.get("target") for item in report]
        assert actions[0] == "switch_approach"
        assert targets[0] == "A002"
        assert actions[1] == "run_experiment"
        assert targets[1] == "A002"
        assert actions[:4] != ["switch_approach", "switch_approach", "switch_approach", "switch_approach"]


def test_policy_a002_open_plans_experiment_not_switch():
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")
        project = Path(tmp) / "research" / "riemann_hypothesis"
        status = json.loads((project / "status.json").read_text(encoding="utf-8"))
        status["active_approach_id"] = "A002"
        checkpoint = json.loads((project / "checkpoint.json").read_text(encoding="utf-8"))
        checkpoint["active_approach_id"] = "A002"
        state = manager._load_autopilot_state(project)
        state["last_action"] = "switch_approach"
        state["last_action_key"] = "switch_approach:A002"
        state["switch_cooldown"] = 1
        (project / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        (project / "checkpoint.json").write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
        (project / "autopilot_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

        plan = json.loads(manager.autopilot_plan())
        assert plan["action"] == "run_experiment"
        assert plan["target"] == "A002"


def test_policy_a001_verify_no_progress_does_not_switch():
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")
        project = Path(tmp) / "research" / "riemann_hypothesis"
        status = json.loads((project / "status.json").read_text(encoding="utf-8"))
        status["active_approach_id"] = "A001"
        checkpoint = json.loads((project / "checkpoint.json").read_text(encoding="utf-8"))
        checkpoint["active_approach_id"] = "A001"
        state = manager._load_autopilot_state(project)
        state["last_action"] = "verify_claims"
        state["last_action_key"] = "verify_claims"
        state["last_progress_made"] = False
        state["exhausted_actions"] = ["verify_claims"]
        state["completed_actions"] = ["verify_claims"]
        state["action_attempt_counts"] = {"verify_claims": 1}
        (project / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        (project / "checkpoint.json").write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
        (project / "autopilot_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

        plan = json.loads(manager.autopilot_plan())
        assert plan["action"] in {"retrieve_literature", "generate_new_lemma", "summarize_progress"}
        assert plan["action"] != "switch_approach"


def test_autopilot_start_avoids_forbidden_repetition_sequences():
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")
        project = Path(tmp) / "research" / "riemann_hypothesis"

        approaches = json.loads((project / "approaches.json").read_text(encoding="utf-8"))
        for item in approaches:
            if item["id"] == "A003":
                item["status"] = "stagnation_limited"
            if item["id"] == "A002":
                item["status"] = "open"
        status = json.loads((project / "status.json").read_text(encoding="utf-8"))
        status.update({"active_approach_id": "A003", "focused_approach_id": "A003"})
        checkpoint = json.loads((project / "checkpoint.json").read_text(encoding="utf-8"))
        checkpoint.update({"active_approach_id": "A003", "stagnation_status": "limit_reached:repetition"})
        lemmas = [{
            "lemma_id": "L011",
            "approach_id": "A003",
            "title": "Grounded positivity kernel candidate",
            "formal_statement_latex": "Let K be a positive definite kernel on a Hilbert function space associated with the explicit formula for zeta.",
            "assumptions": ["K is an explicit-formula kernel", "K is positive definite on a Hilbert function space"],
            "conclusion": "The route gives a conditional implication toward critical-line zeros.",
            "related_known_criteria": ["Weil criterion"],
            "compared_criteria": ["Weil criterion"],
            "proof_status": "open",
            "testability": "high",
            "possible_counterexample_search": "Counterargument search already exhausted.",
            "source_ids": ["S001", "S002"],
            "risk": "medium",
            "lemma_quality_score": 4,
            "source_grounding_score": 4,
            "testability_score": 5,
            "novelty_score": 4,
            "tautology_status": "none",
            "circularity_status": "none",
        }]
        state = manager._load_autopilot_state(project)
        state["completed_actions"] = ["refine_existing_lemma:L011", "disprove_lemma:L011"]
        state["exhausted_actions"] = ["refine_existing_lemma:L011", "disprove_lemma:L011"]
        state["action_attempt_counts"] = {"refine_existing_lemma:L011": 1, "disprove_lemma:L011": 1}
        (project / "approaches.json").write_text(json.dumps(approaches, indent=2), encoding="utf-8")
        (project / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        (project / "checkpoint.json").write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
        (project / "formal_lemmas.json").write_text(json.dumps(lemmas, indent=2), encoding="utf-8")
        (project / "autopilot_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

        manager.autopilot_start(10)
        report = json.loads(manager.autopilot_report())
        pairs = [(item["action"], item.get("target")) for item in report]
        for prev, cur in zip(pairs, pairs[1:]):
            assert not (prev[0] == "switch_approach" and cur[0] == "switch_approach")
            assert not (prev[0] == cur[0] and prev[1] == cur[1] and cur[0] in {"refine_existing_lemma", "disprove_lemma", "retrieve_literature"})
            assert not (prev[0] == "verify_claims" and cur[0] == "switch_approach")


def test_policy_global_scan_runs_a002_before_pause():
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")
        project = Path(tmp) / "research" / "riemann_hypothesis"

        status = json.loads((project / "status.json").read_text(encoding="utf-8"))
        status["active_approach_id"] = "A001"
        checkpoint = json.loads((project / "checkpoint.json").read_text(encoding="utf-8"))
        checkpoint["active_approach_id"] = "A001"
        approaches = json.loads((project / "approaches.json").read_text(encoding="utf-8"))
        for item in approaches:
            if item["id"] == "A002":
                item["status"] = "open"
        state = manager._load_autopilot_state(project)
        state["completed_actions"] = [
            "verify_claims",
            "retrieve_literature:A001:Riemann hypothesis equivalent formulations Weil criterion Li criterion",
            "generate_new_lemma:A001",
            "summarize_progress",
        ]
        state["exhausted_actions"] = list(state["completed_actions"])
        state["action_attempt_counts"] = {key: 1 for key in state["completed_actions"]}
        state["last_action"] = "summarize_progress"
        state["last_action_key"] = "summarize_progress"
        state["last_progress_made"] = False
        (project / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        (project / "checkpoint.json").write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
        (project / "approaches.json").write_text(json.dumps(approaches, indent=2), encoding="utf-8")
        (project / "autopilot_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

        plan = json.loads(manager.autopilot_plan())
        assert plan["action"] == "run_experiment"
        assert plan["target"] == "A002"
        assert plan["action"] != "pause_no_high_value"


def test_policy_does_not_rerun_analyzed_a002_experiment():
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")
        project = Path(tmp) / "research" / "riemann_hypothesis"

        status = json.loads((project / "status.json").read_text(encoding="utf-8"))
        status["active_approach_id"] = "A001"
        checkpoint = json.loads((project / "checkpoint.json").read_text(encoding="utf-8"))
        checkpoint["active_approach_id"] = "A001"
        approaches = json.loads((project / "approaches.json").read_text(encoding="utf-8"))
        for item in approaches:
            if item["id"] == "A002":
                item["status"] = "open"
        exp_dir = project / "experiments"
        notes_dir = project / "notes"
        exp_dir.mkdir(parents=True, exist_ok=True)
        notes_dir.mkdir(parents=True, exist_ok=True)
        experiment = exp_dir / "experiment_A002_step_5.json"
        experiment.write_text(json.dumps({"approach": "A002", "proof_status": "not_a_proof"}), encoding="utf-8")
        report = notes_dir / "experiment_analysis_A002_18.json"
        report.write_text(json.dumps({
            "report_id": "ER018",
            "experiment_id": "experiment_A002_step_5",
            "approach_id": "A002",
            "used_for_claim_ids": [],
            "evidence_strength": "weak_to_medium",
            "proof_status": "evidence_only",
        }), encoding="utf-8")
        state = manager._load_autopilot_state(project)
        state["completed_actions"] = [
            "verify_claims",
            "retrieve_literature:A001:Riemann hypothesis equivalent formulations Weil criterion Li criterion",
            "generate_new_lemma:A001",
            "summarize_progress",
        ]
        state["exhausted_actions"] = list(state["completed_actions"])
        state["action_attempt_counts"] = {key: 1 for key in state["completed_actions"]}
        state["last_action"] = "summarize_progress"
        state["last_action_key"] = "summarize_progress"
        state["last_progress_made"] = False
        (project / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        (project / "checkpoint.json").write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
        (project / "approaches.json").write_text(json.dumps(approaches, indent=2), encoding="utf-8")
        (project / "autopilot_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

        plan = json.loads(manager.autopilot_plan())
        assert plan["action"] != "run_experiment"
        assert plan["action"] in {"summarize_progress", "generate_new_lemma", "pause_no_high_value", "switch_approach"}


def test_global_scan_uses_open_a003_before_pausing():
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")
        project = Path(tmp) / "research" / "riemann_hypothesis"
        state = manager._load_autopilot_state(project)
        retrieve_key = "retrieve_literature:A001:Riemann hypothesis equivalent formulations Weil criterion Li criterion"
        state["completed_actions"] = ["verify_claims", retrieve_key, "generate_new_lemma:A001", "summarize_progress"]
        state["exhausted_actions"] = ["verify_claims", retrieve_key]
        state["action_attempt_counts"] = {key: 1 for key in state["completed_actions"]}
        (project / "autopilot_state.json").write_text(json.dumps(state), encoding="utf-8")
        plan = json.loads(manager.autopilot_plan())
        assert plan["action"] == "generate_new_lemma"
        assert plan["target"] == "A003"


def test_continuous_research_rolls_exhausted_policy_into_new_epoch():
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")
        project = Path(tmp) / "research" / "riemann_hypothesis"
        state = manager._load_autopilot_state(project)
        retrieve = "retrieve_literature:A001:Riemann hypothesis equivalent formulations Weil criterion Li criterion"
        exhausted = ["verify_claims", retrieve, "generate_new_lemma:A001", "summarize_progress", "run_experiment:A002", "generate_new_lemma:A003"]
        state["continuous_research"] = True
        state["completed_actions"] = exhausted
        state["exhausted_actions"] = exhausted
        state["action_attempt_counts"] = {key: 3 for key in exhausted}
        (project / "autopilot_state.json").write_text(json.dumps(state), encoding="utf-8")
        plan = json.loads(manager.autopilot_plan())
        assert plan["action"] == "start_new_epoch"
        event = json.loads(manager.autopilot_next())
        assert event["action"] == "start_new_epoch"
        updated = manager._load_autopilot_state(project)
        assert updated["research_epoch"] == 1
        assert updated["exhausted_actions"] == []
        assert updated["continuous_research"] is True


if __name__ == "__main__":
    test_research_auto_does_not_catch_autopilot_commands()
    test_internal_autopilot_actions_are_detected()
    test_autopilot_plan_next_report()
    test_autopilot_marks_duplicate_once_then_moves_to_best_lemma()
    test_autopilot_exhausts_zero_result_literature_once()
    test_autopilot_asks_enable_web_once_and_stops()
    test_autopilot_does_not_repeat_exhausted_refine()
    test_research_clean_noise_removes_invalid_domain_gaps()
    test_autopilot_exhausts_disprove_then_switches_to_a002()
    test_autopilot_switch_cooldown_runs_a002_experiment_next()
    test_policy_a002_open_plans_experiment_not_switch()
    test_policy_a001_verify_no_progress_does_not_switch()
    test_autopilot_start_avoids_forbidden_repetition_sequences()
    test_policy_global_scan_runs_a002_before_pause()
    test_policy_does_not_rerun_analyzed_a002_experiment()
    print("research cli routing tests passed")
