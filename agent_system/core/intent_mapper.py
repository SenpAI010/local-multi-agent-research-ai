"""Intent mapping for normalized user input."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Tuple

from agent_system.core.input_normalizer import NormalizedInput


@dataclass
class Interpretation:
    raw_input: str
    corrected_text: str
    interpreted_as: str
    intent: str
    confidence: float
    corrections: List[Dict[str, str]]
    signals: List[str]
    evidence: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class IntentMapper:
    """Converts normalized text into user-specific structured intent."""

    INTENT_RULES: List[Tuple[str, Tuple[str, ...]]] = [
        ("code_or_project_review", ("feedback", "review", "schau code", "code anschauen", "fehler suchen")),
        ("capability_question", ("was kann", "was kan", "fähigkeiten", "faehigkeiten", "alles machen")),
        ("build_request", ("baue", "bau", "code", "erstelle", "mach ein", "programmiere")),
        ("screen_question", ("siehst", "bildschirm", "monitor", "offen", "fenster")),
        ("audio_listen", ("hör", "hoer", "mithören", "mithoeren", "mikro")),
        ("memory_update", ("merk dir", "speicher", "memory", "profil")),
        ("settings_scope", ("erlaube", "zugriff", "scope", "anschauen", "sehen darf")),
        ("architecture_security_review", ("architektur", "security", "sicherheit", "lücken", "luecken")),
        ("general_chat", ()),
    ]

    MEANINGS = {
        "code_or_project_review": "User wants technical feedback on the current code/project.",
        "capability_question": "User asks what the local agent can currently do.",
        "build_request": "User wants the agent to build or code something concrete.",
        "screen_question": "User asks about visible screen/window context.",
        "audio_listen": "User wants microphone/audio listening to start or be controlled.",
        "memory_update": "User wants something stored or updated in memory/profile.",
        "settings_scope": "User wants to configure permissions or observation scope.",
        "architecture_security_review": "User wants architecture and security review of the code/project.",
    }

    def __init__(self, user_model):
        self.user_model = user_model

    def map(self, normalized: NormalizedInput) -> Interpretation:
        phrase_meaning = (
            self._lookup_phrase_meaning(normalized.raw_input)
            or self._lookup_phrase_meaning(normalized.normalized_text)
        )
        intent, signals = self._detect_intent(normalized.normalized_text)

        confidence = 0.5
        evidence = list(normalized.evidence)
        if normalized.corrections:
            confidence += 0.1
            signals.append("personal_typo_correction")
        if phrase_meaning:
            confidence += 0.3
            signals.append("known_phrase_meaning")
            evidence.append("matched user-specific phrase meaning")
        if intent != "general_chat":
            confidence += 0.14
            evidence.append(f"matched intent rule: {intent}")
        if normalized.unclear:
            confidence -= 0.1
            evidence.append("input was unclear/incomplete")

        confidence = min(0.98, max(0.1, confidence))
        return Interpretation(
            raw_input=normalized.raw_input,
            corrected_text=normalized.normalized_text,
            interpreted_as=phrase_meaning or self.MEANINGS.get(intent, normalized.normalized_text),
            intent=intent,
            confidence=round(confidence, 3),
            corrections=normalized.corrections,
            signals=signals,
            evidence=evidence,
        )

    def _lookup_phrase_meaning(self, text: str) -> str:
        lowered = text.lower().strip(" ?!.,")
        meanings = self.user_model.phrase_meanings()
        if lowered in meanings:
            return meanings[lowered]
        for phrase, meaning in meanings.items():
            if phrase in lowered:
                return meaning
        return ""

    def _detect_intent(self, text: str) -> tuple[str, List[str]]:
        lowered = text.lower()
        signals: List[str] = []
        for intent, phrases in self.INTENT_RULES:
            if not phrases:
                continue
            hits = [phrase for phrase in phrases if phrase in lowered]
            if hits:
                signals.extend(hits[:3])
                return intent, signals
        return "general_chat", signals


__all__ = ["IntentMapper", "Interpretation"]
