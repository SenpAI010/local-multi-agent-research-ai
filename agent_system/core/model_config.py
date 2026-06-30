"""
Central model configuration with professional defaults and safe fallbacks.
"""
import os
from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class ModelChoice:
    role: str
    primary: str
    fallbacks: tuple[str, ...]

    def candidates(self) -> List[str]:
        return [self.primary, *self.fallbacks]


class ModelConfig:
    """Defines local model roles for the multi-agent system."""

    def __init__(self):
        self.roles: Dict[str, ModelChoice] = {
            "chief": ModelChoice(
                role="chief",
                primary=os.environ.get("LOCAL_AGENT_CHIEF_MODEL", "qwen3:30b"),
                fallbacks=("deepseek-r1:32b", "qwen2.5:7b-instruct"),
            ),
            "reasoning": ModelChoice(
                role="reasoning",
                primary=os.environ.get("LOCAL_AGENT_REASONING_MODEL", "deepseek-r1:70b"),
                fallbacks=("deepseek-r1:32b", "qwen3:30b"),
            ),
            "coding": ModelChoice(
                role="coding",
                primary=os.environ.get("LOCAL_AGENT_CODING_MODEL", "qwen3-coder:30b"),
                fallbacks=("qwen2.5-coder:32b", "qwen3:30b"),
            ),
            "vision": ModelChoice(
                role="vision",
                primary=os.environ.get("LOCAL_AGENT_VISION_MODEL", "qwen2.5vl:72b"),
                fallbacks=("llama3.2-vision:90b",),
            ),
            "vision_backup": ModelChoice(
                role="vision_backup",
                primary=os.environ.get("LOCAL_AGENT_VISION_BACKUP_MODEL", "llama3.2-vision:90b"),
                fallbacks=("qwen2.5vl:72b",),
            ),
        }

    def get(self, role: str) -> ModelChoice:
        return self.roles[role]

    def primary(self, role: str) -> str:
        return self.get(role).primary

    def all_primary_models(self) -> List[str]:
        return [choice.primary for choice in self.roles.values()]


__all__ = ["ModelConfig", "ModelChoice"]
