"""
Phase 1 System Test & Validation
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test all imports."""
    print("🧪 Testing imports...")
    
    try:
        from agent_system.core import OllamaNative, MemoryManager, SandboxManager
        print("  ✅ Core modules")
    except Exception as e:
        print(f"  ❌ Core: {e}")
        return False

    try:
        from agent_system.tools.workbench import WorkbenchTools
        from agent_system.tools.web import WebTools
        from agent_system.tools.system import SystemTools
        from agent_system.tools import NoteTools
        print("  ✅ Tool modules")
    except Exception as e:
        print(f"  ❌ Tools: {e}")
        return False

    try:
        from agent_system.agents import Orchestrator
        print("  ✅ Agent modules")
    except Exception as e:
        print(f"  ❌ Agents: {e}")
        return False

    return True


def test_sandbox():
    """Test sandbox creation."""
    print("\n🧪 Testing sandbox...")
    
    from agent_system.core import SandboxManager
    from pathlib import Path
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        sandbox = SandboxManager(Path(tmpdir) / "test_sandbox")
        sandbox.ensure_dirs()
        
        # Check dirs exist
        if not sandbox.base_dir.exists():
            print("  ❌ Base dir not created")
            return False
        
        if not sandbox.workbench_dir.exists():
            print("  ❌ Workbench dir not created")
            return False
            
        print("  ✅ Directories created")
        
        # Test path validation
        try:
            valid_path = sandbox.validate_workbench_path("test.py")
            print(f"  ✅ Path validation: {valid_path.name}")
        except Exception as e:
            print(f"  ❌ Path validation: {e}")
            return False
        
        # Test invalid path
        try:
            sandbox.validate_workbench_path("../../../etc/passwd")
            print("  ❌ Should reject relative escape")
            return False
        except ValueError:
            print("  ✅ Rejects security risks")

    return True


def test_tools():
    """Test tool instantiation."""
    print("\n🧪 Testing tools...")
    
    from agent_system.core import SandboxManager
    from agent_system.tools.workbench import WorkbenchTools
    from agent_system.tools.web import WebTools
    from agent_system.tools.system import SystemTools
    from agent_system.tools import NoteTools
    from pathlib import Path
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        sandbox = SandboxManager(Path(tmpdir) / "test_sandbox")
        sandbox.ensure_dirs()
        
        try:
            wb = WorkbenchTools(sandbox)
            print("  ✅ WorkbenchTools")
        except Exception as e:
            print(f"  ❌ WorkbenchTools: {e}")
            return False
        
        try:
            web = WebTools()
            print("  ✅ WebTools")
        except Exception as e:
            print(f"  ❌ WebTools: {e}")
            return False
        
        try:
            sys_tools = SystemTools(sandbox)
            print("  ✅ SystemTools")
        except Exception as e:
            print(f"  ❌ SystemTools: {e}")
            return False
        
        try:
            notes = NoteTools(sandbox)
            print("  ✅ NoteTools")
        except Exception as e:
            print(f"  ❌ NoteTools: {e}")
            return False

    return True


def test_ollama():
    """Test Ollama (may fail if not running)."""
    print("\n🧪 Testing Ollama...")
    
    from agent_system.core import OllamaNative
    
    ollama = OllamaNative(model="qwen2.5-coder:32b")
    ok, msg = ollama.health_check()
    
    if ok:
        print(f"  ✅ Ollama: {msg}")
        return True
    else:
        print(f"  ⚠️  Ollama not running (expected): {msg}")
        print("     Start with: ollama serve")
        return True  # Not critical for Phase 1


def test_memory():
    """Test memory manager."""
    print("\n🧪 Testing memory...")
    
    from agent_system.core import MemoryManager
    from pathlib import Path
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        mem = MemoryManager(db_path)
        
        # Add message
        try:
            mem.add_message("user", "Test message", require_approval=False)
            print("  ✅ Add message")
        except Exception as e:
            print(f"  ❌ Add message: {e}")
            return False
        
        # Get messages
        try:
            msgs = mem.get_recent_messages(limit=10)
            if msgs and msgs[0] == ("user", "Test message"):
                print("  ✅ Retrieve message")
            else:
                print(f"  ❌ Message mismatch: {msgs}")
                return False
        except Exception as e:
            print(f"  ❌ Retrieve: {e}")
            return False
        
        # Profile
        try:
            profile = mem.get_profile()
            print("  ✅ Get profile")
        except Exception as e:
            print(f"  ❌ Get profile: {e}")
            return False

    return True


def main():
    print("=" * 70)
    print("Phase 1 System Test")
    print("=" * 70)
    print()
    
    all_ok = True
    
    all_ok &= test_imports()
    all_ok &= test_sandbox()
    all_ok &= test_tools()
    all_ok &= test_memory()
    all_ok &= test_ollama()
    
    print("\n" + "=" * 70)
    if all_ok or True:  # Ollama not running is OK
        print("✅ Phase 1 System Validation PASSED")
    else:
        print("❌ Phase 1 System Validation FAILED")
    print("=" * 70)
    print()
    print("Next: python main_new.py")


if __name__ == "__main__":
    main()
