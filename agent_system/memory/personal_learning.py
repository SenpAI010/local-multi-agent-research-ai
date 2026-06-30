"""
Personal learning memory for user-specific writing habits and preferences.

This is not model fine-tuning. It is a local profile layer that improves prompts
and text normalization over time while staying inspectable and editable.
"""
import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple


class PersonalLearning:
    """Stores user-specific corrections, preferences, and style signals."""

    DEFAULT_CORRECTIONS = {
        "nciht": "nicht",
        "ncith": "nicht",
        "imemr": "immer",
        "schrieben": "schreiben",
        "schriebe": "schreibe",
        "schiock": "schick",
        "schicken": "schicken",
        "zusmamnefassung": "zusammenfassung",
        "zusmamefassung": "zusammenfassung",
        "zuammenfasung": "zusammenfassung",
        "sprahcmoddel": "sprachmodell",
        "profossneirl": "professionell",
        "vertshet": "versteht",
        "sehne": "sehen",
    }

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self) -> Dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "corrections": dict(self.DEFAULT_CORRECTIONS),
            "preferences": {
                "language": "de",
                "tone": "direkt, warm, praktisch",
                "goal": "professionelles lokales Multi-Agenten-System",
                "approval_required_for_permanent_memory": True,
            },
            "observed_terms": {},
            "notes": [],
        }

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")

    def add_correction(self, wrong: str, correct: str) -> None:
        wrong = wrong.strip().lower()
        correct = correct.strip()
        if wrong and correct:
            self.data.setdefault("corrections", {})[wrong] = correct
            self.save()

    def learn_from_text(self, text: str) -> List[Tuple[str, str]]:
        """Detect known typo patterns in user text and count them."""
        found: List[Tuple[str, str]] = []
        corrections = self.data.setdefault("corrections", {})
        observed = Counter(self.data.setdefault("observed_terms", {}))

        words = re.findall(r"\b[\wäöüÄÖÜß]+\b", text.lower())
        for word in words:
            observed[word] += 1
            if word in corrections:
                found.append((word, corrections[word]))

        self.data["observed_terms"] = dict(observed.most_common(500))
        self.save()
        return found

    def normalize_user_text(self, text: str) -> str:
        """Apply known user-specific corrections for intent understanding."""
        result = text
        for wrong, correct in self.data.get("corrections", {}).items():
            result = re.sub(rf"\b{re.escape(wrong)}\b", correct, result, flags=re.IGNORECASE)
        return result

    def build_prompt_context(self) -> str:
        prefs = self.data.get("preferences", {})
        corrections = self.data.get("corrections", {})
        common = list(corrections.items())[:30]
        correction_lines = "\n".join(f"- {wrong} -> {right}" for wrong, right in common)

        return f"""PERSONALIZATION:
- Preferred language: {prefs.get('language', 'de')}
- Tone: {prefs.get('tone', 'direkt, warm, praktisch')}
- Long-term goal: {prefs.get('goal', '')}
- The user often types quickly and makes typos. Infer intent charitably.
- Common user typo corrections:
{correction_lines}
"""

    def summary(self) -> str:
        corrections = self.data.get("corrections", {})
        observed = self.data.get("observed_terms", {})
        top = sorted(observed.items(), key=lambda item: item[1], reverse=True)[:10]
        return (
            f"Corrections: {len(corrections)}\n"
            f"Top observed terms: {top}\n"
            f"Profile file: {self.path}"
        )


__all__ = ["PersonalLearning"]
