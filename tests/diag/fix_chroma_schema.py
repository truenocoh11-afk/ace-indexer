import sqlite3, os

base = r'c:\Users\Julian\Documents\BoluIdeas\ACE indexer\.ace\indices\chroma_db'
db_path = os.path.join(base, 'chroma.sqlite3')
print(f'DB path: {db_path}')
print(f'Exists: {os.path.exists(db_path)}')

if not os.path.exists(db_path):
    print('ERROR: chroma.sqlite3 not found at expected path')
    import sys; sys.exit(1)

conn = sqlite3.connect(db_path, timeout=10)
conn.execute('PRAGMA journal_mode=WAL')

cur = conn.execute("PRAGMA table_info(collections)")
cols = [row[1] for row in cur.fetchall()]
print(f'Columns in collections: {cols}')

if 'topic' not in cols:
    conn.execute('ALTER TABLE collections ADD COLUMN topic TEXT')
    conn.commit()
    print('SUCCESS: Added column "topic". Schema patched.')
else:
    print('Column "topic" already exists, no patch needed.')

conn.close()
print('DONE')
