import os
import json
import chromadb

def check_metadata():
    db_path = os.path.join(os.path.dirname(os.getcwd()), '.ace', 'indices', 'chroma_db')
    if not os.path.exists(db_path):
        print(f"DB not found at {db_path}")
        return

    client = chromadb.PersistentClient(path=db_path)
    collection = client.get_or_create_collection("project_context")
    
    print(f"Connected to DB: {db_path}")
    print(f"Total documents in collection: {collection.count()}")
    
    print("Checking for Call Graph metadata in ChromaDB...")
    results = collection.get(limit=10, include=["metadatas"])
    
    found_calls = 0
    for meta in results['metadatas']:
        filepath = meta.get('filepath', 'Unknown')
        calls_str = meta.get('calls')
        if calls_str:
            calls = json.loads(calls_str)
            if calls:
                print(f"\n[+] File: {filepath}")
                print(f"    Calls found: {calls[:10]} ... ({len(calls)} total)")
                found_calls += 1
                if found_calls >= 5: # Just show a few examples
                    break
                    
    if found_calls == 0:
        res = collection.get(limit=5, include=["metadatas"])
        if res and res['metadatas']:
            for meta in res['metadatas']:
                filepath = meta.get('filepath', '')
                calls_str = meta.get('calls')
                calls = json.loads(calls_str) if calls_str else []
                print(f"File: {filepath} | Calls keys: {len(calls)}")

if __name__ == "__main__":
    check_metadata()
