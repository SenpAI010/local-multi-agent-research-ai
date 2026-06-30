"""Short-term raw input storage."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class RawInputEvent:
    id: str
    ts: int
    text: str
    source: str = "cli"
    active_window: Optional[str] = None
    session_id: str = "default"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RawInputStore:
    """Keeps unchanged user inputs in short-term session memory."""

    def __init__(self, max_events: int = 200):
        self.max_events = max_events
        self.events: List[RawInputEvent] = []

    def add(self, text: str, source: str = "cli", active_window: Optional[str] = None, session_id: str = "default") -> RawInputEvent:
        event = RawInputEvent(
            id=str(uuid.uuid4()),
            ts=int(time.time()),
            text=text,
            source=source,
            active_window=active_window,
            session_id=session_id,
        )
        self.events.append(event)
        self.events = self.events[-self.max_events:]
        return event

    def recent(self, limit: int = 20) -> List[RawInputEvent]:
        return self.events[-limit:]


__all__ = ["RawInputStore", "RawInputEvent"]
