"""
POC Test: Validate ACE Compact optimization ideas against live ChromaDB data.
Run from: ace_engine/ directory
Usage: python ../test_optimizations_poc.py
"""
import sys, os, re, json, time

# Setup paths
ace_root = os.path.dirname(os.path.abspath(__file__))
ace_engine = os.path.join(ace_root, "ace_engine")
sys.path.insert(0, ace_engine)

from core.indexer import Indexer

PROJECT_PATH = ace_root
indexer = Indexer()

print("=" * 60)
print("ACE COMPACT OPTIMIZATION — POC TESTS")
print("=" * 60)

# ── TEST 1: Path Confidence Scoring (OPT-1) ────────────────
print("\n## TEST 1: Path Confidence Scoring (OPT-1)")
print("Simulate path-based penalty for noise paths")

NOISE_PATH_PATTERNS = [
    r'[\\/]data[\\/]hashes[\\/]',
    r'[\\/]backup',
    r'[\\/]legacy',
    r'\.(bak|old|orig)$',
    r'[\\/]\.ace[\\/]',
]

def path_penalty(filepath: str) -> float:
    """Returns a penalty (negative) for paths that are likely noise."""
    for pattern in NOISE_PATH_PATTERNS:
        if re.search(pattern, filepath, re.IGNORECASE):
            return -0.3
    return 0.0

# Run a query that previously returned noise
results = indexer.query(PROJECT_PATH, "_format_compact")
ids = results["ids"][0]
metas = results["metadatas"][0]

print(f"  Query: '_format_compact' → {len(ids)} results")
for i, (doc_id, meta) in enumerate(zip(ids, metas)):
    penalty = path_penalty(meta.get("path", doc_id))
    original_score = meta.get("rrf_score", 0)
    adjusted = original_score + penalty
    tag = " ⚠️ PENALIZED" if penalty < 0 else ""
    print(f"  [{i+1}] score={original_score:.3f} adj={adjusted:.3f}{tag} → {os.path.relpath(meta.get('path', doc_id), PROJECT_PATH)}")

# ── TEST 2: Workspace-Only Filter (OPT-2) ──────────────────
print("\n## TEST 2: Workspace-Only Filter (OPT-2)")
print("Check how many remote results exist in the index")

try:
    # Use indexer's cached collection (avoids version mismatch)
    collection = indexer._get_chroma_collection(PROJECT_PATH)
    if collection:
        try:
            remotes = collection.get(where={"remote": True}, include=["metadatas"])
            remote_count = len(remotes["ids"])
            print(f"  Remote entries in index: {remote_count}")
            if remote_count > 0:
                for rid, rmeta in zip(remotes["ids"][:5], remotes["metadatas"][:5]):
                    print(f"    → {rmeta.get('env', '?')}: {rmeta.get('path', rid)[:80]}")
        except Exception as e:
            print(f"  No remote entries found ({e})")
            remote_count = 0
        total = collection.count()
        print(f"  Total entries: {total} | Local: {total - remote_count} | Remote: {remote_count}")
        print(f"  ✅ Workspace-only filter would exclude {remote_count} entries by default")
    else:
        print("  ⚠️ Collection not available")
        remote_count = 0
        total = 0
except Exception as e:
    print(f"  ❌ ChromaDB Error: {e}")
    remote_count = 0
    total = 0

# ── TEST 3: Smart auto_usages Symbol Extraction (OPT-3) ────
print("\n## TEST 3: Smart auto_usages Symbol Extraction (OPT-3)")
print("Compare current vs proposed symbol extraction")

query = "_format_compact"
results = indexer.query(PROJECT_PATH, query)
docs = results["documents"][0]
metas = results["metadatas"][0]

if docs:
    # CURRENT: regex on full file content (documents[0])
    sym_match_current = re.search(
        r'(?:function|class|def|const|let|var|export function)\s+([a-zA-Z0-9_]+)',
        docs[0]
    )
    current_symbol = sym_match_current.group(1) if sym_match_current else None
    
    # PROPOSED: use line_map to match query tokens
    line_map_raw = metas[0].get("line_map", "{}")
    try:
        line_map = json.loads(line_map_raw) if isinstance(line_map_raw, str) else line_map_raw
    except:
        line_map = {}
    
    proposed_symbol = None
    query_tokens = query.replace("(", " ").replace(")", " ").replace(".", " ").split()
    for token in query_tokens:
        for key in line_map.keys():
            if token.lower() in key.lower() or key.lower() in token.lower():
                proposed_symbol = key
                break
        if proposed_symbol:
            break
    
    # If no line_map match, try skeleton-based extraction
    if not proposed_symbol:
        skeleton = metas[0].get("skeleton", "")
        for token in query_tokens:
            sk_match = re.search(rf'def\s+({re.escape(token)}[a-zA-Z0-9_]*)', skeleton)
            if sk_match:
                proposed_symbol = sk_match.group(1)
                break
    
    print(f"  Query: '{query}'")
    print(f"  CURRENT method (regex on docs[0]): → '{current_symbol}'")
    print(f"  PROPOSED method (line_map match): → '{proposed_symbol}'")
    print(f"  Available line_map keys: {list(line_map.keys())[:10]}")
    
    if proposed_symbol and proposed_symbol != current_symbol:
        print(f"  ✅ IMPROVEMENT: Would search for '{proposed_symbol}' instead of '{current_symbol}'")
    elif proposed_symbol == query:
        print(f"  ✅ CORRECT: Query matches symbol directly, skip DOMINO (avoid self-reference)")
    else:
        print(f"  ⚠️  No improvement found — both methods yield same result or no match")

