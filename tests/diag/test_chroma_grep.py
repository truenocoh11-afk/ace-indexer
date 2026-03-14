import os, sys, time
sys.path.append(os.getcwd())
import chromadb

indices_dir = os.path.join(os.getcwd(), '.ace', 'indices')
client = chromadb.PersistentClient(path=os.path.join(indices_dir, 'chroma_db'))
col = client.get_collection(name='project_context')

tests = [
    ("literal identifier", "_weighted_rrf"),
    ("plain URL fragment", "http"),
    ("port number", "8080"),
]

for label, query in tests:
    print(f"\n--- Test: {label} ('{query}') ---")
    t0 = time.time()
    res = col.get(where_document={"$contains": query}, include=["metadatas"])
    elapsed = (time.time() - t0) * 1000
    names = [os.path.basename(m["path"]) for m in res["metadatas"][:5]]
    print(f"Found {len(res['ids'])} files in {elapsed:.0f}ms")
    print(f"  Sample: {names}")
