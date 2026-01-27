import requests
import json
import sys
import threading
import time

BASE_URL = "http://127.0.0.1:8000"

def listen_sse():
    print("[Test] Connecting to SSE stream...")
    try:
        with requests.get(f"{BASE_URL}/sse", stream=True) as r:
            for line in r.iter_lines():
                if line:
                    decoded = line.decode('utf-8')
                    if decoded.startswith("data:"):
                        data = decoded.replace("data: ", "")
                        if "?" in data: 
                            # We got the endpoint with session ID
                            # e.g. /messages?session_id=...
                            return data.strip()
    except Exception as e:
        print(f"SSE Error: {e}")
    return None

def main():
    # 1. Get Session ID from SSE
    endpoint = listen_sse()
    if not endpoint:
        print("[Test] Failed to get session ID from SSE.")
        sys.exit(1)
            
    print(f"[Test] Session established! Endpoint: {endpoint}")
    post_url = f"{BASE_URL}{endpoint}"
    
    # 2. Add Init Request (Required by MCP)
    init_payload = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"}
        },
        "id": 1
    }
    
    # 3. Add List Tools Request
    list_tools_payload = {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "id": 2
    }

    try:
        print("[Test] Sending 'initialize'...")
        r1 = requests.post(post_url, json=init_payload)
        print(f"[Test] Init Response: {r1.status_code}")
        
        # We need to send 'notifications/initialized' to complete handshake usually,
        # but for simple listing, server might accept parallel requests or wait.
        # Let's try sending initialized.
        requests.post(post_url, json={
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        })

        print("[Test] Sending 'tools/list'...")
        r2 = requests.post(post_url, json=list_tools_payload)
        print(f"[Test] Tools Response: {r2.status_code}")
        
        if r2.status_code == 200:
             # It might return accepted (202) and send result via SSE? 
             # Or return immediately? SSE Transport usually uses SSE for responses.
             print("[Test] Request accepted. (Note: Actual response comes via SSE stream in full implementation)")
             print("[Test] Server is RESPONDING to MCP commands!")
             
    except Exception as e:
        print(f"[Test] Post Error: {e}")

if __name__ == "__main__":
    main()
