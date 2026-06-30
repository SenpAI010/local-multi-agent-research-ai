"""
Persistent personalized user model.

This is the inspectable learning layer: preferences, typo mappings, known
projects, recurring intents, interpretation history and confidence updates.
It is not LLM fine-tuning.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_USER_MODEL: Dict[str, Any] = {
    "user_profile": {
        "preferred_language": "deutsch",
        "preferred_style": "direkt, praktisch, technisch, mit Beispielen",
        "technical_level": "fortgeschritten",
        "common_typos": {
            "feddback": "feedback",
            "nciht": "nicht",
            "imemr": "immer",
            "schrieben": "schreiben",
            "progreameire": "programmiere",
            "sprahcmoddel": "sprachmodell",
            "visuel": "visual",
        },
        "projects": {
            "local_ai_agent": {
                "goal": "lokaler autonomer KI-Agent mit Memory, RAG und Tool-Nutzung",
                "current_focus": "personalisiertes Lernen und Nutzeranpassung",
            }
        },
    },
    "intent_memory": {},
    "phrase_meanings": {
        "feddback": "Der Nutzer moechte Feedback zum aktuellen Code/Projektstand.",
        "feedback": "Der Nutzer moechte Feedback zum aktuellen Code/Projektstand.",
        "mach feedback": "Der Nutzer moechte ein kurzes technisches Review mit konkreten Fixes.",
        "was kan mein agent alles": "Der Nutzer fragt nach den aktuellen Faehigkeiten des lokalen KI-Agenten.",
        "schau code": "Der Nutzer moechte read-only Codeanalyse des erlaubten Projekt-Scope.",
    },
    "confirmed_interpretations": [],
    "rejected_interpretations": [],
    "stats": {
        "turns_seen": 0,
        "positive_feedback": 0,
        "negative_feedback": 0,
    },
}


class UserModel:
    """JSON-backed user model that can be updated without model fine-tuning."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                return self._merge_defaults(loaded)
            except Exception:
                pass
        return json.loads(json.dumps(DEFAULT_USER_MODEL))

    def _merge_defaults(self, loaded: Dict[str, Any]) -> Dict[str, Any]:
        merged = json.loads(json.dumps(DEFAULT_USER_MODEL))
        for key, value in loaded.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key].update(value)
            else:
                merged[key] = value
        return merged

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")

    def common_typos(self) -> Dict[str, str]:
        profile = self.data.setdefault("user_profile", {})
        return profile.setdefault("common_typos", {})

    def phrase_meanings(self) -> Dict[str, str]:
        return self.data.setdefault("phrase_meanings", {})

    def record_turn(self, raw_text: str, normalized_text: str, intent: str, confidence: float) -> None:
        stats = self.data.setdefault("stats", {})
        stats["turns_seen"] = int(stats.get("turns_seen", 0)) + 1

        intents = Counter(self.data.setdefault("intent_memory", {}))
        intents[intent] += 1
        self.data["intent_memory"] = dict(intents.most_common(100))

        history = self.data.setdefault("recent_interpretations", [])
        history.append({
            "ts": int(time.time()),
            "raw_input": raw_text[:500],
            "normalized": normalized_text[:500],
            "intent": intent,
            "confidence": round(float(confidence), 3),
        })
        self.data["recent_interpretations"] = history[-50:]
        self.save()

    def add_typo(self, wrong: str, correct: str) -> None:
        wrong = wrong.strip().lower()
        correct = correct.strip()
        if wrong and correct:
            self.common_typos()[wrong] = correct
            self.save()

    def confirm_interpretation(self, raw_input: str, interpreted_as: str, confidence: float) -> None:
        self.data.setdefault("stats", {})["positive_feedback"] = int(
            self.data.setdefault("stats", {}).get("positive_feedback", 0)
        ) + 1
        self.data.setdefault("confirmed_interpretations", []).append({
            "ts": int(time.time()),
            "raw_input": raw_input,
            "interpreted_as": interpreted_as,
            "confidence": min(1.0, float(confidence) + 0.08),
        })
        if raw_input and interpreted_as:
            key = raw_input.lower().strip()
            self.phrase_meanings()[key] = interpreted_as
            self.phrase_meanings()[key.strip(" ?!.,")] = interpreted_as
        self.save()

    def reject_interpretation(self, raw_input: str, interpreted_as: str, correction: Optional[str] = None) -> None:
        self.data.setdefault("stats", {})["negative_feedback"] = int(
            self.data.setdefault("stats", {}).get("negative_feedback", 0)
        ) + 1
        self.data.setdefault("rejected_interpretations", []).append({
            "ts": int(time.time()),
            "raw_input": raw_input,
            "interpreted_as": interpreted_as,
            "correction": correction or "",
        })
        if correction:
            key = raw_input.lower().strip()
            self.phrase_meanings()[key] = correction
            self.phrase_meanings()[key.strip(" ?!.,")] = correction
        self.save()

    def prompt_context(self) -> str:
        profile = self.data.get("user_profile", {})
        typo_items = list(profile.get("common_typos", {}).items())[:40]
        phrase_items = list(self.phrase_meanings().items())[:25]
        intents = self.data.get("intent_memory", {})

        return (
            "USER MODEL:\n"
            f"- Preferred language: {profile.get('preferred_language', 'deutsch')}\n"
            f"- Preferred style: {profile.get('preferred_style', '')}\n"
            f"- Technical level: {profile.get('technical_level', '')}\n"
            f"- Frequent intents: {json.dumps(intents, ensure_ascii=False)}\n"
            "- Common typos:\n"
            + "\n".join(f"  - {wrong} -> {right}" for wrong, right in typo_items)
            + "\n- Known phrase meanings:\n"
            + "\n".join(f"  - {raw} => {meaning}" for raw, meaning in phrase_items)
        )

    def summary(self) -> str:
        profile = self.data.get("user_profile", {})
        stats = self.data.get("stats", {})
        return json.dumps({
            "profile": profile,
            "intent_memory": self.data.get("intent_memory", {}),
            "stats": stats,
            "file": str(self.path),
        }, indent=2, ensure_ascii=False)


__all__ = ["UserModel", "DEFAULT_USER_MODEL"]
