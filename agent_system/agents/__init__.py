"""
Agent Orchestrator: Main Chef-Agent mit Tool-Koordination
"""
import json
import time
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from .workers import WorkerRouter
from agent_system.memory.personal_learning import PersonalLearning
from agent_system.memory.user_model import UserModel
from agent_system.memory.feedback_logger import FeedbackLogger
from agent_system.core.system_monitor import SystemMonitor
from agent_system.core.task_classifier import TaskClassifier
from agent_system.core.input_normalizer import InputNormalizer
from agent_system.core.intent_mapper import IntentMapper, Interpretation
from agent_system.core.audit_logger import AuditLogger
from agent_system.runtime import RawInputStore, TurnPipeline

class Orchestrator:
    """
    Chef-Agent: Koordiniert Tool-Aufrufe, Gedächtnis und Ollama-Kommunikation.
    
    Workflow:
    1. User gibt Eingabe
    2. Orchestrator laden Kontext (Profile, Memory)
    3. Chat mit Ollama mit natives Tool-Calling
    4. Tool-Call erkannt → Tool ausführen mit Approval
    5. Feedback an Ollama
    6. Loop bis keine Tool-Calls mehr
    7. Speichern in Memory
    """

    def __init__(
        self,
        ollama_native,  # OllamaNative instance
        memory_mgr,      # MemoryManager instance
        sandbox_mgr,     # SandboxManager instance
    ):
        self.ollama = ollama_native
        self.memory = memory_mgr
        self.sandbox = sandbox_mgr
        self.max_tool_hops = 12
        self.summary_every_turns = 12
        self.turn_count = 0
        self.session_messages: List[Tuple[str, str]] = []
        self.worker_router = WorkerRouter()
        self.learning = PersonalLearning(self.sandbox.base_dir / "personal_learning.json")
        self.user_model = UserModel(self.sandbox.base_dir / "user_model.json")
        self.input_normalizer = InputNormalizer(self.user_model)
        self.intent_mapper = IntentMapper(self.user_model)
        self.raw_input_store = RawInputStore()
        self.feedback_logger = FeedbackLogger(self.sandbox.base_dir / "feedback.sqlite3")
        self.audit = AuditLogger(self.sandbox.base_dir / "audit.jsonl")
        self.turn_pipeline = TurnPipeline(
            user_model=self.user_model,
            raw_store=self.raw_input_store,
            normalizer=self.input_normalizer,
            intent_mapper=self.intent_mapper,
            audit=self.audit,
            trace_dir=self.sandbox.base_dir / "traces",
        )
        self.last_interpretation: Optional[Interpretation] = None
        self.system_monitor = SystemMonitor()
        self.task_classifier = TaskClassifier()
        self.fast_model = "qwen2.5:7b-instruct"

    def register_tools(self, tool_defs: Dict[str, Any]) -> None:
        """
        Registriert Tools bei Ollama.
        
        tool_defs: {
            "tool_name": callable_function,
            ...
        }
        """
        self.ollama.register_tools(tool_defs)
        self.tool_funcs = tool_defs

    def run_turn(self, user_text: str, auto_mode: bool = False) -> str:
        """
        Führt einen kompletten Turn aus:
        - Chat mit Tool-Loop
        - Speichern in Memory
        - Ggf. Zusammenfassung
        
        Returns: Final response text
        """
        self.turn_count += 1
        intent_text = self._extract_user_intent_text(user_text)
        trace = self.turn_pipeline.start_turn(intent_text)
        interpretation = Interpretation(**trace.interpretation)
        pending_memory = getattr(self, "_pending_retrieved_memory", None)
        if pending_memory:
            self.turn_pipeline.set_retrieved_memory(pending_memory)
            self._pending_retrieved_memory = None
        self.last_interpretation = interpretation
        self.learning.learn_from_text(intent_text)
        normalized_user_text = self.learning.normalize_user_text(interpretation.corrected_text)
        self.audit.log("input_interpreted", interpretation.to_dict())

        if self._debug_enabled():
            print("\n[DEBUG] Interpretation:")
            print(json.dumps(interpretation.to_dict(), indent=2, ensure_ascii=False))

        fast_answer = self._try_fast_answer(normalized_user_text)
        if fast_answer is not None:
            self.session_messages.append(("user", user_text))
            self.session_messages.append(("assistant", fast_answer))
            return fast_answer

        decision = self.task_classifier.classify(normalized_user_text)
        deep_requested = False
        if decision.should_ask_deep and not auto_mode:
            if self._avatar_permission_enabled("deep_thinking_auto"):
                print(
                    "Diese Anfrage profitiert von laengerem Nachdenken "
                    f"({decision.reason}). [auto: avatar trust profile]"
                )
                deep_requested = True
            else:
                ans = input(
                    f"Diese Anfrage koennte von laengerem Nachdenken profitieren ({decision.reason}). "
                    "Soll ich tiefer nachdenken? [y/N] "
                ).strip().lower()
                deep_requested = ans in {"y", "yes", "j", "ja"}
        
        # Keep active context in RAM. Permanent storage is opt-in only.
        self.session_messages.append(("user", user_text))
        recent = self.session_messages[-20:]

        # System-Prompt mit Profil
        system_prompt = self.memory.build_system_prompt()
        system_prompt = (
            f"{system_prompt}\n\n"
            f"{self.learning.build_prompt_context()}\n\n"
            f"{self.user_model.prompt_context()}\n\n"
            "CURRENT INPUT INTERPRETATION:\n"
            f"- Raw: {interpretation.raw_input}\n"
            f"- Corrected: {interpretation.corrected_text}\n"
            f"- Interpreted as: {interpretation.interpreted_as}\n"
            f"- Intent: {interpretation.intent}\n"
            f"- Confidence: {interpretation.confidence}\n"
            "Use the interpreted meaning, but do not hide uncertainty if confidence is low.\n"
        )
        worker = self.worker_router.route(normalized_user_text)
        if not deep_requested and decision.complexity in {"simple", "medium"}:
            chief = self.worker_router.registry.get("chief_reasoning")
            if chief and worker.name in {"deep_reasoning", "chief_reasoning"}:
                worker = chief
        worker = self._adapt_worker_for_resources(worker)
        self.turn_pipeline.set_specialist(worker.name, worker.model, worker.purpose)
        self.ollama.set_model(worker.model)
        self.ollama.set_tools_enabled(worker.supports_tools)
        system_prompt = (
            f"{system_prompt}\n\n"
            f"ACTIVE SPECIALIST: {worker.name}\n"
            f"PURPOSE: {worker.purpose}\n"
            f"{worker.system_hint}\n"
        )

        # Chat-History für Ollama
        messages: List[Dict[str, str]] = []
        for role, content in recent:
            if role not in {"system", "user", "assistant"}:
                role = "user"
            messages.append({"role": role, "content": content})

        # Tool-Loop
        response_text = ""
        for step in range(self.max_tool_hops):
            if auto_mode:
                print(f"[Step {step + 1}/{self.max_tool_hops}] 🤔 Thinking...")

            # Chat mit Ollama
            try:
                response_text, tool_call = self.ollama.chat_with_tools(
                    messages=messages,
                    system=system_prompt,
                )
            except Exception as e:
                response_text = f"Error communicating with Ollama: {e}"
                break

            # Kein Tool-Call → fertig
            if tool_call is None:
                if self._looks_like_text_tool_call(response_text):
                    response_text = (
                        "Das Modell hat einen Tool-Aufruf als normalen JSON-Text "
                        "ausgegeben. Bitte wiederhole die Anfrage kurz; native "
                        "Tool-Calls sind jetzt im System-Prompt erzwungen."
                    )
                break

            # Tool validieren & ausführen
            tool_name = tool_call.get("name")
            args = tool_call.get("arguments", {})

            if tool_name not in self.tool_funcs:
                messages.append({"role": "assistant", "content": response_text})
                messages.append({
                    "role": "user",
                    "content": f"Unknown tool: {tool_name}. Available: {list(self.tool_funcs.keys())}"
                })
                continue

            if auto_mode:
                print(f"  🔧 Tool: {tool_name}")
            self.audit.log("tool_call_requested", {"tool": tool_name, "arguments": args})
            self.turn_pipeline.add_tool_event({"phase": "requested", "tool": tool_name, "arguments": args})

            # Tool ausführen
            if not isinstance(args, dict):
                tool_result = {"ok": False, "error": "Tool arguments must be an object."}
            else:
                try:
                    raw_result = self.tool_funcs[tool_name](**args)
                    tool_result = raw_result if isinstance(raw_result, dict) else {"ok": True, "result": raw_result}
                except Exception as e:
                    tool_result = {"ok": False, "error": str(e)}
            self.audit.log("tool_call_result", {"tool": tool_name, "ok": tool_result.get("ok"), "result": tool_result})
            self.turn_pipeline.add_tool_event({"phase": "result", "tool": tool_name, "ok": tool_result.get("ok")})

            if auto_mode:
                ok = tool_result.get("ok", False)
                print(f"  ✓ Result: ok={ok}")

            # Feedback an Ollama
            messages.append({"role": "assistant", "content": response_text})
            messages.append({
                "role": "user",
                "content": f"TOOL_OUTPUT {tool_name}: {json.dumps(tool_result, ensure_ascii=False)}"
            })

        self.session_messages.append(("assistant", response_text))
        self.turn_pipeline.set_response(response_text)

        if self.memory.ask_yes_no("Save this conversation turn to long-term SQLite memory?"):
            self.memory.add_message("user", user_text, require_approval=False)
            self.memory.add_message("assistant", response_text, require_approval=False)

        # Ggf. Zusammenfassung
        if self.turn_count % self.summary_every_turns == 0:
            self._try_summarize()

        return response_text

    def confirm_last_interpretation(self) -> str:
        if not self.last_interpretation:
            return "Keine letzte Interpretation vorhanden."
        item = self.last_interpretation
        self.user_model.confirm_interpretation(item.raw_input, item.interpreted_as, item.confidence)
        self.feedback_logger.log(
            item.raw_input,
            item.interpreted_as,
            "confirmed",
            confidence=item.confidence,
            metadata=item.to_dict(),
        )
        self.audit.log("feedback_confirmed", item.to_dict())
        self.turn_pipeline.add_learning_update({
            "type": "feedback_confirmed",
            "raw_input": item.raw_input,
            "interpreted_as": item.interpreted_as,
            "confidence": item.confidence,
        })
        return f"Bestaetigt: '{item.raw_input}' => {item.interpreted_as}"

    def reject_last_interpretation(self, correction: str = "") -> str:
        if not self.last_interpretation:
            return "Keine letzte Interpretation vorhanden."
        item = self.last_interpretation
        self.user_model.reject_interpretation(item.raw_input, item.interpreted_as, correction=correction or None)
        self.feedback_logger.log(
            item.raw_input,
            item.interpreted_as,
            "rejected",
            correction=correction or None,
            confidence=item.confidence,
            metadata=item.to_dict(),
        )
        self.audit.log("feedback_rejected", {**item.to_dict(), "correction": correction})
        self.turn_pipeline.add_learning_update({
            "type": "feedback_rejected",
            "raw_input": item.raw_input,
            "rejected": item.interpreted_as,
            "correction": correction,
        })
        if correction:
            return f"Korrigiert gelernt: '{item.raw_input}' => {correction}"
        return f"Abgelehnt: '{item.raw_input}' wurde nicht als '{item.interpreted_as}' gemeint."

    def interpret_text(self, text: str) -> Interpretation:
        trace = self.turn_pipeline.preview(self._extract_user_intent_text(text))
        return Interpretation(**trace.interpretation)

    def _try_fast_answer(self, user_text: str) -> Optional[str]:
        """Answer trivial profile/status questions without RAG or large models."""
        intent_text = self._extract_user_intent_text(user_text)
        text = intent_text.strip().lower()
        if not text:
            return ""

        if any(q in text for q in ("wer bin ich", "wer bin ich?", "kennst du mich")):
            profile = self.memory.get_profile().get("user_info", {})
            name = profile.get("name")
            role = profile.get("role")
            if name and role:
                return f"Du bist {name}. Ich kenne dich als {role} und arbeite mit dir an deinem lokalen Multi-Agenten-System."
            if name:
                return f"Du bist {name}. Ich arbeite mit dir an deinem lokalen Multi-Agenten-System."
            return "Ich kenne deinen Namen noch nicht sicher. Ich arbeite mit dir an diesem lokalen Multi-Agenten-System."

        if text in {"hi", "hallo", "hey", "servus"}:
            profile = self.memory.get_profile().get("user_info", {})
            name = profile.get("name")
            return f"Hi {name}. Ich bin da." if name else "Hi! Ich bin da."

        if text in {
            "ok", "okay", "stark", "nice", "gut", "super", "passt", "perfekt",
            "danke", "top", "alles klar", "ja", "jup",
        }:
            return "Alles klar."

        if "welches modell" in text or "welche modelle" in text:
            worker = self.worker_router.route(intent_text)
            return f"Fuer diese Anfrage wuerde ich den Spezialisten `{worker.name}` mit Modell `{worker.model}` nutzen."

        return None

    def _extract_user_intent_text(self, text: str) -> str:
        """Extract the actual user request from augmented visual/RAG prompts."""
        if not text:
            return ""

        markers = ("[USER]", "Original query:")
        for marker in markers:
            if marker in text:
                return text.rsplit(marker, 1)[1].strip()
        return text.strip()

    def _adapt_worker_for_resources(self, worker):
        """Prefer smaller available model under system pressure."""
        snap = self.system_monitor.snapshot()
        if snap.pressure == "high":
            # Keep coding specialist if needed, but use fast fallback for general reasoning.
            if worker.name in {"chief_reasoning", "deep_reasoning", "audio_meeting"}:
                fallback = self.worker_router.registry.get("chief_reasoning")
                if fallback:
                    return fallback
        return worker

    def _avatar_permission_enabled(self, key: str) -> bool:
        """Read opt-in behavior toggles from the avatar trust profile."""
        path = self.sandbox.base_dir / "avatar_permissions.json"
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return False
        return bool(data.get(key, False))

    def _debug_enabled(self) -> bool:
        path = self.sandbox.base_dir / "avatar_permissions.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return bool(data.get("debug_observability", False))
            except Exception:
                pass
        return False

    def _try_summarize(self) -> None:
        """Erstellt Zusammenfassung der letzten Messages."""
        recent = self.session_messages[-50:]
        prev_summary = self.memory.get_latest_summary() or "(none)"

        summary_messages = [
            {
                "role": "user",
                "content": f"""Summarize the conversation briefly. Include:
- Main topics discussed
- Decisions made
- Current goals/tasks
- Important findings

Previous summary:
{prev_summary}

Recent messages:
{json.dumps(recent, ensure_ascii=False)}"""
            }
        ]

        try:
            summary, _ = self.ollama.chat_with_tools(messages=summary_messages)
            if summary:
                self.memory.add_summary(summary)
        except Exception:
            pass  # Fail silently

    def _looks_like_text_tool_call(self, text: str) -> bool:
        """Detect old JSON-as-text tool calls without executing them."""
        stripped = (text or "").strip()
        if not stripped:
            return False

        lowered = stripped.lower()
        if (
            ("save_note" in lowered or "wb_write_file" in lowered or "run_command" in lowered)
            and ("arguments" in lowered or "args" in lowered)
        ):
            return True

        try:
            data = json.loads(stripped)
        except Exception:
            return False

        if not isinstance(data, dict):
            return False

        return (
            ("name" in data and "arguments" in data)
            or ("tool" in data and "args" in data)
        )

    def health_check(self) -> Tuple[bool, str]:
        """Prüft Ollama-Verbindung."""
        return self.ollama.health_check()


# Export für __init__.py
__all__ = ["Orchestrator"]
