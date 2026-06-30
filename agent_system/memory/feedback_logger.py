"""
Feedback learning log for confirmed/rejected interpretations.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class FeedbackLogger:
    """Stores feedback events and exposes recent learning signals."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    raw_input TEXT NOT NULL,
                    interpreted_as TEXT NOT NULL,
                    feedback TEXT NOT NULL,
                    correction TEXT,
                    confidence REAL,
                    metadata TEXT
                )
                """
            )
            conn.commit()

    def log(
        self,
        raw_input: str,
        interpreted_as: str,
        feedback: str,
        correction: Optional[str] = None,
        confidence: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO feedback_events
                (ts, raw_input, interpreted_as, feedback, correction, confidence, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(time.time()),
                    raw_input,
                    interpreted_as,
                    feedback,
                    correction,
                    float(confidence),
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM feedback_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM feedback_events").fetchone()[0]
            pos = conn.execute("SELECT COUNT(*) FROM feedback_events WHERE feedback='confirmed'").fetchone()[0]
            neg = conn.execute("SELECT COUNT(*) FROM feedback_events WHERE feedback='rejected'").fetchone()[0]
        return {"total": total, "confirmed": pos, "rejected": neg}


__all__ = ["FeedbackLogger"]
