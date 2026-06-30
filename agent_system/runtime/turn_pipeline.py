"""Central per-turn pipeline for personalization and observability."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_system.core.audit_logger import AuditLogger
from agent_system.core.input_normalizer import InputNormalizer, NormalizedInput
from agent_system.core.intent_mapper import IntentMapper, Interpretation
from agent_system.runtime.raw_input_store import RawInputStore, RawInputEvent


@dataclass
class TurnTrace:
    trace_id: str
    ts: int
    raw_input: Dict[str, Any]
    normalized_input: Dict[str, Any]
    interpretation: Dict[str, Any]
    selected_specialist: Optional[Dict[str, Any]] = None
    retrieved_memory: List[Dict[str, Any]] = field(default_factory=list)
    tools_used: List[Dict[str, Any]] = field(default_factory=list)
    learning_updates: List[Dict[str, Any]] = field(default_factory=list)
    response_preview: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TurnPipeline:
    """Coordinates raw input, normalization, intent mapping and trace writing."""

    def __init__(
        self,
        user_model,
        raw_store: RawInputStore,
        normalizer: InputNormalizer,
        intent_mapper: IntentMapper,
        audit: AuditLogger,
        trace_dir: Path,
    ):
        self.user_model = user_model
        self.raw_store = raw_store
        self.normalizer = normalizer
        self.intent_mapper = intent_mapper
        self.audit = audit
        self.trace_dir = Path(trace_dir)
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.latest_trace: Optional[TurnTrace] = None

    def start_turn(self, text: str, source: str = "cli", active_window: Optional[str] = None) -> TurnTrace:
        raw = self.raw_store.add(text=text, source=source, active_window=active_window)
        normalized = self.normalizer.normalize(raw.text)
        interpretation = self.intent_mapper.map(normalized)
        trace = self._make_trace(raw, normalized, interpretation)

        self.user_model.record_turn(
            raw_text=interpretation.raw_input,
            normalized_text=interpretation.corrected_text,
            intent=interpretation.intent,
            confidence=interpretation.confidence,
        )
        self.audit.log("turn_pipeline_started", trace.to_dict())
        self._save_trace(trace)
        return trace

    def preview(self, text: str, source: str = "preview") -> TurnTrace:
        raw = RawInputEvent(
            id="preview",
            ts=int(time.time()),
            text=text,
            source=source,
            active_window=None,
            session_id="preview",
        )
        normalized = self.normalizer.normalize(raw.text)
        interpretation = self.intent_mapper.map(normalized)
        return self._make_trace(raw, normalized, interpretation, persist=False)

    def set_specialist(self, name: str, model: str, purpose: str = "") -> None:
        if not self.latest_trace:
            return
        self.latest_trace.selected_specialist = {
            "name": name,
            "model": model,
            "purpose": purpose,
        }
        self._save_trace(self.latest_trace)

    def set_retrieved_memory(self, items: List[Dict[str, Any]]) -> None:
        if not self.latest_trace:
            return
        compact = []
        for item in items[:10]:
            compact.append({
                "id": item.get("id"),
                "relevance": item.get("relevance"),
                "metadata": item.get("metadata", {}),
                "text_preview": (item.get("text") or item.get("content") or "")[:240],
            })
        self.latest_trace.retrieved_memory = compact
        self._save_trace(self.latest_trace)

    def add_tool_event(self, event: Dict[str, Any]) -> None:
        if not self.latest_trace:
            return
        self.latest_trace.tools_used.append(event)
        self._save_trace(self.latest_trace)

    def add_learning_update(self, event: Dict[str, Any]) -> None:
        if not self.latest_trace:
            return
        self.latest_trace.learning_updates.append(event)
        self._save_trace(self.latest_trace)

    def set_response(self, response: str) -> None:
        if not self.latest_trace:
            return
        self.latest_trace.response_preview = response[:500]
        self._save_trace(self.latest_trace)

    def latest_trace_dict(self) -> Dict[str, Any]:
        if not self.latest_trace:
            path = self.trace_dir / "latest_trace.json"
            if path.exists():
                try:
                    return json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    return {}
            return {}
        return self.latest_trace.to_dict()

    def _make_trace(
        self,
        raw: RawInputEvent,
        normalized: NormalizedInput,
        interpretation: Interpretation,
        persist: bool = True,
    ) -> TurnTrace:
        trace = TurnTrace(
            trace_id=raw.id,
            ts=raw.ts,
            raw_input=raw.to_dict(),
            normalized_input=normalized.to_dict(),
            interpretation=interpretation.to_dict(),
        )
        if persist:
            self.latest_trace = trace
        return trace

    def _save_trace(self, trace: TurnTrace) -> None:
        data = trace.to_dict()
        latest = self.trace_dir / "latest_trace.json"
        latest.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        history = self.trace_dir / "trace_history.jsonl"
        with history.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(data, ensure_ascii=False) + "\n")


__all__ = ["TurnPipeline", "TurnTrace"]
