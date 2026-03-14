import asyncio
import os
import sys
import json
from collections import defaultdict

# Setup paths
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from core.indexer import Indexer

async def test_logic():
    indexer = Indexer()
    project_path = os.path.dirname(project_root) # The root of the repo
    print(f"Testing on project: {project_path}")
    
    indices_dir, _ = indexer._get_paths(project_path)
    print(f"Indices dir: {indices_dir}")
    
    collection = indexer._store.get_collection(project_path, indices_dir)
    if not collection:
        print("❌ Collection not found!")
        return

    # 1. Test Retrieval
    total_items = collection.count()
    print(f"Total items in index: {total_items}")
    
    all_metas = []
    batch_size = 2000
    for i in range(0, total_items, batch_size):
        batch = collection.get(include=["metadatas"], limit=batch_size, offset=i)
        if batch and batch.get("metadatas"):
            all_metas.extend(batch["metadatas"])
    
    print(f"Retrieved {len(all_metas)} metadatas.")
    
    # 2. Test Processing
    code_metas = [m for m in all_metas if m.get("type", "code") == "code"]
    print(f"Code files: {len(code_metas)}")
    
    modules_map = defaultdict(lambda: {"files": 0, "api_count": 0})
    global_api = []
    entry_points = []
    
    for m in code_metas:
        fpath = m.get("path", "")
        try:
            rel = os.path.relpath(fpath, project_path).replace("\\", "/")
        except:
            rel = fpath.replace("\\", "/")
        
        mod_name = rel.split("/")[0] if "/" in rel else "/"
        modules_map[mod_name]["files"] += 1
        
        if any(x in rel.lower() for x in ["main.py", "cli.py", "index.ts", "app."]):
            entry_points.append(rel)
        
        try:
            lmap = json.loads(m.get("line_map", "{}"))
        except:
            lmap = {}
        
        global_api.extend([(sym, rel, ln) for sym, ln in lmap.items()])
        modules_map[mod_name]["api_count"] += len(lmap)

    print("\n--- [MODULES] STATS ---")
    for mod, stats in sorted(modules_map.items()):
        print(f"Mod: {mod:20} | Files: {stats['files']:3} | Exports: {stats['api_count']:4}")

    print(f"\nEntry Points Found: {entry_points}")
    print(f"Total Symbols: {len(global_api)}")

    # 3. Test DEPS logic
    print("\n--- Testing Dependency Inference ---")
    deps = defaultdict(set)
    sym_file_map = {sym: rel for sym, rel, _ in global_api}
    
    for m in code_metas[:50]: # Sample for speed
        try:
            fpath = m.get("path", "")
            rel = os.path.relpath(fpath, project_path).replace("\\", "/")
            mod_source = rel.split("/")[0] if "/" in rel else "/"
            calls = json.loads(m.get("calls", "[]"))
            for c in calls:
                if c in sym_file_map:
                    mod_target = sym_file_map[c].split("/")[0] if "/" in sym_file_map[c] else "/"
                    if mod_source != mod_target:
                        deps[mod_source].add(mod_target)
        except: continue
        
    for src, tgts in sorted(deps.items()):
        print(f"{src} -> {tgts}")

if __name__ == "__main__":
    asyncio.run(test_logic())
