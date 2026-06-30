"""Compatibility wrapper around the professional AgentRegistry."""
from .registry import AgentRegistry, SpecialistAgent


class WorkerRouter:
    """Routes a task to the most suitable registered specialist."""

    def __init__(
        self,
        coding_model: str = "qwen3-coder:30b",
        reasoning_model: str = "deepseek-r1:70b",
        chief_model: str = "qwen3:30b",
        vision_model: str = "qwen2.5vl:72b",
        vision_backup_model: str = "llama3.2-vision:90b",
    ):
        self.registry = AgentRegistry(
            chief_model=chief_model,
            coding_model=coding_model,
            reasoning_model=reasoning_model,
            vision_model=vision_model,
            vision_backup_model=vision_backup_model,
        )

    def route(self, user_text: str) -> SpecialistAgent:
        return self.registry.route(user_text)


__all__ = ["WorkerRouter"]
