import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from agent_system.research.infrastructure import PDFCorpus, MathlibWorkspace, ExperimentProtocolValidator, ResearchReportExporter
from agent_system.research.manager import ResearchProjectManager
from agent_system.research.live_monitor import ResearchLiveMonitor


def test_pdf_ingestion_is_hash_bound_and_page_addressable():
    from pypdf import PdfWriter
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pdf = root / "paper.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        with pdf.open("wb") as handle:
            writer.write(handle)
        project = root / "project"
        record = PDFCorpus().ingest(pdf, project)
        assert record["pages"] == 1
        assert len(record["sha256"]) == 64
        assert Path(record["corpus_path"]).is_file()
        assert record["extraction_status"] == "no_extractable_text"


def test_mathlib_setup_uses_official_lake_template():
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="created", stderr="")
    with tempfile.TemporaryDirectory() as tmp:
        result = MathlibWorkspace(runner=runner).setup(Path(tmp))
        assert result["ready"] is True
        assert calls[0][-1] == "math-lax"
        assert Path(calls[0][0]).name.lower() in {"lake", "lake.exe"}
        assert calls[0][1] == "new"


def test_experiment_protocol_requires_controls_uncertainty_and_reproduction():
    validator = ExperimentProtocolValidator()
    bad = validator.validate({"hypothesis": "x affects y", "analysis_plan": "t-test"})
    assert bad["valid"] is False
    assert "missing:controls" in bad["issues"]
    assert "missing:uncertainty_method" in bad["issues"]
    good = validator.validate({
        "hypothesis": "x affects y", "independent_variables": ["x"], "dependent_variables": ["y"],
        "controls": ["baseline"], "sample_size_or_power": "power >= .8", "analysis_plan": "preregistered model",
        "uncertainty_method": "95% CI", "failure_criteria": "CI contains zero", "reproduction_steps": ["seed=1"],
    })
    assert good["valid"] is True


def test_report_export_contains_claims_lemmas_and_sources():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        (project / "claims.json").write_text(json.dumps([{"claim_id": "C1", "status": "unverified", "text": "claim"}]), encoding="utf-8")
        (project / "formal_lemmas.json").write_text(json.dumps([{"lemma_id": "L1", "proof_status": "open", "title": "lemma", "conclusion": "x"}]), encoding="utf-8")
        (project / "sources.json").write_text(json.dumps([{"source_id": "S1", "title": "source"}]), encoding="utf-8")
        result = ResearchReportExporter().export(project)
        text = Path(result["markdown"]).read_text(encoding="utf-8")
        assert "C1" in text and "L1" in text and "S1" in text


def test_background_research_checkpoints_and_completes():
    with tempfile.TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Background test")
        manager.autopilot_next = lambda project_dir=None: json.dumps({"action": "generate_new_lemma", "state_summary": {"current_status": "autopilot_paused_no_high_value_action"}})
        manager.background_research_start(2, interval_seconds=0.1, max_minutes=1)
        deadline = time.time() + 3
        state = {}
        while time.time() < deadline:
            state = json.loads(manager.background_research_status())
            if state.get("status") == "completed":
                break
            time.sleep(0.05)
        assert state["status"] == "completed"
        assert state["completed_steps"] == 2


def test_live_monitor_is_local_read_only_and_exposes_project_state():
    import urllib.request
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        (project / "status.json").write_text(json.dumps({"problem": "Live test", "active_approach_id": "A001"}), encoding="utf-8")
        (project / "checkpoint.json").write_text(json.dumps({"last_completed_step": 3}), encoding="utf-8")
        (project / "claims.json").write_text("[]", encoding="utf-8")
        (project / "formal_lemmas.json").write_text("[]", encoding="utf-8")
        (project / "sources.json").write_text("[]", encoding="utf-8")
        monitor = ResearchLiveMonitor()
        try:
            url = monitor.start(project, 0)
            assert url.startswith("http://127.0.0.1:")
            html = urllib.request.urlopen(url, timeout=3).read().decode("utf-8")
            data = json.loads(urllib.request.urlopen(url + "api/state", timeout=3).read().decode("utf-8"))
            assert "Research Live" in html
            assert data["problem"] == "Live test"
            assert data["checkpoint"]["last_completed_step"] == 3
        finally:
            monitor.stop()


def test_riemann_experiment_computes_real_zeros_with_reproducibility_metadata():
    with tempfile.TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")
        output = manager.run_experiment("A002")
        project = Path(tmp) / "research" / "riemann_hypothesis"
        artifacts = sorted((project / "experiments").glob("experiment_A002_*.json"))
        data = json.loads(artifacts[-1].read_text(encoding="utf-8"))
        assert "result=ok" in output
        assert data["data_source"] == "mpmath.zetazero"
        assert data["precision_decimal_digits"] == 50
        assert data["sample_size"] == 20
        assert len(data["rows"]) == 20
        assert all(abs(float(row["real"]) - 0.5) < 1e-20 for row in data["rows"])
        assert data["proof_status"] == "finite_numerical_evidence_only"


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("research infrastructure tests passed")
