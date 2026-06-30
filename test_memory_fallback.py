from pathlib import Path
from tempfile import TemporaryDirectory

from agent_system.memory.semantic_store import SemanticStore


def test_fallback_store_quarantines_corrupt_json_and_recovers():
    with TemporaryDirectory() as tmp:
        store = SemanticStore(Path(tmp))
        store.use_fallback = True
        store.fallback_file.write_text("{broken json", encoding="utf-8")

        assert store.list_knowledge() == []
        assert not store.fallback_file.exists()
        assert store.fallback_file.with_suffix(".json.corrupt").exists()

        doc_id = store.add_knowledge("Riemann hypothesis note", {"type": "test"}, "doc-1")
        assert doc_id == "doc-1"
        assert store.get_knowledge("doc-1")["text"] == "Riemann hypothesis note"
        assert not list(Path(tmp).glob("*.tmp"))


if __name__ == "__main__":
    test_fallback_store_quarantines_corrupt_json_and_recovers()
    print("memory fallback tests passed")
