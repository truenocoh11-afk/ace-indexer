import os
import json
import sys
import time
from .skeletonizer import Skeletonizer
from .scanner import FileScanner
from .vector_store import VectorStore
from .search_engine import SearchEngine

class Indexer:
    def __init__(self):
        self.skeletonizer = Skeletonizer()
        self._scanner = FileScanner()
        self._store = VectorStore()
        self._engine = SearchEngine()

    def _get_ace_path(self, project_path: str) -> str:
        return os.path.join(project_path, ".ace")

    def _ensure_gitignore(self, ace_path: str):
        """Ensures .ace folder has a .gitignore to prevent committing indices."""
        gitignore_path = os.path.join(ace_path, ".gitignore")
        if not os.path.exists(gitignore_path):
            with open(gitignore_path, "w") as f:
                f.write("*\n!.gitignore\n")

    def _get_paths(self, project_path: str):
        ace_path = self._get_ace_path(project_path)
        indices_dir = os.path.join(ace_path, "indices")
        hashes_path = os.path.join(ace_path, "hashes.json")
        
        os.makedirs(indices_dir, exist_ok=True)
        self._ensure_gitignore(ace_path)
        
        return indices_dir, hashes_path

    def _load_hashes(self, hashes_path: str) -> dict:
        if os.path.exists(hashes_path):
            with open(hashes_path, "r") as f:
                return json.load(f)
        return {}

    def _save_hashes(self, hashes_path: str, hashes: dict):
        with open(hashes_path, "w") as f:
            json.dump(hashes, f, indent=2)

    def index_project(self, project_path: str, force: bool = False, extra_ignore_dirs: list = None):
        start_time = time.time()
        sys.stderr.write(f"[Indexer] Indexing project: {project_path}\n")
        
        indices_dir, hashes_path = self._get_paths(project_path)
        collection = self._store.get_collection(project_path, indices_dir)
        
        if not collection: 
            return {"indexed": 0, "deleted": 0, "duration_seconds": 0.0, "error": "ChromaDB Init Failed"}
            
        known_hashes = self._load_hashes(hashes_path)
        
        # Phase 1: Scan
        files_to_index, ids_to_delete, new_hashes = self._scanner.scan_files(
            project_path, known_hashes, force, extra_ignore_dirs
        )
        
        # Phase 2: Upsert/Delete
        self._store.delete_stale(collection, ids_to_delete)
        self._store.upsert_files(
            project_path, collection, files_to_index, 
            self.skeletonizer, self._engine.extract_identifiers
        )

        self._save_hashes(hashes_path, new_hashes)
        duration = time.time() - start_time
        return {
            "indexed": len(files_to_index),
            "deleted": len(ids_to_delete),
            "duration_seconds": round(duration, 2)
        }

    def index_remote_data(self, project_path: str, remote_data: dict):
        indices_dir, _ = self._get_paths(project_path)
        collection = self._store.get_collection(project_path, indices_dir)
        if not collection: return
        count = self._store.upsert_remote_data(project_path, collection, remote_data)
        return {"indexed": count, "env": remote_data.get("env_name", "remote")}

    def get_index_status(self, project_path: str):
        indices_dir, hashes_path = self._get_paths(project_path)
        if not os.path.exists(hashes_path):
            return {"status": "error", "message": "Index does not exist for this project."}
            
        known_hashes = self._load_hashes(hashes_path)
        last_update = os.path.getmtime(hashes_path)
        files_on_disk = self._scanner.list_files_on_disk(project_path)
        missing_from_index = [f for f in files_on_disk if f not in known_hashes]
        
        return {
            "status": "ok",
            "indexed_files_count": len(known_hashes),
            "last_update": last_update,
            "missing_from_index_count": len(missing_from_index),
            "missing_files_sample": missing_from_index[:10]
        }

    def list_indexed_files(self, project_path: str, pattern: str = None):
        _, hashes_path = self._get_paths(project_path)
        known_hashes = self._load_hashes(hashes_path)
        files = list(known_hashes.keys())
        if pattern:
            files = [f for f in files if self._engine.matches_file_pattern(f, project_path, pattern)]
        return files

    def query(self, project_path: str, query_text: str, n_results: int = 5, file_pattern: str = None, workspace_only: bool = True):
        t_start = time.time()
        indices_dir, hashes_path = self._get_paths(project_path)
        
        # Auto-Index logic
        known_hashes = self._load_hashes(hashes_path)
        if not known_hashes or (time.time() - os.path.getmtime(hashes_path) > 86400):
            self.index_project(project_path)
            known_hashes = self._load_hashes(hashes_path)

        collection = self._store.get_collection(project_path, indices_dir)
        if not collection: return {"ids": [], "metadatas": [], "documents": []}

        query_type = self._engine.classify_query(query_text)
        
        # 1. Filename Search
        filename_matches = []
        query_lower = query_text.lower()
        all_paths = [(p, False, None) for p in known_hashes.keys()]
        
        if not workspace_only:
            try:
                remotes = collection.get(where={"remote": True}, include=["metadatas"])
                for meta, rid in zip(remotes["metadatas"], remotes["ids"]):
                    all_paths.append((meta["path"], True, rid))
            except Exception: pass

        for path, is_remote, rid in all_paths:
            if not self._engine.matches_file_pattern(path, project_path, file_pattern): continue
            
            internal_id = rid if is_remote else path
            filename = os.path.basename(path).lower()
            rel_path = path.lower() if is_remote else os.path.relpath(path, project_path).lower()
            
            score = 0
            if query_lower == filename: score = 10
            elif query_lower in filename: score = 5
            elif query_lower in rel_path: score = 2
            
            if score > 0:
                filename_matches.append({"id": internal_id, "score": score, "remote": is_remote})
        
        # 2. Hybrid Search
        vector_results = []
        if query_type == 'literal':
            literal_results = self._engine.grep_search(project_path, query_text, file_pattern, collection, workspace_only)
            # Add small vector search for hybrid context
            try:
                v_res = collection.query(query_texts=[query_text], n_results=n_results * 5, where={"remote": False} if workspace_only else None)
                for vid in v_res.get("ids", [[]])[0]:
                    if self._engine.matches_file_pattern(vid, project_path, file_pattern):
                        vector_results.append({"id": vid})
            except Exception: pass
            
            for match in literal_results:
                existing = next((f for f in filename_matches if f["id"] == match["id"]), None)
                if existing: existing["score"] += 1.0
                else: filename_matches.append({"id": match["id"], "score": 0.8, "remote": match["remote"]})
        else:
            try:
                v_res = collection.query(query_texts=[query_text], n_results=n_results * 10, where={"remote": False} if workspace_only else None)
                for vid in v_res.get("ids", [[]])[0]:
                    if self._engine.matches_file_pattern(vid, project_path, file_pattern):
                        vector_results.append({"id": vid})
            except Exception: pass
            
            literal_results = self._engine.grep_search(project_path, query_text, file_pattern, collection, workspace_only)
            for match in literal_results:
                if not any(v["id"] == match["id"] for v in vector_results):
                    filename_matches.append({"id": match["id"], "score": 3, "remote": match["remote"]})

        # 3. Fusion & Ranking
        w_file, w_vec = (50.0, 1.0) if query_type == 'literal' else (10.0, 5.0) if query_type == 'symbol' else (3.0, 5.0)
        final_ids, rrf_scores = self._engine.weighted_rrf(filename_matches, vector_results, w_file=w_file, w_vec=w_vec)
        
        # Penalties
        for fid in final_ids:
            item = next((f for f in filename_matches if f["id"] == fid), None)
            is_rem = item["remote"] if item else fid.startswith("remote://")
            rrf_scores[fid] += self._engine.path_penalty(fid, is_rem, workspace_only)

        # 4. Meta Boosts
        metadatas_lookup = {}
        if final_ids:
            meta_res = collection.get(ids=final_ids[:30], include=["metadatas"])
            metadatas_lookup = {mid: meta for mid, meta in zip(meta_res["ids"], meta_res["metadatas"])}

        identifiers = self._engine.extract_identifiers(query_text)
        if identifiers:
            final_ids, rrf_scores = self._engine.word_boost(final_ids, rrf_scores, identifiers, metadatas_lookup)
            final_ids, rrf_scores = self._engine.declaration_boost(final_ids, rrf_scores, identifiers, metadatas_lookup)
            
        if query_type == 'symbol':
            for fid in final_ids:
                rrf_scores[fid] += 0.5 if metadatas_lookup.get(fid, {}).get("type") == 'code' else -0.8
            
        if query_type == 'conceptual':
            keywords = self._engine.extract_keywords(query_text)
            final_ids, rrf_scores = self._engine.rerank_results(final_ids, rrf_scores, keywords, metadatas_lookup)

        # 5. Build Result
        res_ids, res_metas, res_docs = [], [], []
        for doc_id in final_ids:
            if len(res_ids) >= n_results: break
            try:
                fm_item = next((f for f in filename_matches if f["id"] == doc_id), None)
                is_remote = fm_item["remote"] if fm_item else doc_id.startswith("remote://")
                
                if not is_remote:
                    with open(doc_id, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    if not fm_item and self._engine.is_low_quality(content, doc_id): continue
                    
                    meta_entry = metadatas_lookup.get(doc_id, {})
                    sk = meta_entry.get("skeleton", "")
                    lm = meta_entry.get("line_map", "{}")
                    display_path = doc_id
                    env = None
                    
                    # Line match tracking
                    qt_lower = query_text.lower()
                    match_line = next((i + 1 for i, l in enumerate(content.splitlines()) if qt_lower in l.lower()), 0)
                    if match_line == 0:
                        for ident in identifiers:
                            match_line = next((i + 1 for i, l in enumerate(content.splitlines()) if ident.lower() in l.lower()), 0)
                            if match_line: break
                else:
                    remote_entry = collection.get(ids=[doc_id], include=["documents", "metadatas"])
                    content = remote_entry["documents"][0]
                    display_path = remote_entry["metadatas"][0]["path"]
                    env = remote_entry["metadatas"][0]["env"]
                    sk, lm, match_line = "", "{}", 0

                res_ids.append(doc_id)
                res_metas.append({
                    "path": display_path, "boosted": bool(fm_item), "remote": is_remote, "env": env,
                    "rrf_score": rrf_scores[doc_id], "line": match_line, "skeleton": sk, "line_map": lm,
                    "type": metadatas_lookup.get(doc_id, {}).get("type", "code")
                })
                res_docs.append(content)
            except Exception: continue

        sys.stderr.write(f"[QUERY] Total {time.time()-t_start:.3f}s\n")
        return {"ids": [res_ids], "metadatas": [res_metas], "documents": [res_docs]}
