from pathlib import Path
import tempfile

from agent_system.memory.user_model import UserModel
from agent_system.core.input_normalizer import InputNormalizer
from agent_system.core.intent_mapper import IntentMapper
from agent_system.memory.feedback_logger import FeedbackLogger
from agent_system.core.audit_logger import AuditLogger
from agent_system.runtime import RawInputStore, TurnPipeline


def main():
    print("=" * 70)
    print("Personalization Layer Test")
    print("=" * 70)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = Path(tmp)
        user_model = UserModel(base / "user_model.json")
        normalizer = InputNormalizer(user_model)
        mapper = IntentMapper(user_model)

        item = normalizer.interpret("feddback?")
        assert item.intent == "code_or_project_review", item
        assert "Feedback" in item.interpreted_as or "Feedback" in item.corrected_text
        print("  [OK] feddback? -> code feedback")

        item2 = normalizer.interpret("was kan mein agent alles")
        assert item2.intent == "capability_question", item2
        print("  [OK] messy capability question recognized")

        user_model.confirm_interpretation("feddback?", "Code-Review zum aktuellen Projekt", 0.9)
        item3 = normalizer.interpret("feddback?")
        assert "Code-Review" in item3.interpreted_as
        print("  [OK] confirmed phrase meaning reused")

        feedback = FeedbackLogger(base / "feedback.sqlite3")
        feedback.log("feddback?", item3.interpreted_as, "confirmed", confidence=item3.confidence)
        assert feedback.stats()["confirmed"] == 1
        print("  [OK] feedback logger")

        audit = AuditLogger(base / "audit.jsonl")
        audit.log("input_interpreted", item3.to_dict())
        assert audit.tail(1)[0]["event"] == "input_interpreted"
        print("  [OK] audit logger")

        pipeline = TurnPipeline(
            user_model=user_model,
            raw_store=RawInputStore(),
            normalizer=normalizer,
            intent_mapper=mapper,
            audit=audit,
            trace_dir=base / "traces",
        )
        trace = pipeline.start_turn("feeddbakcm")
        assert trace.raw_input["text"] == "feeddbakcm"
        assert trace.interpretation["intent"] in {"code_or_project_review", "general_chat"}
        assert (base / "traces" / "latest_trace.json").exists()
        print("  [OK] turn pipeline trace")

    print("\n[RESULT] Personalization Layer PASSED")


if __name__ == "__main__":
    main()
