"""Input normalization for the personalized agent."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, List


@dataclass
class NormalizedInput:
    raw_input: str
    normalized_text: str
    confidence: float
    corrections: List[Dict[str, str]]
    unclear: bool
    evidence: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class InputNormalizer:
    """Corrects user-specific typos and produces normalized text."""

    TECH_WORDS = {
        "agent", "ki", "code", "projekt", "visual", "studio", "unity", "discord",
        "feedback", "review", "fehler", "debug", "memory", "rag", "modell",
        "avatar", "screen", "bildschirm", "audio", "mikro", "ollama",
    }

    def __init__(self, user_model):
        self.user_model = user_model

    def normalize(self, text: str) -> NormalizedInput:
        raw = text.strip()
        corrected, corrections = self._apply_corrections(raw)
        evidence: List[str] = []
        confidence = 0.72
        if corrections:
            confidence += 0.16
            evidence.append("personal/edit-distance corrections applied")
        unclear = self._looks_unclear(corrected)
        if unclear:
            confidence -= 0.22
            evidence.append("short or incomplete phrase")
        confidence = min(0.98, max(0.1, confidence))
        return NormalizedInput(
            raw_input=raw,
            normalized_text=corrected,
            confidence=round(confidence, 3),
            corrections=corrections,
            unclear=unclear,
            evidence=evidence,
        )

    def interpret(self, text: str):
        """Backward-compatible helper. Prefer TurnPipeline + IntentMapper."""
        from agent_system.core.intent_mapper import IntentMapper

        normalized = self.normalize(text)
        return IntentMapper(self.user_model).map(normalized)

    def _apply_corrections(self, text: str) -> tuple[str, List[Dict[str, str]]]:
        corrections: List[Dict[str, str]] = []
        result = text
        typo_map = self.user_model.common_typos()

        for wrong, correct in typo_map.items():
            pattern = rf"\b{re.escape(wrong)}\b"
            if re.search(pattern, result, flags=re.IGNORECASE):
                result = re.sub(pattern, correct, result, flags=re.IGNORECASE)
                corrections.append({"from": wrong, "to": correct, "source": "user_model"})

        words = re.findall(r"\b[\wäöüÄÖÜß]+\b", result)
        for word in words:
            lower = word.lower()
            if lower in typo_map or len(lower) < 5:
                continue
            close = difflib.get_close_matches(lower, self.TECH_WORDS, n=1, cutoff=0.82)
            if close:
                corrected = close[0]
                result = re.sub(rf"\b{re.escape(word)}\b", corrected, result, count=1, flags=re.IGNORECASE)
                corrections.append({"from": word, "to": corrected, "source": "edit_distance"})

        return " ".join(result.split()), corrections

    def _looks_unclear(self, text: str) -> bool:
        words = re.findall(r"\b[\wäöüÄÖÜß]+\b", text)
        return len(words) <= 2 and not text.endswith("?")


__all__ = ["InputNormalizer", "NormalizedInput"]
