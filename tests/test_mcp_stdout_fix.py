import json
import subprocess
import sys

def test_mcp_health_scan():
    # Run the MCP server in another process using stdio
    process = subprocess.Popen(
        [sys.executable, "main_stdio.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd="C:\\Users\\Julian\\Documents\\Antigravity\\ACE indexer\\ace_engine"
    )

    try:
        # We need to send initialization first before tools/call
        init_req = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"}
            }
        }
        process.stdin.write(json.dumps(init_req) + "\n")
        process.stdin.flush()
        
        # Read init response
        init_res = process.stdout.readline()
        # Send initialized notification
        process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        process.stdin.flush()
        
        # Prepare JSON-RPC request for the health scan tool
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ace_code_health_scan",
                "arguments": {
                    "project_path": "C:\\Users\\Julian\\Documents\\Antigravity\\ACE indexer"
                }
            }
        }
        
        # Send actual tool request
        process.stdin.write(json.dumps(request) + "\n")
        process.stdin.flush()

        # Read the response
        response_str = process.stdout.readline()
        if not response_str:
            print("FAILED: No output received")
            return 1
            
        print(f"RAW STDOUT RECEIVED:\n{response_str.strip()}")
            
        # Verify it parses as JSON
        try:
            response_data = json.loads(response_str)
            if "error" in response_data:
                print(f"FAILED: Received RPC error:\n{response_data['error']}")
                return 1
            print("SUCCESS: JSON Parsed correctly. The [DEBUG...] print is gone from stdout.")
            return 0
        except json.JSONDecodeError as e:
            print(f"FAILED: JSON decoding error (Error was: {e})")
            return 1
            
    finally:
        process.terminate()

if __name__ == "__main__":
    sys.exit(test_mcp_health_scan())
