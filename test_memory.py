import sys
import os
from pathlib import Path

# Add parent dir to path to import ace_engine
sys.path.append(str(Path(__file__).parent))

from core.memory import MemoryManager

def test_memory():
    project_path = str(Path(__file__).parent.parent)
    print(f"Testing Memory in: {project_path}")
    
    manager = MemoryManager(project_path)
    
    # 1. Test structure creation
    print("\n[1] Ensuring structure...")
    manager.ensure_structure()
    memory_dir = Path(project_path) / ".ace" / "memory"
    if memory_dir.exists():
        print(f"✅ Memory dir exists: {memory_dir}")
    else:
        print("❌ Memory dir NOT found")
        return

    # 2. Test writing
    print("\n[2] Testing write...")
    res = manager.write("context", "# Project Context\nStack: Python, MCP")
    print(f"Write result: {res}")
    
    res = manager.write("task", "Current Task: Testing Memory", append=True)
    print(f"Append result: {res}")

    # 3. Test reading
    print("\n[3] Testing read all...")
    content = manager.read("all")
    print("--- CONTENT START ---")
    print(content)
    print("--- CONTENT END ---")

    # 4. Test boot flag
    print("\n[4] Testing boot flag...")
    print(f"Initial boot flag state: {manager.has_booted()}")
    manager.set_booted()
    print(f"Post-set boot flag state: {manager.has_booted()}")
    manager.clear_boot_flag()
    print(f"Post-clear boot flag state: {manager.has_booted()}")

    print("\n✅ Memory tests completed.")

if __name__ == "__main__":
    test_memory()
