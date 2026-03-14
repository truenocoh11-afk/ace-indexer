import sys, os, json
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
import chromadb

CHROMA_PATH = r'c:\Users\Julian\Documents\BoluIdeas\ACE indexer\.ace\indices\chroma_db'
client = chromadb.PersistentClient(path=CHROMA_PATH)
col = client.get_or_create_collection('project_context')
total = col.count()
print(f'Total entries in ChromaDB: {total}')

if total == 0:
    print('EMPTY INDEX — re-index did not store anything')
    sys.exit(1)

# Peek at first 3 entries
sample = col.get(limit=3, include=['metadatas', 'documents'])
for i, (mid, meta, doc) in enumerate(zip(sample['ids'], sample['metadatas'], sample['documents'])):
    print(f'\n--- Entry {i+1} ---')
    print(f'  ID: {mid[:80]}')
    print(f'  meta keys: {list(meta.keys())}')
    print(f'  path: {meta.get("path","MISSING")}')
    has_lm = 'line_map' in meta
    has_sk = 'skeleton' in meta
    print(f'  has line_map: {has_lm} | has skeleton: {has_sk}')
    if has_lm:
        lm = meta['line_map']
        parsed = json.loads(lm) if isinstance(lm, str) else lm
        print(f'  line_map keys ({len(parsed)}): {list(parsed.keys())[:5]}')
    print(f'  doc len: {len(doc or "")}')

# Check specifically for mcp_server.py entry (which has _format_compact)
print('\n--- Searching for mcp_server.py entry ---')
where_res = col.get(where={"path": {"$contains": "mcp_server"}}, limit=1, include=['metadatas'])
if where_res['ids']:
    m = where_res['metadatas'][0]
    lm = m.get('line_map', 'MISSING')
    print(f'Found. line_map: {str(lm)[:200]}')
else:
    print('mcp_server.py NOT found in index (try keyword search)')
    # Try by ID
    all_ids = col.get(limit=total, include=['metadatas'])
    mcp_entries = [(mid, meta) for mid, meta in zip(all_ids['ids'], all_ids['metadatas']) 
                   if 'mcp_server' in mid or 'mcp_server' in meta.get('path','')]
    print(f'Entries with mcp_server in path/id: {len(mcp_entries)}')
    for mid, meta in mcp_entries[:2]:
        print(f'  ID: {mid[-60:]}')
        print(f'  line_map: {str(meta.get("line_map","MISSING"))[:100]}')
