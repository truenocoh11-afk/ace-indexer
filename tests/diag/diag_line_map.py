import sys, os, json
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from core.indexer import Indexer
idx = Indexer()
PROJECT = r'c:\Users\Julian\Documents\BoluIdeas\ACE indexer'

r = idx.query(PROJECT, '_format_compact')
metas = r.get('metadatas', [[]])[0]
print(f'Results: {len(metas)}')
if metas:
    top = metas[0]
    print(f'Top file: {os.path.basename(top.get("path","?"))}')
    lm = top.get('line_map', 'FIELD_MISSING')
    print(f'line_map raw ({type(lm).__name__}): {str(lm)[:300]}')
    sk = top.get('skeleton', 'FIELD_MISSING')
    print(f'skeleton ({len(str(sk))} chars): {str(sk)[:80]}')
    # Try parse
    try:
        parsed = json.loads(lm) if isinstance(lm, str) else lm
        print(f'line_map parsed keys ({len(parsed)}): {list(parsed.keys())[:10]}')
    except Exception as e:
        print(f'Parse error: {e}')
else:
    print('NO RESULTS for _format_compact')
