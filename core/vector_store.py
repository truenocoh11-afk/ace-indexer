import os
import json
import sys
import chromadb

# --- ChromaDB 0.4.22 Bug Workaround ---
# In Python 3.12, sqlite3 might return an int for seq_id instead of bytes,
# which causes `len(seq_id_bytes)` to throw `TypeError` inside `_decode_seq_id`.
try:
    import chromadb.segment.impl.metadata.sqlite
    _old_decode = chromadb.segment.impl.metadata.sqlite._decode_seq_id
    def _safe_decode_seq_id(seq_id_bytes):
        if isinstance(seq_id_bytes, int):
            seq_id_bytes = seq_id_bytes.to_bytes(8, 'little')
        return _old_decode(seq_id_bytes)
    chromadb.segment.impl.metadata.sqlite._decode_seq_id = _safe_decode_seq_id
except Exception:
    pass
# ------------------------------------

class VectorStore:
    def __init__(self):
        # [v4.0 Phase B] Optimización de latencia: Caché de clientes ChromaDB
        self._chroma_clients = {}

    def get_collection(self, project_path: str, indices_dir: str):
        """Devuelve una colección de ChromaDB cacheadada por proyecto."""
        if project_path in self._chroma_clients:
            return self._chroma_clients[project_path]["collection"]
            
        try:
            client = chromadb.PersistentClient(path=os.path.join(indices_dir, "chroma_db"))
            collection = client.get_or_create_collection(name="project_context")
            # Cacheamos tanto el cliente como la colección
            self._chroma_clients[project_path] = {
                "client": client,
                "collection": collection
            }
            return collection
        except Exception as e:
            sys.stderr.write(f"[VectorStore] Error inicializando ChromaDB para {project_path}: {e}\n")
            return None

    def delete_stale(self, collection, ids_to_delete: list):
        if ids_to_delete:
            sys.stderr.write(f"[VectorStore] Removing {len(ids_to_delete)} stale files.\n")
            collection.delete(ids=ids_to_delete)

    def upsert_files(self, project_path: str, collection, files_to_index: list, skeletonizer, extract_idents_fn):
        if not files_to_index:
            return

        sys.stderr.write(f"[VectorStore] Indexing {len(files_to_index)} new/changed files.\n")
        
        client = self._chroma_clients[project_path]["client"]
        try:
            max_batch = client.get_max_batch_size()
        except AttributeError:
            max_batch = 100
            
        batch_size = min(max_batch, 500)
        docs_buf, metas_buf, ids_buf = [], [], []

        def _flush():
            if docs_buf:
                collection.upsert(documents=docs_buf[:], metadatas=metas_buf[:], ids=ids_buf[:])
                docs_buf.clear(); metas_buf.clear(); ids_buf.clear()

        for filepath in files_to_index:
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                
                skeleton, line_map, calls, inherits = skeletonizer.skeletonize(content, filepath)
                
                is_doc = filepath.endswith((".md", ".txt", ".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".env"))
                
                metas_buf.append({
                    "path": filepath,
                    "remote": False,
                    "skeleton": skeleton,
                    "line_map": json.dumps(line_map),
                    "calls": json.dumps(calls),
                    "inherits": json.dumps(inherits),
                    "type": "doc" if is_doc else "code",
                    "ident_bag": " ".join(extract_idents_fn(content))
                })
                docs_buf.append(content)
                ids_buf.append(filepath)
                
                if len(docs_buf) >= batch_size:
                    _flush()
            except Exception as e:
                sys.stderr.write(f"Error indexing {filepath}: {e}\n")
        
        _flush()

    def upsert_remote_data(self, project_path: str, collection, remote_data: dict):
        """Incorporate remote file snippets into the local vector index."""
        env_name = remote_data.get("env_name", "remote")
        files = remote_data.get("files", [])
        
        sys.stderr.write(f"[VectorStore] Indexing remote data for env: {env_name}\n")
        
        documents = []
        metadatas = []
        ids = []
        
        for f in files:
            path = f["path"]
            snippet = f["snippet"]
            remote_id = f"remote://{env_name}/{path}"
            
            documents.append(snippet)
            metadatas.append({
                "path": path,
                "env": env_name,
                "remote": True,
                "type": "code",
                "hash": f.get("hash", "")
            })
            ids.append(remote_id)
            
        # Batch add
        batch_size = 100
        for i in range(0, len(documents), batch_size):
            collection.upsert(
                documents=documents[i:i+batch_size],
                metadatas=metadatas[i:i+batch_size],
                ids=ids[i:i+batch_size]
            )
            
        return len(documents)
