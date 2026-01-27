import requests
import os
import time
import sys

BASE_URL = "http://127.0.0.1:8000"

def test_ace():
    print("[Test] Waiting for server to be healthy...")
    retries = 10
    while retries > 0:
        try:
            r = requests.get(f"{BASE_URL}/health")
            if r.status_code == 200:
                print("[Test] Server is ONLINE.")
                break
        except requests.exceptions.ConnectionError as e:
            print(f"[Test] Connection Error: {e}")
        time.sleep(1)
        retries -= 1
        print(f"[Test] Waiting... {retries}")
    
    if retries == 0:
        print("[Test] Server failed to start.")
        sys.exit(1)

    project_path = os.getcwd() # Should be ace_engine root
    print(f"[Test] Triggering Indexing for: {project_path}")
    
    # Trigger Indexing
    r = requests.post(f"{BASE_URL}/v1/context/index", 
                      json={"project_path": project_path, "force": True})
    print(f"[Test] Index Response: {r.status_code} - {r.json()}")
    
    # Query
    query = "What does the Skeletonizer do?"
    print(f"[Test] Querying: '{query}'")
    
    headers = {"X-Project-Path": project_path}
    r = requests.post(f"{BASE_URL}/v1/context/query", 
                      json={"query": query}, headers=headers)
    
    if r.status_code == 200:
        data = r.json()
        print("\n[Test] Results:")
        for res in data.get("results", []):
            print(f"--- File: {res['file_path']} ---")
            print(f"Type: {res['type']}")
            print(res['content'][:200] + "...\n")
    else:
        print(f"[Test] Query Failed: {r.text}")

if __name__ == "__main__":
    test_ace()
