
import sys, os
# Add current directory and ace_engine to path so core/ can be imported correctly
sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "ace_engine"))
from core.indexer import Indexer

indexer = Indexer()
project_path = r"c:\Users\Julian\Documents\BoluIdeas\ACE indexer"
print(f"Testing on: {project_path}")
results = indexer.query(project_path, "Indexer")

# Results from indexer.query are in format [[ {ids}, {metas}, {docs} ]] or similar depending on implementation
# Actually indexer.query returns a dict with "ids", "metadatas", "documents" where each is a list of lists (one per query)
documents = results.get("documents", [[]])[0]
metadatas = results.get("metadatas", [[]])[0]

print(f"[Test] Got {len(documents)} results")
for m in metadatas:
    print(f" - {m.get('path', '?')}")

from adapters.mcp_server import create_mcp_server
# We can't easily test call_tool directly without a full MCP setup, but we can test the formatter logic
# if we monkey-patch or simulate the context. 
# However, the user plan suggests a simple retrieval test.

print("\n--- Success Criteria: At least one file returned ---")
if len(documents) > 0:
    print("✅ PASS: Retrieval logic working.")
else:
    print("❌ FAIL: No results found.")
