"""
New Main CLI: Ollama Multi-Agent System (Phase 1)

Usage:
  python agent_system/main.py              # Interactive mode
  python agent_system/main.py /auto 10 "task"  # Auto mode
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_system.core import OllamaNative, MemoryManager, SandboxManager
from agent_system.tools.workbench import WorkbenchTools
from agent_system.tools.web import WebTools
from agent_system.tools.system import SystemTools
from agent_system.tools import NoteTools
from agent_system.agents import Orchestrator


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


def main():
    print("=" * 70)
    print("Ollama Multi-Agent System (Phase 1)")
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
    print()

    # ===== User Setup (First Time) =====
    profile = memory.get_profile()
    if not profile:
        print("First time setup:")
        profile = memory.setup_user_profile()
    print()

    # ===== Main Loop =====
    print("Type 'exit' to quit.")
    print("Type '/auto <steps> <task>' for auto mode.")
    print()

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

            response = agent.run_turn(task, auto_mode=True)
            print(f"\nAI: {response}\n")
            continue

        # Normal mode
        response = agent.run_turn(user_input)
        print(f"\nAI: {response}\n")


if __name__ == "__main__":
    main()
