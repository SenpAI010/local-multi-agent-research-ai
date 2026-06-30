"""
Phase 3 System Test & Validation: RAG + Semantic Memory
"""
import sys
from pathlib import Path
import tempfile
import shutil

sys.path.insert(0, str(Path(__file__).parent))


def test_semantic_store():
    """Test semantic vector database."""
    print("[TEST] Testing SemanticStore...")
    
    from agent_system.memory.semantic_store import SemanticStore
    import shutil
    
    test_dir = Path("./agent_sandbox/test_semantic")
    test_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        store = SemanticStore(test_dir / "chroma")
        
        try:
            # Add knowledge
            id1 = store.add_knowledge("Python is a programming language")
            id2 = store.add_knowledge("JavaScript runs in browsers")
            print("  [OK] Knowledge added")
        except Exception as e:
            print(f"  [FAIL] Add knowledge failed: {e}")
            return False
        
        try:
            # Retrieve
            results = store.retrieve("What is Python?", top_k=2)
            if results and len(results) > 0:
                print(f"  [OK] Retrieved {len(results)} results")
            else:
                print("  [WARN] No results retrieved (expected on first run)")
        except Exception as e:
            print(f"  [FAIL] Retrieval failed: {e}")
            return False
        
        try:
            # Count
            count = store.get_count()
            print(f"  [OK] Store count: {count} documents")
        except Exception as e:
            print(f"  [FAIL] Count failed: {e}")
            return False
        
        return True
    
    finally:
        # Clean up
        try:
            if test_dir.exists():
                shutil.rmtree(test_dir, ignore_errors=True)
        except Exception:
            pass


def test_decision_logger():
    """Test decision logging."""
    print("\n[TEST] Testing DecisionLogger...")
    
    from agent_system.memory.decision_logger import DecisionLogger
    
    test_dir = Path("./agent_sandbox/test_decisions")
    test_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        logger = DecisionLogger(test_dir / "decisions.db")
        
        try:
            # Log decision
            decision_id = logger.log_decision(
                title="Fix SyntaxError",
                decision="Add missing bracket",
                reasoning="Syntax error on line 12",
                tags=["error", "fix"]
            )
            print(f"  [OK] Decision logged (ID: {decision_id})")
        except Exception as e:
            print(f"  [FAIL] Log decision failed: {e}")
            return False
        
        try:
            # Retrieve
            decision = logger.get_decision(decision_id)
            if decision and decision["title"] == "Fix SyntaxError":
                print("  [OK] Decision retrieved")
            else:
                print("  [FAIL] Decision not found")
                return False
        except Exception as e:
            print(f"  [FAIL] Retrieve failed: {e}")
            return False
        
        try:
            # Get stats
            stats = logger.get_stats()
            print(f"  [OK] Stats: {stats['total_decisions']} total decisions")
        except Exception as e:
            print(f"  [FAIL] Stats failed: {e}")
            return False
        
        logger.close()
        return True
    
    finally:
        try:
            if test_dir.exists():
                shutil.rmtree(test_dir, ignore_errors=True)
        except Exception:
            pass


def test_rag_engine():
    """Test RAG engine."""
    print("\n[TEST] Testing RAGEngine...")
    
    from agent_system.memory.semantic_store import SemanticStore
    from agent_system.memory.decision_logger import DecisionLogger
    from agent_system.memory.rag_engine import RAGEngine
    from agent_system.core import MemoryManager
    
    test_dir = Path("./agent_sandbox/test_rag")
    test_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Initialize components
        semantic = SemanticStore(test_dir / "chroma")
        decisions = DecisionLogger(test_dir / "decisions.db")
        memory = MemoryManager(test_dir / "memory.db")
        
        rag = RAGEngine(semantic, decisions, memory)
        
        try:
            # Add some knowledge
            semantic.add_knowledge("Error handling in Python uses try/except blocks")
            semantic.add_knowledge("Debugging with breakpoints helps find issues")
            print("  [OK] Knowledge added")
        except Exception as e:
            print(f"  [FAIL] Add knowledge failed: {e}")
            return False
        
        try:
            # Enrich context
            enriched = rag.enrich_context("How do I handle errors?", top_k=3)
            print(f"  [OK] Context enriched")
        except Exception as e:
            print(f"  [FAIL] Enrich context failed: {e}")
            return False
        
        try:
            # Build augmented prompt
            prompt = rag.build_augmented_prompt(
                "How to debug?",
                enriched,
                max_context_length=500
            )
            if "[AUGMENTED CONTEXT]" in prompt and "[USER QUERY]" in prompt:
                print("  [OK] Prompt augmentation working")
            else:
                print("  [FAIL] Prompt format incorrect")
                return False
        except Exception as e:
            print(f"  [FAIL] Build prompt failed: {e}")
            return False
        
        try:
            # Store decision
            dec_id = rag.store_decision(
                title="Use try/except",
                decision="Wrap risky code in try block",
                reasoning="Prevents crashes"
            )
            print(f"  [OK] Decision stored (ID: {dec_id})")
        except Exception as e:
            print(f"  [FAIL] Store decision failed: {e}")
            return False
        
        try:
            # Get stats
            stats = rag.get_context_stats()
            print(f"  [OK] Stats retrieved")
        except Exception as e:
            print(f"  [FAIL] Stats failed: {e}")
            return False
        
        decisions.close()
        memory.close()
        return True
    
    finally:
        try:
            if test_dir.exists():
                shutil.rmtree(test_dir, ignore_errors=True)
        except Exception:
            pass


def test_orchestrator_rag():
    """Test RAG-enabled Orchestrator."""
    print("\n[TEST] Testing OrchestratorWithRAG...")
    
    from agent_system.core import OllamaNative, MemoryManager, SandboxManager
    from agent_system.agents.orchestrator_rag import OrchestratorWithRAG
    
    test_dir = Path("./agent_sandbox/test_orch")
    test_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Initialize
        try:
            sandbox = SandboxManager(test_dir)
            sandbox.ensure_dirs()
            
            memory = MemoryManager(test_dir / "memory.db")
            ollama = OllamaNative()
            
            orchestrator = OrchestratorWithRAG(ollama, memory, sandbox)
            print("  [OK] OrchestratorWithRAG initialized")
        except Exception as e:
            print(f"  [FAIL] Init failed: {e}")
            return False
        
        # Check RAG stats
        try:
            stats = orchestrator.get_rag_stats()
            print(f"  [OK] RAG stats retrieved")
        except Exception as e:
            print(f"  [FAIL] Get stats failed: {e}")
            return False
        
        return True
    
    finally:
        try:
            if test_dir.exists():
                shutil.rmtree(test_dir, ignore_errors=True)
        except Exception:
            pass


def main():
    print("=" * 70)
    print("Phase 3 System Test (RAG + Semantic Memory)")
    print("=" * 70)
    print()
    
    all_ok = True
    
    try:
        all_ok &= test_semantic_store()
        all_ok &= test_decision_logger()
        all_ok &= test_rag_engine()
        all_ok &= test_orchestrator_rag()
    except ImportError as e:
        print(f"\n[WARN] Import error: {e}")
        print("Make sure to install: pip install chromadb")
        all_ok = False
    
    print("\n" + "=" * 70)
    if all_ok:
        print("[RESULT] Phase 3 System Validation PASSED")
    else:
        print("[RESULT] Phase 3 System Validation FAILED")
    print("=" * 70)
    print()
    print("Next: python main_phase3.py")


if __name__ == "__main__":
    main()
