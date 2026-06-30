"""
NEW Main Entry Point (Phase 1)

This is the new modular system.
Original main.py is preserved as main_old.py

To start:
  python main_new.py
"""

import sys
from pathlib import Path

# Delegate to new system
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    from agent_system.main import main
    main()
