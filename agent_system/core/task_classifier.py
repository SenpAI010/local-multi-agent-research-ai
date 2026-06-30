"""
Heuristic task classifier for speed vs deep-thinking decisions.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class TaskDecision:
    complexity: str
    should_ask_deep: bool
    reason: str


class TaskClassifier:
    """Classifies whether a user request should be answered fast or deeply."""

    ACKS = {
        "ok", "okay", "stark", "nice", "gut", "super", "passt", "perfekt",
        "danke", "top", "alles klar", "ja", "jup",
    }

    DEEP_KEYWORDS = (
        "architektur", "security", "sicherheit", "optimier", "debug", "fehler",
        "strategie", "vergleich", "analyse", "review", "refactor", "plane",
        "komplex", "mathe", "beweis", "forschung", "langgraph", "multi-agent",
        "entscheidung", "design", "performance", "speicher", "datenbank",
    )

    FAST_PHRASES = (
        "wer bin ich", "welches modell", "siehst du", "was ist offen",
        "welches video",
    )
    GREETINGS = {"hi", "hallo", "hey", "servus"}

    def classify(self, text: str) -> TaskDecision:
        t = text.strip().lower()
        if not t:
            return TaskDecision("trivial", False, "empty")

        if t in self.ACKS:
            return TaskDecision("trivial", False, "acknowledgement")

        if t in self.GREETINGS:
            return TaskDecision("trivial", False, "greeting")

        if len(t) < 80 and any(keyword in t for keyword in self.FAST_PHRASES):
            return TaskDecision("simple", False, "simple status/profile question")

        score = 0
        score += sum(1 for keyword in self.DEEP_KEYWORDS if keyword in t)
        if len(t) > 220:
            score += 2
        elif len(t) > 120:
            score += 1
        if "?" in t and ("warum" in t or "wie" in t):
            score += 1

        if score >= 2:
            return TaskDecision("complex", True, "complexity/risk keywords")
        if score == 1:
            return TaskDecision("medium", True, "possibly benefits from deeper reasoning")
        return TaskDecision("simple", False, "default fast path")


__all__ = ["TaskClassifier", "TaskDecision"]
