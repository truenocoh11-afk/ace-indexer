import sys, os, json, sqlite3
sys.path.insert(0, '.')

SQLITE_PATH = r'c:\Users\Julian\Documents\BoluIdeas\ACE indexer\.ace\indices\chroma_db\chroma.sqlite3'
conn = sqlite3.connect(SQLITE_PATH)

count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
print(f'Total embeddings: {count}')

# Check all DISTINCT meta keys present in the whole index
all_keys = conn.execute("SELECT DISTINCT key FROM embedding_metadata").fetchall()
print(f'\nAll meta keys in index: {[r[0] for r in all_keys]}')

# Sample one entry's full metadata
sample_id = conn.execute("SELECT id FROM embeddings LIMIT 1").fetchone()[0]
print(f'\nSample ID: {sample_id}')

meta_rows = conn.execute(
    "SELECT key, string_value, int_value, float_value FROM embedding_metadata WHERE id=?", 
    (sample_id,)
).fetchall()
print('Sample meta:')
for k, sv, iv, fv in meta_rows:
    val = sv if sv is not None else (iv if iv is not None else fv)
    print(f'  {k}: {str(val)[:80]}')

conn.close()
