import argparse
import subprocess
import sys
from pathlib import Path

# Add core path
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
sys.path.append(str(current_dir.parent))

from core.memory import MemoryManager

def main():
    parser = argparse.ArgumentParser(description="Wrapper for Agent Deployments that updates ACE Memory")
    parser.add_argument("--cmd", required=True, help="The actual command to run (e.g. 'ssh user@host ...')")
    parser.add_argument("--target", default="unknown", help="Target environment (vps, prod, staging)")
    parser.add_argument("--desc", default="", help="Short description of what is being deployed")
    
    # Parse known args, pass the rest? No, simple strings for agents.
    args = parser.parse_args()
    
    manager = MemoryManager(str(project_root))
    
    # 1. Log Start
    print(f"🔄 [ACE] Intercepting deploy command...")
    entry = f"- [DEPLOY_START] Target: `{args.target}` | Cmd: `{args.cmd}`"
    if args.desc:
        entry += f" | Desc: {args.desc}"
        
    try:
        manager.write("task", entry, append=True)
    except Exception as e:
        print(f"⚠️ Warning: Could not write to memory: {e}")

    # 2. Run Real Command (Streaming output)
    print(f"🚀 [ACE] Executing: {args.cmd}")
    print("-" * 40)
    
    try:
        # shell=True allows full strings like "npm run build && scp ..." 
        # (Agents love chaining commands)
        process = subprocess.Popen(
            args.cmd, 
            shell=True,
            stdout=sys.stdout,
            stderr=sys.stderr
        )
        return_code = process.wait()
        print("-" * 40)
        
        # 3. Log Result
        status = "SUCCESS" if return_code == 0 else "FAILED"
        result_entry = f"- [DEPLOY_END] Status: {status} (Exit Code: {return_code})"
        manager.write("task", result_entry, append=True)
        
        if return_code != 0:
            print(f"❌ [ACE] Command failed with code {return_code}")
            sys.exit(return_code)
            
        print(f"✅ [ACE] Command finished successfully. Memory updated.")
        
    except Exception as e:
        err_msg = f"- [DEPLOY_ERROR] Exception: {str(e)}"
        manager.write("task", err_msg, append=True)
        print(f"💥 [ACE] Critical Error executing command: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
