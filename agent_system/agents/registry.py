"""
Professional agent registry for specialist routing.

The registry is the stable contract between the Chef-Agent and specialist
workers. New local capabilities (vision, image generation, video, robotics,
research) can be added here without rewriting the CLI.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class SpecialistAgent:
    name: str
    model: str
    purpose: str
    keywords: tuple[str, ...]
    supports_tools: bool = True
    tools: tuple[str, ...] = field(default_factory=tuple)
    system_hint: str = ""

    def score(self, text: str) -> int:
        lower = text.lower()
        return sum(1 for keyword in self.keywords if keyword in lower)


class AgentRegistry:
    """Registry of all specialist agents known to the Chef-Agent."""

    def __init__(
        self,
        chief_model: str = "qwen3:30b",
        coding_model: str = "qwen3-coder:30b",
        reasoning_model: str = "deepseek-r1:70b",
        vision_model: str = "qwen2.5vl:72b",
        vision_backup_model: str = "llama3.2-vision:90b",
    ):
        self.agents: Dict[str, SpecialistAgent] = {}
        self.default_name = "chief_reasoning"

        self.register(SpecialistAgent(
            name="chief_reasoning",
            model=chief_model,
            purpose="Primary conversation, orchestration, planning, delegation, user adaptation.",
            supports_tools=False,
            keywords=(
                "warum", "plan", "strategie", "architektur", "forschung", "research",
                "mathe", "beweis", "analyse", "entscheidung", "konzept",
            ),
            system_hint=(
                "You are the Chef-Agent. Understand the user, keep the system coherent, "
                "delegate to specialists, and optimize for the user's long-term goals."
            ),
        ))

        self.register(SpecialistAgent(
            name="deep_reasoning",
            model=reasoning_model,
            purpose="Heavy reasoning, math, research, architecture, careful analysis.",
            supports_tools=False,
            keywords=(
                "tief", "beweis", "mathematik", "mathe", "forschung", "paper",
                "komplex", "architektur", "optimierung", "theorie",
            ),
            system_hint=(
                "You are the deep reasoning specialist. Use rigorous analysis, "
                "state assumptions, and solve difficult planning/research problems."
            ),
        ))

        self.register(SpecialistAgent(
            name="code_master",
            model=coding_model,
            purpose="Code generation, debugging, review, tests, local tool usage.",
            supports_tools=True,
            keywords=(
                "code", "python", "bug", "syntax", "traceback", "klasse", "function",
                "unity", "c#", "ros", "gazebo", "test", "refactor", "programm",
            ),
            tools=(
                "wb_write_file", "wb_read_file", "wb_run_python", "wb_pip_install",
                "run_command", "propose_file_replacement", "apply_file_replacement",
            ),
            system_hint=(
                "You are the coding specialist. Be precise, test-minded, and conservative. "
                "Never modify the user's real workspace directly; use sandbox tools only."
            ),
        ))

        self.register(SpecialistAgent(
            name="screen_observer",
            model=reasoning_model,
            purpose="Screen/OCR interpretation, IDE/Discord/meeting context, read-only feedback.",
            supports_tools=False,
            keywords=(
                "monitor", "bildschirm", "screenshot", "discord", "zoom", "meeting",
                "sehen", "ocr", "fenster", "visuell",
            ),
            system_hint=(
                "You are the screen-awareness specialist. Use only provided visual/OCR context. "
                "Never pretend to see unavailable details."
            ),
        ))

        self.register(SpecialistAgent(
            name="audio_meeting",
            model=chief_model,
            purpose="Audio transcript cleanup, meeting notes, summaries, action items.",
            supports_tools=False,
            keywords=(
                "audio", "zuhören", "zuhoeren", "mithören", "mithoeren", "transkript",
                "zusammenfassung", "notizen", "gespräch", "gespraech",
            ),
            system_hint=(
                "You are the meeting specialist. Summarize only transcripted content, "
                "separate facts from uncertainty, and extract action items."
            ),
        ))

        self.register(SpecialistAgent(
            name="vision_future",
            model=vision_model,
            purpose="Image, screenshot, document, UI and visual scene understanding.",
            supports_tools=False,
            keywords=("bild", "image", "foto", "video", "kamera", "vlm"),
            system_hint=(
                "You are the vision specialist. Analyze images/screenshots/documents "
                "when image input is wired into the runtime."
            ),
        ))

        self.register(SpecialistAgent(
            name="image_generation",
            model=chief_model,
            purpose="Local image generation planning through ComfyUI/FLUX workflows.",
            supports_tools=False,
            keywords=("bild generieren", "image generate", "flux", "comfyui", "stable diffusion"),
            system_hint=(
                "You are the image generation planner. Convert user ideas into precise "
                "ComfyUI/FLUX prompts and workflow requirements."
            ),
        ))

        self.register(SpecialistAgent(
            name="video_generation",
            model=chief_model,
            purpose="Local video generation planning through ComfyUI video workflows.",
            supports_tools=False,
            keywords=("video generieren", "animation", "videogenerierung", "text to video"),
            system_hint=(
                "You are the video generation planner. Prepare local video generation "
                "requests and explain required workflows."
            ),
        ))

        self.register(SpecialistAgent(
            name="vision_backup",
            model=vision_backup_model,
            purpose="Backup image analysis specialist.",
            supports_tools=False,
            keywords=("llama vision", "bild backup", "vision backup"),
            system_hint="You are the backup vision specialist.",
        ))

    def register(self, agent: SpecialistAgent) -> None:
        self.agents[agent.name] = agent

    def route(self, text: str) -> SpecialistAgent:
        scored = sorted(
            self.agents.values(),
            key=lambda agent: agent.score(text),
            reverse=True,
        )
        if scored and scored[0].score(text) > 0:
            return scored[0]
        return self.agents[self.default_name]

    def list_agents(self) -> List[SpecialistAgent]:
        return list(self.agents.values())

    def get(self, name: str) -> Optional[SpecialistAgent]:
        return self.agents.get(name)


__all__ = ["AgentRegistry", "SpecialistAgent"]
