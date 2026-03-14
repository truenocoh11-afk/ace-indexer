
import sys
import os
import re
from pathlib import Path

# Add core path
current_dir = Path(__file__).resolve().parent
sys.path.append(str(current_dir.parent))

from core.indexer import Indexer

def test_query_classification():
    print("\n--- Testing Query Classification ---")
    idx = Indexer()
    
    cases = [
        ("indexer.py", "literal"),
        ("Indexer", "symbol"), # PascalCase
        ("get_files", "symbol"), # snake_case
        ("line_map", "symbol"), # snake_case
        ("handleRequest", "symbol"), # camelCase
        ("how does indexing work", "conceptual"),
        ("MAX_RETRIES", "symbol"), # CONSTANT
        ("_format_compact", "symbol"), # internal symbol
        ("print(x)", "literal"), # function call pattern
        ("sys.path", "literal"), # member access pattern
    ]
    
    passed = 0
    for q, expected in cases:
        result = idx._classify_query(q)
        if result == expected:
            print(f"✅ '{q}' -> {result}")
            passed += 1
        else:
            print(f"❌ '{q}' -> {result} (Expected: {expected})")
            
    print(f"\nPassed: {passed}/{len(cases)}")

def test_auto_usages_logic():
    print("\n--- Testing Auto Usages Logic (Mock) ---")
    # Simulate the logic in mcp_server.py
    
    # Case 1: Metadata 0 is doc, Metadata 1 is code
    metadatas = [
        {"path": "docs/api.md", "type": "doc", "line_map": "{}", "skeleton": ""},
        {"path": "core/logic.py", "type": "code", "line_map": '{"my_func": 10}', "skeleton": "def my_func(): pass"}
    ]
    
    # Logic from mcp_server.py
    best_meta = None
    for m in metadatas:
        if m.get('type') == 'code':
            best_meta = m
            break
    if not best_meta and metadatas:
        best_meta = metadatas[0]
        
    print(f"Selected metadata path: {best_meta['path']}")
    
    if best_meta['path'] == "core/logic.py":
        print("✅ Correctly prioritized 'code' file")
    else:
        print("❌ Failed to prioritize 'code' file")

if __name__ == "__main__":
    test_query_classification()
    test_auto_usages_logic()