# ── TEST 4: Confidence Scoring (OPT-4) ─────────────────────
print("\n## TEST 4: Confidence Scoring (OPT-4)")
print("Derive confidence labels from existing rrf_score + literal_match")

results = indexer.query(PROJECT_PATH, "_format_compact")
ids = results["ids"][0]
metas = results["metadatas"][0]

for i, (doc_id, meta) in enumerate(zip(ids, metas)):
    score = meta.get("rrf_score", 0)
    literal = meta.get("literal_match", False)
    
    if literal and score > 0.7:
        conf = "HIGH"
    elif literal or score > 0.4:
        conf = "MED"
    else:
        conf = "LOW"
    
    path = os.path.relpath(meta.get("path", doc_id), PROJECT_PATH)
    print(f"  [{i+1}] CONF={conf} (score={score:.3f}, literal={literal}) → {path}")

# ── TEST 5: Zero-Results Reformulation (OPT-5) ─────────────
print("\n## TEST 5: Zero-Results Reformulation (OPT-5)")
print("Test with a query that returns 0 results")

zero_test_queries = [
    "xyzNonExistentSymbol12345",
    "database_migration_rollback",
]

for q in zero_test_queries:
    results = indexer.query(PROJECT_PATH, q)
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    
    if not docs:
        meta = metas[0] if metas else {}
        n_indexed = meta.get("indexed_files", "?")
        missing = meta.get("missing_files", [])
        
        # Simulate reformulation hints
        hints = []
        special_chars = set("().'\"\\")
        if any(c in special_chars for c in q):
            hints.append("Try a conceptual query instead of code literal")
        if "_" in q:
            # Suggest splitting snake_case
            parts = q.split("_")
            hints.append(f"Try separate words: '{' '.join(parts)}'")
        if len(q.split()) == 1:
            hints.append(f"Try broader: 'where is {q} defined' or 'function {q}'")
        
        print(f"  Query: '{q}' → 0 results")
        print(f"  Index: {n_indexed} files")
        if hints:
            print(f"  💡 REFORMULATE: {hints[0]}")
        if missing:
            print(f"  📁 Unindexed files found on disk: {len(missing)}")
    else:
        print(f"  Query: '{q}' → {len(docs)} results (not zero, skip)")

# ── TEST 6: Token Telemetry (OPT-6) ────────────────────────
print("\n## TEST 6: Token Telemetry (OPT-6)")
print("Measure output size: compact vs full")

results = indexer.query(PROJECT_PATH, "_format_compact")
docs = results["documents"][0]
metas = results["metadatas"][0]

# Simulate compact output
sys.path.insert(0, ace_engine)
from adapters.mcp_server import create_mcp_server
# Can't call _format_compact directly in this scope, so simulate
compact_lines = []
compact_lines.append(f"[SEARCH: _format_compact] [RESULTS: {len(docs)}]")
compact_lines.append("FILE\tTYPE\tFLAGS\tLOCATION\tSNIPPET_CHARS")
for doc, meta in zip(docs, metas):
    path = os.path.relpath(meta.get("path", ""), PROJECT_PATH)
    snippet_len = min(len(doc), 600)
    compact_lines.append(f"{path}\tcode\t-\t-\t{snippet_len}")
compact_lines.append("\n===SOURCES===")
for doc, meta in zip(docs, metas):
    path = os.path.relpath(meta.get("path", ""), PROJECT_PATH)
    skeleton = meta.get("skeleton", "")
    limit = 400
    compact_lines.append(f"--- {path} ---")
    if skeleton and len(skeleton) > 50:
        compact_lines.append(skeleton[:limit])
    else:
        compact_lines.append(doc[:limit])

compact_output = "\n".join(compact_lines)

# Full output (simulated — all docs truncated at 1500 chars)
full_output = "\n".join([
    f"--- File: {meta.get('path', '')} ---\n{doc[:1500]}\n{'='*20}"
    for doc, meta in zip(docs, metas)
])

compact_chars = len(compact_output)
full_chars = len(full_output)
savings_pct = round((1 - compact_chars / max(full_chars, 1)) * 100)

print(f"  Compact output: {compact_chars} chars (~{compact_chars // 4} tokens)")
print(f"  Full output: {full_chars} chars (~{full_chars // 4} tokens)")
print(f"  Token savings: ~{savings_pct}%")

print("\n" + "=" * 60)
print("ALL POC TESTS COMPLETE")
print("=" * 60)
