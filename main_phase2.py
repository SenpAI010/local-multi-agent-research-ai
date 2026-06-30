"""
Phase 2 Main CLI: Screen-Aware Agent
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_system.core import OllamaNative, MemoryManager, SandboxManager, MultimodalAgent
from agent_system.tools.workbench import WorkbenchTools
from agent_system.tools.web import WebTools
from agent_system.tools.system import SystemTools
from agent_system.tools import NoteTools
from agent_system.agents import Orchestrator
from agent_system.observers import ScreenshotMonitor, WindowTracker, OCREngine, ErrorDetector


def create_toolset(sandbox_mgr: SandboxManager) -> dict:
    """Erstellt alle verfügbaren Tools."""
    wb = WorkbenchTools(sandbox_mgr)
    web = WebTools()
    sys_tools = SystemTools(sandbox_mgr)
    notes = NoteTools(sandbox_mgr)

    return {
        # Workbench
        "wb_write_file": wb.wb_write_file,
        "wb_read_file": wb.wb_read_file,
        "wb_run_python": wb.wb_run_python,
        "wb_pip_install": wb.wb_pip_install,
        
        # Web
        "web_search": web.web_search,
        "web_fetch": web.web_fetch,
        
        # System
        "run_command": sys_tools.run_command,
        
        # Notes
        "save_note": notes.save_note,
        "list_notes": notes.list_notes,
    }


def context_callback(context):
    """Callback wenn Multimodal-Kontext sich ändert."""
    # Optional: Hier könnte man proaktive Fehler-Erkennung implementieren
    if context.detected_errors:
        print(f"\n⚠️  [ALERT] {len(context.detected_errors)} error(s) detected in active window:")
        for err in context.detected_errors[:3]:
            print(f"   Line {err.get('line', '?')}: {err.get('type')}")


def main():
    print("=" * 70)
    print("Ollama Multi-Agent System (Phase 2: Screen-Aware)")
    print("=" * 70)
    print()

    # ===== Setup =====
    
    # Sandbox
    sandbox_dir = Path("./agent_sandbox")
    sandbox = SandboxManager(sandbox_dir)
    sandbox.ensure_dirs()
    print(f"✅ Sandbox: {sandbox.base_dir}")

    # Memory
    memory = MemoryManager(sandbox.db_path)
    print(f"✅ Memory: {sandbox.db_path}")

    # Ollama
    ollama = OllamaNative(model="qwen2.5:7b-instruct")
    ok, msg = ollama.health_check()
    if not ok:
        print(f"❌ {msg}")
        print("\nMake sure Ollama is running:")
        print("  ollama serve")
        return
    print(f"✅ {msg}")

    # Tools
    toolset = create_toolset(sandbox)
    ollama.register_tools(toolset)
    print(f"✅ Registered {len(toolset)} tools")

    # Orchestrator
    agent = Orchestrator(ollama, memory, sandbox)
    agent.register_tools(toolset)
    print(f"✅ Orchestrator ready")

    # ===== Phase 2: Multimodal =====
    print("\n🔭 Initializing Multimodal Agent (Screen-Awareness)...")
    
    try:
        multimodal = MultimodalAgent(
            sandbox_dir=sandbox_dir,
            screenshot_interval_sec=3.0,  # Screenshot every 3 seconds
            enable_ocr=True,
            enable_errors=True,
        )
        multimodal.add_context_callback(context_callback)
        print("✅ Screenshot Monitor ready")
        print("✅ Window Tracker ready")
        print("✅ OCR Engine ready")
        print("✅ Error Detector ready")
    except Exception as e:
        print(f"⚠️  Multimodal setup failed: {e}")
        multimodal = None

    # ===== User Setup (First Time) =====
    profile = memory.get_profile()
    if not profile:
        print("\nFirst time setup:")
        profile = memory.setup_user_profile()
    print()

    # ===== Start Monitoring =====
    if multimodal:
        print("Starting background monitoring...")
        multimodal.start_monitoring()
        print()

    # ===== Main Loop =====
    print("Type 'exit' to quit.")
    print("Type '/auto <steps> <task>' for auto mode.")
    print("Type '/screenshot' to take a screenshot and analyze it.")
    print("Type '/context' to show current visual context.")
    print()

    try:
        while True:
            try:
                user_input = input("You: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye!")
                break

            if not user_input:
                continue

            if user_input.lower() in {"exit", "quit"}:
                print("Goodbye!")
                break

            # ===== Special Commands =====

            # Screenshot command
            if user_input.lower() == "/screenshot":
                if multimodal:
                    result = multimodal.take_screenshot()
                    if result.get("ok"):
                        analysis = multimodal.analyze_active_window()
                        print(f"\n📸 Screenshot taken: {result.get('filepath')}")
                        print(f"   Window: {result.get('window')}")
                        if analysis.get("errors"):
                            print(f"   ❌ {analysis.get('error_count')} error(s):")
                            for suggestion in analysis.get("suggestions", [])[:3]:
                                print(f"      • {suggestion}")
                        else:
                            print(f"   ✅ No errors detected")
                    else:
                        print(f"❌ {result.get('error')}")
                else:
                    print("Multimodal disabled")
                continue

            # Context command
            if user_input.lower() == "/context":
                if multimodal:
                    ctx_str = multimodal.get_context_string()
                    print(f"\n📊 Current Visual Context:\n{ctx_str}\n")
                else:
                    print("Multimodal disabled")
                continue

            # Auto mode
            if user_input.lower().startswith("/auto"):
                parts = user_input.split(maxsplit=2)
                max_steps = 10
                task = ""

                try:
                    if len(parts) >= 2:
                        max_steps = int(parts[1])
                    if len(parts) >= 3:
                        task = parts[2]
                except ValueError:
                    pass

                if not task:
                    print("AI: Usage: /auto <max_steps> <task>\n")
                    continue

                # Add context if available
                if multimodal:
                    ctx = multimodal.get_context_string()
                    task_with_context = f"[VISUAL CONTEXT]\n{ctx}\n\n[TASK]\n{task}"
                else:
                    task_with_context = task

                response = agent.run_turn(task_with_context, auto_mode=True)
                print(f"\nAI: {response}\n")
                continue

            # Normal mode
            # Add visual context if multimodal available
            if multimodal:
                ctx = multimodal.get_context_string()
                if ctx.strip():
                    user_input_with_context = f"[VISUAL CONTEXT]\n{ctx}\n\n[USER]\n{user_input}"
                else:
                    user_input_with_context = user_input
            else:
                user_input_with_context = user_input

            response = agent.run_turn(user_input_with_context)
            print(f"\nAI: {response}\n")

    except KeyboardInterrupt:
        print("\nInterrupted")
    
    finally:
        if multimodal:
            multimodal.stop_monitoring()
            print("Monitoring stopped")


if __name__ == "__main__":
    main()
