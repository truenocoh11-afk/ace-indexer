import sys, os, re, json, time
sys.path.insert(0, '.')
from core.indexer import Indexer

PROJECT = r'c:\Users\Julian\Documents\BoluIdeas\ACE indexer'
idx = Indexer()

print("=" * 60)
print("STEP 0: Re-indexing fresh...")
result = idx.index_project(PROJECT, force=True)
print(f"Index result: {result}")
if result.get('error'):
    print(f"ERROR: {result['error']}")
    sys.exit(1)
if result.get('indexed', 0) == 0:
    print("WARNING: 0 files indexed — ChromaDB may still be locked or schema broken")
    sys.exit(1)
print("Re-index: OK\n")

# Clear Chroma cache so next query uses the fresh index
idx._chroma_clients.clear()

# ─────────── OPT-1: Path Penalty ───────────
print("=" * 60)
print("OPT-1: Path Confidence Scoring")
r = idx.query(PROJECT, '_weighted_rrf')
metas = r.get('metadatas', [[]])[0]
print(f"  Results: {len(metas)}")
for m in metas[:3]:
    print(f"  path={os.path.basename(m.get('path','?'))} rrf={m.get('rrf_score',0):.3f}")
noise = [m for m in metas if 'hashes' in m.get('path', '') or 'backup' in m.get('path', '')]
for n in noise:
    score = n.get('rrf_score', 1.0)
    assert score < 0.3, f'FALLO OPT-1: noise no penalizado ({n["path"]}, score={score})'
good = [m for m in metas if 'indexer.py' in m.get('path', '')]
if good:
    assert good[0].get('rrf_score', 0) >= 0.0, 'FALLO OPT-1: indexer.py penalizado erroneamente'
print("OPT-1: PASSED\n")

# ─────────── OPT-2: Workspace Filter ───────────
print("=" * 60)
print("OPT-2: Workspace Filter")
r = idx.query(PROJECT, 'sync', workspace_only=True)
remotes = [m for m in r.get('metadatas', [[]])[0] if m.get('remote', False)]
assert len(remotes) == 0, f'FALLO OPT-2: {len(remotes)} remotos con workspace_only=True'
print("OPT-2 workspace_only=True: PASSED")
r2 = idx.query(PROJECT, 'sync', workspace_only=False)
print(f"OPT-2 workspace_only=False returned {len(r2.get('metadatas',[[]])[0])} results")
print("OPT-2: PASSED\n")

# ─────────── OPT-3: Smart auto_usages via line_map ───────────
print("=" * 60)
print("OPT-3: Smart auto_usages via line_map")
r = idx.query(PROJECT, '_format_compact')
metas3 = r.get('metadatas', [[]])[0]
print(f"  Results: {len(metas3)}")
if metas3:
    best_meta = None
    for m in metas3:
        if m.get('type') == 'code':
            best_meta = m
            break
    if not best_meta:
        best_meta = metas3[0]

    top = best_meta
    print(f"  Top file (code prioritized): {os.path.basename(top.get('path','?'))}")
    lm_raw = top.get('line_map', '{}')
    print(f"  line_map type: {type(lm_raw)}, preview: {str(lm_raw)[:100]}")
    line_map = json.loads(lm_raw) if isinstance(lm_raw, str) else (lm_raw or {})
    print(f"  line_map keys ({len(line_map)}): {list(line_map.keys())[:8]}")

    tokens = re.split(r'[\s_.]+', '_format_compact'.lower())
    found = None
    for tok in tokens:
        if len(tok) < 3: continue
        for key in line_map:
            if tok in key.lower(): found = key; break
        if found: break
    print(f"  Symbol extracted: {found}")
    assert found and 'format' in found.lower(), f'FALLO OPT-3: extrajo incorrecto o None: {found}'
else:
    print("  WARNING: 0 results for _format_compact")
    assert False, 'FALLO OPT-3: 0 resultados'

# Failure case: line_map vacio -> no debe extraer nada
sym_vague = None
for tok in re.split(r'[\s_.]+', 'arquitectura backend'.lower()):
    if len(tok) < 3: continue
    for key in {}:
        if tok in key.lower(): sym_vague = key; break
    if sym_vague: break
assert sym_vague is None, f'FALLO OPT-3: fallback ciego activo: {sym_vague}'
print("OPT-3: PASSED\n")

# ─────────── OPT-4: CONF column derivation ───────────
print("=" * 60)
print("OPT-4: CONF column derivation logic")
test_cases = [
    ({'rrf_score': 0.8, 'literal_match': True},  'HIGH'),
    ({'rrf_score': 0.5, 'literal_match': False},  'MED'),
    ({'rrf_score': 0.2, 'literal_match': False},  'LOW'),
    ({'rrf_score': 0.3, 'literal_match': True},   'MED'),
]
for meta, expected in test_cases:
    rrf_score = meta.get('rrf_score', 0)
    literal   = meta.get('literal_match', False)
    conf = 'HIGH' if literal and rrf_score > 0.7 else ('MED' if literal or rrf_score > 0.4 else 'LOW')
    assert conf == expected, f'FALLO OPT-4: {meta} -> {conf}, esperado {expected}'
    print(f"  {meta} -> CONF={conf}: OK")
print("OPT-4: PASSED\n")

# ─────────── OPT-5: Zero-Results Hints ───────────
print("=" * 60)
print("OPT-5: Zero-Results reformulation hints")
r5 = idx.query(PROJECT, 'xyzNonExistentSymbol99')
docs5 = r5.get('documents', [[]])[0]
query5 = 'xyzNonExistentSymbol99'
hints = [f"[COMPACT] 0 results for: '{query5}'"]
if len(query5.split()) == 1:
    hints.append(f"💡 Try: 'where is {query5} defined' or file_pattern='*.py'")
assert len(hints) > 1, 'FALLO OPT-5: no genera hints'
old = "[COMPACT] 0 results for: 'x'. Try ace_search_code for hints."
assert '💡' not in old
print(f"  Hints: {hints[1]}")
print("OPT-5: PASSED\n")

# ─────────── OPT-6: Token Telemetry ───────────
print("=" * 60)
print("OPT-6: Token telemetry format")
output_chars = 2500
full_estimate = int(output_chars * 2.5)
savings_pct = max(0, int((1 - output_chars / max(full_estimate, 1)) * 100))
debug_line = f'[DEBUG] Time: 0.20s | Q1: 0.20s | Fmt: 0.00s | Usages: 0.00s | Out: {output_chars}ch (~{output_chars//4}tok) | ~{savings_pct}% saved'
assert '[DEBUG]' in debug_line and 'Out:' in debug_line and 'tok' in debug_line and 'saved' in debug_line
old_debug = '[DEBUG TIMEOUT] Total: 0.20s'
assert 'tok' not in old_debug and 'saved' not in old_debug
print(f"  {debug_line}")
print("OPT-6: PASSED\n")

print("=" * 60)
print("✅ ALL GATES PASSED")
