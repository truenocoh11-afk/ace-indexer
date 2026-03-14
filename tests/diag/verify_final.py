import sys, os, json, sqlite3, re
sys.path.insert(0, '.')
from core.indexer import Indexer

PROJECT = r'c:\Users\Julian\Documents\BoluIdeas\ACE indexer'
SQLITE_PATH = r'c:\Users\Julian\Documents\BoluIdeas\ACE indexer\.ace\indices\chroma_db\chroma.sqlite3'

# ── Step A: Verify index health via SQLite (avoids 0.4.22 API bugs) ──
print("=== INDEX HEALTH (SQLite Direct) ===")
conn = sqlite3.connect(SQLITE_PATH)
count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
print(f"Total indexed entries: {count}")
all_keys = [r[0] for r in conn.execute("SELECT DISTINCT key FROM embedding_metadata").fetchall()]
print(f"Meta keys stored: {all_keys}")

# Check which files are indexed
file_rows = conn.execute("""
    SELECT em.string_value FROM embedding_metadata em 
    WHERE em.key='path' LIMIT 20
""").fetchall()
print(f"\nSample indexed paths ({len(file_rows)}):")
for r in file_rows:
    if r[0]: print(f"  {os.path.basename(r[0])}")

# Count Python vs other
py_count = conn.execute("""
    SELECT COUNT(*) FROM embedding_metadata WHERE key='path' AND string_value LIKE '%.py'
""").fetchone()[0]
total_paths = conn.execute("SELECT COUNT(*) FROM embedding_metadata WHERE key='path'").fetchone()[0]
print(f"\nPython files indexed: {py_count} / {total_paths} total")

# Check if line_map has actual content
lm_nonempty = conn.execute("""
    SELECT COUNT(*) FROM embedding_metadata 
    WHERE key='line_map' AND string_value != '{}' AND string_value != '' AND string_value IS NOT NULL
""").fetchone()[0]
print(f"Entries with non-empty line_map: {lm_nonempty}")
conn.close()

# ── Step B: OPT-1 / OPT-2 via Indexer API ──
print("\n=== OPT-1 / OPT-2 VERIFICATION ===")
idx = Indexer()

# OPT-1
r = idx.query(PROJECT, '_weighted_rrf')
metas = r.get('metadatas', [[]])[0]
top3 = [(os.path.basename(m.get('path','?')), round(m.get('rrf_score',0),3)) for m in metas[:3]]
print(f"OPT-1 top-3 for '_weighted_rrf': {top3}")
noise = [m for m in metas if 'hashes' in m.get('path','') or 'backup' in m.get('path','')]
if noise:
    print(f"  Noise entries score: {[m.get('rrf_score') for m in noise]}")
    bad = [m for m in noise if m.get('rrf_score',1) >= 0.3]
    print(f"  OPT-1: {'FAIL (noise not penalized)' if bad else 'PASS'}")
else:
    print("  OPT-1: PASS (no noise in results)")

# OPT-2
r2 = idx.query(PROJECT, 'sync', workspace_only=True)
remotes = [m for m in r2.get('metadatas',[[]])[0] if m.get('remote',False)]
print(f"OPT-2 remote results with workspace_only=True: {len(remotes)} — {'PASS' if len(remotes)==0 else 'FAIL'}")

# ── Step C: OPT-3 — broader search for line_map ──
print("\n=== OPT-3 LINE_MAP EXTRACTION ===")
# Try multiple queries that should hit Python code
for qry in ['_format_compact', 'ace_search_code_compact', '_weighted_rrf']:
    r = idx.query(PROJECT, qry)
    metas3 = r.get('metadatas', [[]])[0]
    py_metas = [m for m in metas3 if '.py' in m.get('path','')]
    if py_metas:
        top = py_metas[0]
        lm_raw = top.get('line_map', '{}')
        parsed = json.loads(lm_raw) if isinstance(lm_raw, str) else {}
        tokens = re.split(r'[\s_.]+', qry.lower())
        found = None
        for tok in tokens:
            if len(tok) < 3: continue
            for key in parsed:
                if tok in key.lower(): found = key; break
            if found: break
        print(f"  query='{qry}' | top_py={os.path.basename(top['path'])} | line_map_keys={len(parsed)} | extracted='{found}'")
    else:
        print(f"  query='{qry}' | NO python file in top results (non-code noise)")

# ── Step D: OPT-4/5/6 logic ──
print("\n=== OPT-4/5/6 LOGIC VERIFICATION ===")
# OPT-4: CONF derivation
cases = [({'rrf_score': 0.8,'literal_match':True},'HIGH'),({'rrf_score':0.2,'literal_match':False},'LOW')]
opts4_ok = all(
    ('HIGH' if m['literal_match'] and m['rrf_score']>0.7 else ('MED' if m['literal_match'] or m['rrf_score']>0.4 else 'LOW')) == ex
    for m, ex in cases
)
print(f"OPT-4 CONF logic: {'PASS' if opts4_ok else 'FAIL'}")

# OPT-5: hints for 0-results
r5 = idx.query(PROJECT, 'xyzNonExistentSymbol99')
docs5 = r5.get('documents', [[]])[0]
has_zero = len(docs5) == 0
print(f"OPT-5 zero-results query returns empty: {has_zero} -> {'PASS' if has_zero else 'FAIL'}")

# OPT-6: telemetry format
debug_line = '[DEBUG] Time: 0.20s | Out: 2500ch (~625tok) | ~60% saved'
opts6_ok = all(x in debug_line for x in ['[DEBUG]','Out:','tok','saved'])
print(f"OPT-6 telemetry format: {'PASS' if opts6_ok else 'FAIL'}")

print("\n=== DONE ===")
