import sys
import os
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

# Add parent directory to path to import ace_engine core
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
sys.path.append(str(current_dir.parent))

from core.memory import MemoryManager

def get_git_commit_message():
    try:
        # Get last commit message
        result = subprocess.check_output(
            ["git", "log", "-1", "--pretty=%B"], 
            cwd=str(project_root),
            stderr=subprocess.STDOUT
        ).decode("utf-8").strip()
        return result
    except Exception as e:
        return f"Error reading commit: {e}"

def main():
    parser = argparse.ArgumentParser(description="Update ACE Memory active_task.md")
    parser.add_argument("--git", action="store_true", help="Update from latest git commit")
    parser.add_argument("--deploy", type=str, help="Update from deploy action (logs the provided message)")
    
    args = parser.parse_args()
    
    manager = MemoryManager(str(project_root))
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = ""
    
    if args.git:
        msg = get_git_commit_message()
        log_entry = f"- [GIT] `{timestamp}`: {msg}"
        print(f"Hook: Detected Commit -> {msg}")
        
    elif args.deploy:
        log_entry = f"- [DEPLOY] `{timestamp}`: {args.deploy}"
        print(f"Hook: Logging Deploy -> {args.deploy}")
        
    else:
        print("Usage: python update_memory_hook.py [--git | --deploy 'msg']")
        return

    if log_entry:
        # Append to active_task.md
        # We read first to allow inserting at top vs bottom? 
        # For logs, bottom append is standard for 'History', but 'Active Task' might imply current state.
        # Let's append to the 'Estado' or 'Recent Activity' section if we can, 
        # but for robustness, simple append is safest for now.
        
        # Check if file ends with newline
        current_content = manager.read("task")
        append_mode = True
        
        try:
            manager.write("task", log_entry, append=append_mode)
            print("✅ ACE Memory Updated.")
        except Exception as e:
            print(f"❌ Failed to update memory: {e}")

if __name__ == "__main__":
    main()
