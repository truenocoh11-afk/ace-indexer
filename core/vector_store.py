import os
import json
import sys
import chromadb
from .exact_search import TrigramIndex

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
            
            # Phase 2: HNSW Parameter Tuning 
            hnsw_config = {
                "hnsw:space": "cosine",
                "hnsw:construction_ef": 200, 
                "hnsw:M": 32,
                "hnsw:search_ef": 100
            }

            # Phase 7D: Explicit ONNX Embedding Function (Opt B)
            embedding_function = None
            try:
                from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
                embedding_function = ONNXMiniLM_L6_V2(preferred_providers=["CPUExecutionProvider"])
            except ImportError:
                sys.stderr.write("[VectorStore] Warning: onnxruntime not found. Using default embedding function (Opt B pending).\n")
            except Exception as e:
                sys.stderr.write(f"[VectorStore] Warning: Failed to initialize ONNX embedding function: {e}\n")
            
            collection = client.get_or_create_collection(
                name="project_context", 
                metadata=hnsw_config,
                embedding_function=embedding_function
            )
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
            sys.stderr.write(f"[VectorStore] Removing {len(ids_to_delete)} stale files and their chunks.\n")
            # Phase 6: Robust cascade delete using metadata path
            collection.delete(where={"path": {"$in": ids_to_delete}})
            
            # Phase 6: Cleanup Trigram Index
            try:
                client = collection._client
                persist_dir = client._persist_directory if hasattr(client, '_persist_directory') else None
                if not persist_dir:
                    persist_dir = client._server.settings.persist_directory if hasattr(client, '_server') else None
                if persist_dir:
                    trigram_db = os.path.join(os.path.dirname(persist_dir), "trigram_index.db")
                    trigram_index = TrigramIndex(trigram_db)
                    trigram_index.delete_documents(ids_to_delete)
            except Exception as e:
                sys.stderr.write(f"[VectorStore] Trigram cleanup warning: {e}\n")

    def upsert_files(self, project_path: str, collection, files_to_index: list, skeletonizer, extract_idents_fn):
        if not files_to_index:
            return

        sys.stderr.write(f"[VectorStore] Indexing {len(files_to_index)} new/changed files.\n")
        
        client = self._chroma_clients[project_path]["client"]
        try:
            max_batch = client.get_max_batch_size()
        except AttributeError:
            max_batch = 100
            
        batch_size = min(max_batch, 5000)
        docs_buf, metas_buf, ids_buf = [], [], []
        trigram_buf = []

        # Phase 5/7: Derive trigram DB path reliably from cached ChromaDB persistent client
        try:
            persist_dir = client._client._persist_directory if hasattr(client, '_client') else None
            if not persist_dir:
                persist_dir = client._server.settings.persist_directory if hasattr(client, '_server') else None
            if persist_dir:
                trigram_db = os.path.join(os.path.dirname(persist_dir), "trigram_index.db")
            else:
                trigram_db = os.path.join(project_path, ".ace", "indices", "trigram_index.db")
        except Exception:
            trigram_db = os.path.join(project_path, ".ace", "indices", "trigram_index.db")
        
        trigram_index = TrigramIndex(trigram_db)

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
                content_lines = content.splitlines()
                
                # Phase 4: Chunking logic
                chunks = []
                chunks.append({
                    "id": filepath,
                    "content": content,
                    "metadata": {
                        "path": filepath,
                        "line": 0,
                        "type": "doc" if is_doc else "file",
                        "skeleton": skeleton,
                        "ident_bag": " ".join(extract_idents_fn(content))
                    }
                })

                if not is_doc and isinstance(line_map, list):
                    for entry in line_map:
                        symbol_name = entry.get("name")
                        start = entry.get("start_line", 1) - 1
                        end = entry.get("end_line", len(content_lines))
                        
                        if symbol_name and (end - start) > 0:
                            symbol_content = "\n".join(content_lines[start:end])
                            chunks.append({
                                "id": f"{filepath}::{symbol_name}::{start+1}",
                                "content": symbol_content,
                                "metadata": {
                                    "path": filepath,
                                    "line": start + 1,
                                    "symbol": symbol_name,
                                    "type": entry.get("type", "code"),
                                    "parent_file": filepath,
                                    "ident_bag": " ".join(extract_idents_fn(symbol_content))
                                }
                            })

                for chunk in chunks:
                    docs_buf.append(chunk["content"])
                    ids_buf.append(chunk["id"])
                    
                    # Phase 7: Buffer for batch indexing
                    trigram_buf.append((chunk["id"], chunk["content"]))
                    
                    # Common metadata + specific chunk metadata
                    meta = {
                        "remote": False,
                        "calls": json.dumps(calls),
                        "inherits": json.dumps(inherits)
                    }
                    meta.update(chunk["metadata"])
                    metas_buf.append(meta)
                    
                    if len(docs_buf) >= batch_size:
                        _flush()

            except Exception as e:
                sys.stderr.write(f"Error indexing {filepath}: {e}\n")
        
        _flush()
        # Phase 7: Final Trigram batch ingestion
        if trigram_buf:
            trigram_index.index_documents_batch(trigram_buf)

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
