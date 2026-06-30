from pathlib import Path
from tempfile import TemporaryDirectory
import json

from agent_system.research import ResearchProjectManager
from agent_system.research.web_proxy import WebResearchProxy
from agent_system.tools.web import WebTools


def test_web_proxy_blocks_unsafe_targets():
    with TemporaryDirectory() as tmp:
        proxy = WebResearchProxy(Path(tmp), enabled=True)
        assert not proxy.fetch_text("file:///C:/secret.txt")["allowed"]
        assert not proxy.fetch_text("http://127.0.0.1:11434/api/tags")["allowed"]
        assert not proxy.fetch_text("http://192.168.0.1/")["allowed"]
        assert not proxy.fetch_text("https://example.com/")["allowed"]


def test_web_proxy_allowlist_management_blocks_private_domains():
    with TemporaryDirectory() as tmp:
        proxy = WebResearchProxy(Path(tmp), enabled=True)
        proxy.add_domain("example.org")
        assert "example.org" in proxy.allowlist()
        proxy.remove_domain("example.org")
        assert "example.org" not in proxy.allowlist()
        try:
            proxy.add_domain("127.0.0.1")
            raised = False
        except ValueError:
            raised = True
        assert raised


def test_empty_allowlist_remains_empty():
    with TemporaryDirectory() as tmp:
        proxy = WebResearchProxy(Path(tmp), enabled=True)
        for domain in list(proxy.allowlist()):
            proxy.remove_domain(domain)
        assert proxy.allowlist() == []
        assert not proxy.fetch_text("https://arxiv.org/")["allowed"]


def test_general_webtools_blocks_redirect_to_private_target():
    class FakeResponse:
        status_code = 302
        headers = {"Location": "http://127.0.0.1:11434/api/tags"}

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=65536, decode_unicode=True):
            return iter(())

    tools = WebTools()
    tools._resolves_to_private = lambda host: False
    import agent_system.tools.web as web_mod
    original_get = web_mod.requests.get
    try:
        web_mod.requests.get = lambda *args, **kwargs: FakeResponse()
        result = tools.web_fetch("https://example.com/start")
    finally:
        web_mod.requests.get = original_get
    assert result["ok"] is False
    assert "private" in result["error"].lower()


def test_minimal_query_regex_does_not_crash():
    with TemporaryDirectory() as tmp:
        proxy = WebResearchProxy(Path(tmp), enabled=True)
        assert proxy._minimal_query("Weil criterion Riemann hypothesis positivity")
        cleaned = proxy._minimal_query("Weil criterion / Riemann-hypothesis + positivity")
        assert "Weil criterion / Riemann-hypothesis + positivity" == cleaned
        weird = proxy._minimal_query("Weil criterion [DROP] $(whoami) <script>")
        assert "[" not in weird
        assert "$" not in weird
        assert "<" not in weird


def test_research_web_search_does_not_crash_and_audit_works():
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")
        manager.set_web_enabled(True)
        result = manager.web_search("Weil criterion / Riemann-hypothesis + positivity")
        assert isinstance(result, str)
        assert manager.web_sources().strip().startswith("[")
        assert manager.web_audit().strip().startswith("[")


def test_research_web_status_and_claim_trust():
    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")
        assert "deaktiviert" in manager.set_web_enabled(False)
        assert "aktiv" in manager.set_web_enabled(True)
        status = json.loads(manager.web_status())
        assert status["enabled"] is True
        assert "export.arxiv.org" in status["allowlist"]

        project = Path(tmp) / "research" / "riemann_hypothesis"
        claims = [{
            "claim_id": "C999",
            "text": "Known theorem with untrusted source must not become source-supported.",
            "type": "known_theorem",
            "status": "unverified",
            "source_ids": ["S999"],
            "depends_on": [],
            "counterarguments": [],
            "risk": "high",
            "formal_status": "not_formalized",
        }]
        sources = [{
            "source_id": "S999",
            "title": "Unknown blog",
            "authors": "Unknown",
            "year": "2026",
            "url": "https://example.com/x",
            "bibtex_key": "unknown_blog",
            "summary": "Untrusted.",
            "trust_level": "unknown",
        }]
        (project / "claims.json").write_text(json.dumps(claims, indent=2), encoding="utf-8")
        (project / "sources.json").write_text(json.dumps(sources, indent=2), encoding="utf-8")
        manager.verify_claims()
        checked = json.loads((project / "claims.json").read_text(encoding="utf-8"))
        assert checked[0]["status"] == "unverified"
        assert checked[0]["risk"] == "high"


def test_research_web_search_integrates_sources():
    class FakeProxy:
        def search_literature(self, query, purpose=""):
            return [{
                "title": "Weil positivity criterion for the Riemann hypothesis",
                "authors": "Example Author",
                "year": "2020",
                "url": "https://arxiv.org/abs/2001.00001",
                "bibtex_key": "example_weil_positivity_2020",
                "summary": "A web-proxy source about Weil-style positivity.",
                "relevance": "Source grounding for positivity lemmas.",
                "retrieval_mode": "web_arxiv",
            }]

        def audit_tail(self, limit=40):
            return []

    with TemporaryDirectory() as tmp:
        manager = ResearchProjectManager(Path(tmp))
        manager.start("Riemannsche Vermutung")
        manager.set_web_enabled(True)
        manager._web_proxy = lambda project_dir: FakeProxy()
        result = manager.web_search("Weil criterion Riemann hypothesis positivity")
        assert "1 neue Source" in result

        project = Path(tmp) / "research" / "riemann_hypothesis"
        sources = json.loads((project / "sources.json").read_text(encoding="utf-8"))
        assert len(sources) >= 3
        added = sources[-1]
        assert added["source_id"].startswith("S")
        assert added["retrieval_mode"] == "web_proxy"
        assert added["retrieval_mode_detail"] == "web_arxiv"
        assert added["trust_level"] == "survey"
        assert added["used_for_approach_id"]
        assert "example_weil_positivity_2020" in (project / "references.bib").read_text(encoding="utf-8")
        assert "Weil positivity criterion" in (project / "main.tex").read_text(encoding="utf-8")


if __name__ == "__main__":
    test_web_proxy_blocks_unsafe_targets()
    test_web_proxy_allowlist_management_blocks_private_domains()
    test_empty_allowlist_remains_empty()
    test_general_webtools_blocks_redirect_to_private_target()
    test_minimal_query_regex_does_not_crash()
    test_research_web_search_does_not_crash_and_audit_works()
    test_research_web_status_and_claim_trust()
    test_research_web_search_integrates_sources()
    print("research web proxy tests passed")
