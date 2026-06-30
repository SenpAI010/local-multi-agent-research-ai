"""
Phase 3 Orchestrator: Adds RAG context enrichment to base Orchestrator
"""

from typing import Dict, List, Any, Optional
import json

from agent_system.agents import Orchestrator
from agent_system.core.intent_mapper import Interpretation
from agent_system.memory.semantic_store import SemanticStore
from agent_system.memory.decision_logger import DecisionLogger
from agent_system.memory.rag_engine import RAGEngine


class OrchestratorWithRAG(Orchestrator):
    """
    Extended Orchestrator with Retrieval-Augmented Generation.
    
    Adds:
    - Semantic knowledge retrieval
    - Decision history tracking
    - Context-aware prompt augmentation
    - Solution suggestions from history
    """
    
    def __init__(self, ollama_native, memory_mgr, sandbox_mgr):
        """
        Initialize RAG-enabled Orchestrator.
        
        Args:
            ollama_native: OllamaNative instance
            memory_mgr: MemoryManager instance
            sandbox_mgr: SandboxManager instance
        """
        super().__init__(ollama_native, memory_mgr, sandbox_mgr)
        
        # Initialize Phase 3 components
        db_path = sandbox_mgr.base_dir / "chroma_db"
        
        self.semantic_store = SemanticStore(db_path)
        self.decision_logger = DecisionLogger(sandbox_mgr.db_path.parent / "decisions.db")
        self.rag_engine = RAGEngine(self.semantic_store, self.decision_logger, memory_mgr)
        
        print("✅ RAG Engine initialized")
    
    def run_turn_with_rag(
        self,
        user_text: str,
        auto_mode: bool = False,
        use_rag: bool = True,
        store_response: bool = False
    ) -> str:
        """
        Enhanced turn with RAG context enrichment.
        
        Args:
            user_text: User input
            auto_mode: Auto-execution mode
            use_rag: Enable RAG context enrichment
            store_response: Store response as knowledge
            
        Returns:
            Response text
        """
        intent_text = self._extract_user_intent_text(user_text)
        preview_trace = self.turn_pipeline.preview(intent_text)
        interpretation = type("PreviewInterpretation", (), preview_trace.interpretation)()
        search_query = (
            f"{interpretation.corrected_text}\n"
            f"Intent: {interpretation.intent}\n"
            f"Meaning: {interpretation.interpreted_as}"
        )

        fast_answer = self._try_fast_answer(interpretation.corrected_text)
        if fast_answer is not None:
            self.turn_count += 1
            trace = self.turn_pipeline.start_turn(intent_text)
            self.last_interpretation = Interpretation(**trace.interpretation)
            self.learning.learn_from_text(intent_text)
            self.turn_pipeline.set_specialist("fast_path", self.ollama.model, "Direct fast answer without RAG/tool loop")
            self.turn_pipeline.set_response(fast_answer)
            self.session_messages.append(("user", user_text))
            self.session_messages.append(("assistant", fast_answer))
            return fast_answer

        if use_rag and not self._should_use_rag(interpretation.corrected_text):
            use_rag = False

        # Enrich context with RAG
        if use_rag:
            print("🔍 Retrieving relevant knowledge...")
            enriched = self.rag_engine.enrich_context(search_query, top_k=5)
            self._pending_retrieved_memory = (
                enriched.get("retrieved_knowledge", []) + enriched.get("similar_decisions", [])
            )
            
            # Build augmented prompt
            augmented_query = self.rag_engine.build_augmented_prompt(
                (
                    f"{user_text}\n\n"
                    "[INPUT INTERPRETATION]\n"
                    f"Corrected: {interpretation.corrected_text}\n"
                    f"Intent: {interpretation.intent}\n"
                    f"Meaning: {interpretation.interpreted_as}\n"
                    f"Confidence: {interpretation.confidence}"
                ),
                enriched,
                max_context_length=1500
            )
            
            # Log if relevant context found
            if enriched.get("retrieved_knowledge") or enriched.get("similar_decisions"):
                print("✅ Knowledge retrieved, using for context")
            
            # Use augmented query instead of plain
            query_to_process = augmented_query
        else:
            query_to_process = user_text
        
        # Run normal turn processing (inherited from base Orchestrator)
        response = super().run_turn(query_to_process, auto_mode=auto_mode)
        
        # Store successful response as knowledge only with explicit approval.
        should_store = store_response
        if len(response) > 100 and not should_store:
            should_store = self.memory.ask_yes_no(
                "Store this answer in semantic long-term memory?"
            )

        if should_store and len(response) > 100:
            try:
                self.rag_engine.store_knowledge_from_response(
                    user_text,
                    response,
                    metadata={"type": "agent_response", "confidence": 0.9}
                )
                print("💾 Response stored for future reference")
            except Exception as e:
                print(f"⚠️  Could not store response: {e}")
        
        return response

    def _should_use_rag(self, user_text: str) -> bool:
        """Avoid slow retrieval for simple conversational/status questions."""
        text = self._extract_user_intent_text(user_text).strip().lower()
        decision = self.task_classifier.classify(text)
        if decision.complexity in {"trivial", "simple"}:
            return False

        rag_keywords = (
            "erinner", "memory", "frueher", "früher", "entscheidung", "projekt",
            "zusammenfassung", "history", "verlauf", "was haben wir",
        )
        if any(keyword in text for keyword in rag_keywords):
            return True

        return decision.complexity == "complex"

    def confirm_last_interpretation(self) -> str:
        message = super().confirm_last_interpretation()
        item = self.last_interpretation
        if item:
            try:
                self.semantic_store.add_knowledge(
                    text=(
                        "Confirmed user phrase meaning:\n"
                        f"Raw input: {item.raw_input}\n"
                        f"Corrected: {item.corrected_text}\n"
                        f"Intent: {item.intent}\n"
                        f"Meaning: {item.interpreted_as}\n"
                        f"Confidence: {item.confidence}"
                    ),
                    metadata={
                        "type": "confirmed_interpretation",
                        "intent": item.intent,
                        "confidence": item.confidence,
                    },
                )
            except Exception:
                pass
        return message

    def reject_last_interpretation(self, correction: str = "") -> str:
        message = super().reject_last_interpretation(correction)
        item = self.last_interpretation
        if item and correction:
            try:
                self.semantic_store.add_knowledge(
                    text=(
                        "Corrected user phrase meaning:\n"
                        f"Raw input: {item.raw_input}\n"
                        f"Rejected meaning: {item.interpreted_as}\n"
                        f"Correct meaning: {correction}"
                    ),
                    metadata={
                        "type": "corrected_interpretation",
                        "intent": item.intent,
                        "confidence": item.confidence,
                    },
                )
            except Exception:
                pass
        return message
    
    def log_decision_interactive(self) -> Optional[int]:
        """
        Interactive decision logging (with user approval).
        
        Returns:
            Decision ID if logged, None if cancelled
        """
        print("\n=== LOG DECISION (Optional) ===")
        print("Store this decision for future reference?")
        
        ans = input("Log decision? [y/N] ").strip().lower()
        if ans != "y":
            return None
        
        title = input("Decision title (brief): ").strip()
        if not title:
            return None
        
        decision = input("What was decided: ").strip()
        reasoning = input("Why (reasoning): ").strip()
        
        tags_str = input("Tags (comma-separated, optional): ").strip()
        tags = [t.strip() for t in tags_str.split(",") if t.strip()]
        
        try:
            decision_id = self.rag_engine.store_decision(
                title=title,
                decision=decision,
                reasoning=reasoning,
                tags=tags
            )
            print(f"✅ Decision logged (ID: {decision_id})")
            return decision_id
        except Exception as e:
            print(f"❌ Error logging decision: {e}")
            return None
    
    def get_suggestions(self, problem: str) -> List[Dict[str, Any]]:
        """
        Get suggestions for a problem based on history.
        
        Args:
            problem: Problem description
            
        Returns:
            List of suggestions
        """
        return self.rag_engine.suggest_from_history(problem, max_suggestions=5)
    
    def show_suggestions(self, problem: str):
        """Show suggestions in readable format."""
        suggestions = self.get_suggestions(problem)
        
        if not suggestions:
            print("No suggestions found")
            return
        
        print(f"\n📚 Suggestions for: {problem}\n")
        
        for i, sugg in enumerate(suggestions, 1):
            source = sugg.get("source", "?")
            
            if source == "decision":
                print(f"{i}. From past decision: {sugg.get('title')}")
                print(f"   Approach: {sugg.get('approach')}")
                if sugg.get('outcome'):
                    print(f"   Outcome: {sugg.get('outcome')}")
            
            elif source == "knowledge":
                print(f"{i}. From knowledge base ({sugg.get('relevance', 0):.0%} relevant)")
                print(f"   {sugg.get('content', '')[:200]}")
            
            print()
    
    def get_rag_stats(self) -> Dict[str, Any]:
        """Get RAG system statistics."""
        stats = self.rag_engine.get_context_stats()
        
        return {
            "semantic_knowledge": stats.get("knowledge_count", 0),
            "decisions_logged": stats.get("decision_stats", {}).get("total_decisions", 0),
            "avg_decision_confidence": stats.get("decision_stats", {}).get("avg_confidence", 0),
        }
    
    def show_rag_stats(self):
        """Show RAG statistics."""
        stats = self.get_rag_stats()
        
        print("\n=== RAG System Status ===")
        print(f"Knowledge base: {stats.get('semantic_knowledge', 0)} documents")
        print(f"Decision log: {stats.get('decisions_logged', 0)} decisions")
        print(f"Decision confidence: {stats.get('avg_decision_confidence', 0):.1%}")
        print()


__all__ = ["OrchestratorWithRAG"]
