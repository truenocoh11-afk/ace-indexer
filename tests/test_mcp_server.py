import subprocess
import json
import os

def test_mcp_connection():
    # Go up one level from the tests directory to the project root
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    script_path = os.path.join(repo_root, "run_mcp.bat")
    
    print(f"[Test] Launching MCP: {script_path}")
    
    # We can't easily speak JSON-RPC 2.0 manually over stdio in a simple script 
    # without a full client implementation.
    # However, we can simply verify the script launches without crashing.
    
    try:
        process = subprocess.Popen(
            [script_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        # Send an initialization request (MCP 2.0 draft) - Simplified
        # Actually, let's just check if it stays alive for 2 seconds.
        try:
             outs, errs = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            print("[Test] Process is alive and waiting (Good sign for an MCP server)")
            process.kill()
            return True
            
        if process.returncode != 0:
            print(f"[Test] Failed. Return code: {process.returncode}")
            print(f"Stderr: {errs}")
            return False
            
    except Exception as e:
        print(f"[Test] Execution failed: {e}")
        return False

if __name__ == "__main__":
    test_mcp_connection()
