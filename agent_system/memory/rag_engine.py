"""
RAGEngine: Retrieval-Augmented Generation
Combines semantic retrieval with LLM for context-aware responses.
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
import json


class RAGEngine:
    """
    Retrieval-Augmented Generation engine.
    Retrieves relevant context and augments prompts for better LLM responses.
    """
    
    def __init__(self, semantic_store, decision_logger, memory_mgr):
        """
        Initialize RAG engine.
        
        Args:
            semantic_store: SemanticStore instance
            decision_logger: DecisionLogger instance
            memory_mgr: MemoryManager instance (from core)
        """
        self.semantic_store = semantic_store
        self.decision_logger = decision_logger
        self.memory_mgr = memory_mgr
    
    def enrich_context(
        self,
        user_query: str,
        context_type: str = "general",
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        Enrich user query with relevant context from knowledge base.
        
        Args:
            user_query: User's question/input
            context_type: Type of context ("general", "code", "decision", "error")
            top_k: Number of relevant documents to retrieve
            
        Returns:
            Enriched context dict with retrieved knowledge, similar decisions, etc.
        """
        context = {
            "query": user_query,
            "type": context_type,
            "retrieved_knowledge": [],
            "similar_decisions": [],
            "memory_summary": None,
        }
        
        # Retrieve from semantic store
        try:
            retrieved = self.semantic_store.retrieve(user_query, top_k=top_k)
            context["retrieved_knowledge"] = [
                item for item in retrieved
                if not self._looks_like_tool_call_text(item.get("text", ""))
            ]
        except Exception as e:
            print(f"❌ Knowledge retrieval failed: {e}")
        
        # Find similar decisions
        try:
            similar = self.decision_logger.find_similar_decisions(user_query, limit=3)
            context["similar_decisions"] = similar
        except Exception as e:
            print(f"❌ Decision search failed: {e}")
        
        # Get memory summary
        try:
            summary = self.memory_mgr.get_latest_summary()
            if summary:
                context["memory_summary"] = summary
        except Exception as e:
            print(f"❌ Memory summary failed: {e}")
        
        return context
    
    def build_augmented_prompt(
        self,
        user_query: str,
        enriched_context: Dict[str, Any],
        max_context_length: int = 2000
    ) -> str:
        """
        Build augmented prompt with retrieved context.
        
        Args:
            user_query: Original user query
            enriched_context: Context from enrich_context()
            max_context_length: Max chars for context section
            
        Returns:
            Augmented prompt string
        """
        prompt_parts = []
        
        # Add retrieved knowledge
        if enriched_context.get("retrieved_knowledge"):
            prompt_parts.append("## RELEVANT KNOWLEDGE")
            for item in enriched_context["retrieved_knowledge"][:3]:
                text = item.get("text", "")[:300]
                relevance = item.get("relevance", 0)
                prompt_parts.append(f"- [{relevance:.1%}] {text}")
        
        # Add similar decisions
        if enriched_context.get("similar_decisions"):
            prompt_parts.append("\n## SIMILAR DECISIONS")
            for dec in enriched_context["similar_decisions"][:2]:
                title = dec.get("title", "")
                reasoning = dec.get("reasoning", "")[:200]
                prompt_parts.append(f"- {title}: {reasoning}")
        
        # Add memory summary
        if enriched_context.get("memory_summary"):
            prompt_parts.append("\n## CONVERSATION SUMMARY")
            summary = enriched_context["memory_summary"][:300]
            prompt_parts.append(summary)
        
        # Combine context
        context_str = "\n".join(prompt_parts)
        
        # Trim to max length
        if len(context_str) > max_context_length:
            context_str = context_str[:max_context_length] + "..."
        
        # Build final prompt
        augmented = f"""[AUGMENTED CONTEXT]
{context_str if context_str else "(no relevant context found)"}

[USER QUERY]
{user_query}"""
        
        return augmented
    
    def store_knowledge_from_response(
        self,
        query: str,
        response: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Store LLM response as knowledge for future retrieval.
        
        Args:
            query: Original query
            response: LLM response
            metadata: Optional metadata
            
        Returns:
            Knowledge ID
        """
        metadata = metadata or {}
        metadata.update({
            "type": "response",
            "query": query[:100],
            "source": "llm_response"
        })
        
        # Store only if response is substantial
        if len(response) > 100 and not self._looks_like_tool_call_text(response):
            return self.semantic_store.add_knowledge(
                text=response,
                metadata=metadata
            )
        
        return ""

    def _looks_like_tool_call_text(self, text: str) -> bool:
        lowered = (text or "").lower()
        return (
            ("save_note" in lowered or "wb_write_file" in lowered or "run_command" in lowered)
            and ("arguments" in lowered or "args" in lowered)
        )
    
    def store_decision(
        self,
        title: str,
        decision: str,
        reasoning: str,
        context: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> int:
        """
        Store a decision with reasoning for future reference.
        
        Args:
            title: Decision title
            decision: What was decided
            reasoning: Why
            context: Optional context
            tags: Optional tags
            
        Returns:
            Decision ID
        """
        return self.decision_logger.log_decision(
            title=title,
            decision=decision,
            reasoning=reasoning,
            context=context,
            tags=tags or [],
            confidence=0.9
        )
    
    def get_context_stats(self) -> Dict[str, Any]:
        """Get statistics about stored knowledge and decisions."""
        stats = {
            "knowledge_count": self.semantic_store.get_count(),
            "decision_stats": self.decision_logger.get_stats(),
            "recent_knowledge": len(self.semantic_store.list_knowledge(limit=10))
        }
        return stats
    
    def suggest_from_history(
        self,
        current_problem: str,
        max_suggestions: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Suggest solutions based on similar past problems/decisions.
        
        Args:
            current_problem: Current issue description
            max_suggestions: Max suggestions to return
            
        Returns:
            List of suggested solutions
        """
        suggestions = []
        
        # Search decisions
        similar_decisions = self.decision_logger.find_similar_decisions(
            current_problem,
            limit=max_suggestions
        )
        
        for dec in similar_decisions:
            if dec.get("outcome"):
                suggestions.append({
                    "source": "decision",
                    "title": dec.get("title"),
                    "approach": dec.get("decision"),
                    "outcome": dec.get("outcome"),
                    "reasoning": dec.get("reasoning")
                })
        
        # Search knowledge
        retrieved = self.semantic_store.retrieve(
            current_problem,
            top_k=max_suggestions
        )
        
        for item in retrieved:
            if item.get("relevance", 0) > 0.6:
                suggestions.append({
                    "source": "knowledge",
                    "content": item.get("text"),
                    "relevance": item.get("relevance"),
                    "metadata": item.get("metadata")
                })
        
        return suggestions[:max_suggestions]


__all__ = ["RAGEngine"]
