import os
import hashlib
import json
import chromadb
from chromadb.config import Settings
from .skeletonizer import Skeletonizer

class Indexer:
    def __init__(self):
        # Indexer is now stateless regarding "data_dir". 
        # It calculates paths based on the project being indexed.
        self.skeletonizer = Skeletonizer()

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

    def _compute_file_hash(self, filepath: str) -> str:
        hasher = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception:
            return ""

    def index_project(self, project_path: str, force: bool = False):
        print(f"[Indexer] Indexing project: {project_path}")
        
        indices_dir, hashes_path = self._get_paths(project_path)
        
        # Initialize Chroma for this project (Stored locally in .ace/indices)
        client = chromadb.PersistentClient(path=os.path.join(indices_dir, "chroma_db"))
        collection = client.get_or_create_collection(name="project_context")

        known_hashes = self._load_hashes(hashes_path)
        new_hashes = {}
        
        files_to_index = []
        ids_to_delete = []

        # Walk files
        for root, dirs, files in os.walk(project_path):
            if "venv" in dirs: dirs.remove("venv")
            if ".git" in dirs: dirs.remove(".git")
            if "__pycache__" in dirs: dirs.remove("__pycache__")
            if "node_modules" in dirs: dirs.remove("node_modules")
            if ".ace" in dirs: dirs.remove(".ace") # CRITICAL: Ignore our own storage
            
            # Legacy ignore (if running self-test)
            # if "ace_engine" in root: continue 
            
            for file in files:
                if not file.endswith((
                    # Frontend / Web
                    ".html", ".htm", ".css", ".scss", ".less", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte",
                    # Backend / Scripting
                    ".py", ".php", ".rb", ".go", ".java", ".cs", ".rs", ".kt", ".swift", ".dart", ".sh",
                    # Data / Config
                    ".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".env", ".sql", ".md", ".txt"
                )): continue
                
                filepath = os.path.join(root, file)
                current_hash = self._compute_file_hash(filepath)
                new_hashes[filepath] = current_hash
                
                if force or known_hashes.get(filepath) != current_hash:
                    files_to_index.append(filepath)
        
        # Detect deleted files
        for path in known_hashes:
            if path not in new_hashes:
                ids_to_delete.append(path)

        # Process Deletions
        if ids_to_delete:
            print(f"[Indexer] Removing {len(ids_to_delete)} stale files.")
            collection.delete(ids=ids_to_delete)

        # Process Additions/Updates
        if files_to_index:
            print(f"[Indexer] Indexing {len(files_to_index)} new/changed files.")
            documents = []
            metadatas = []
            ids = []
            
            for filepath in files_to_index:
                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    
                    skeleton = self.skeletonizer.skeletonize(content)
                    
                    documents.append(content)
                    metadatas.append({
                        "path": filepath, 
                        "skeleton": skeleton,
                        "type": "code"
                    })
                    ids.append(filepath)
                except Exception as e:
                    print(f"Error indexing {filepath}: {e}")

            # Batch add
            batch_size = 100
            for i in range(0, len(documents), batch_size):
                collection.upsert(
                    documents=documents[i:i+batch_size],
                    metadatas=metadatas[i:i+batch_size],
                    ids=ids[i:i+batch_size]
                )

        self._save_hashes(hashes_path, new_hashes)
        return {"indexed": len(files_to_index), "deleted": len(ids_to_delete)}

    def _is_low_quality(self, content: str, path: str) -> bool:
        """Heuristic to detect minified files, large data, or low-info content."""
        if not content: return True
        
        # 1. Minified Check (Avg line length)
        lines = content.splitlines()
        if lines:
            avg_len = len(content) / len(lines)
            if avg_len > 300: return True
            
        # 2. Extension Penalty (Large data files)
        if path.lower().endswith((".json", ".map", ".xml", ".csv")):
            if len(content) > 50000: return True # 50KB+ data files are noisy
            
        return False

    def _weighted_rrf(self, filename_results: list, vector_results: list, k: int = 60, w_file: float = 3.0, w_vec: float = 1.0) -> list:
        """Reciprocal Rank Fusion with weights for hybrid ranking."""
        scores = {} # path -> score
        
        # Process Filename Results
        for rank, item in enumerate(filename_results, start=1):
            path = item["id"]
            scores[path] = scores.get(path, 0.0) + (w_file / (k + rank))

        # Process Vector Results
        for rank, item in enumerate(vector_results, start=1):
            path = item["id"]
            # If we already have a score, we add vector score to it
            scores[path] = scores.get(path, 0.0) + (w_vec / (k + rank))

        # Sort by score descending
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        return sorted_ids, scores

    def query(self, project_path: str, query_text: str, n_results: int = 5):
        indices_dir, hashes_path = self._get_paths(project_path)
        
        if not os.path.exists(indices_dir):
             return {"ids": [], "metadatas": [], "documents": []}

        # 1. Filename Search (Keyword)
        known_hashes = self._load_hashes(hashes_path)
        filename_matches = []
        query_lower = query_text.lower()
        
        # Basic heuristic: if query contains extension, boost exact extension matches
        # or if query looks like a path
        
        for path in known_hashes:
            filename = os.path.basename(path).lower()
            rel_path = os.path.relpath(path, project_path).lower()
            
            # Weighted matching for Filename Rank
            match_score = 0
            if query_lower == filename: match_score = 10 # Exact filename
            elif query_lower in filename: match_score = 5 # Partial filename
            elif query_lower in rel_path: match_score = 2 # Partial path
            
            if match_score > 0:
                filename_matches.append({"id": path, "score": match_score})
        
        # Sort filename matches by match_score
        filename_matches = sorted(filename_matches, key=lambda x: x["score"], reverse=True)

        # 2. Vector Search (Semantic)
        client = chromadb.PersistentClient(path=os.path.join(indices_dir, "chroma_db"))
        vector_results = []
        try:
            collection = client.get_collection(name="project_context")
            v_res = collection.query(query_texts=[query_text], n_results=n_results * 2)
            ids = v_res.get("ids", [[]])[0]
            for vid in ids:
                vector_results.append({"id": vid})
        except Exception:
            pass

        # 3. Fusion (Weighted RRF)
        final_ids, rrf_scores = self._weighted_rrf(filename_matches, vector_results, w_file=3.0, w_vec=1.0)
        
        # 4. Filter & Build Final Response
        res_ids = []
        res_metas = []
        res_docs = []
        
        # Re-fetch content and metadata for the winners
        # (Chroma usually has them, but for filename matches we might need to read disk)
        for doc_id in final_ids:
            if len(res_ids) >= n_results: break
            
            try:
                # Meta check
                is_boosted = any(f["id"] == doc_id for f in filename_matches)
                
                with open(doc_id, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                
                # Anti-Flooding Filter
                if not is_boosted and self._is_low_quality(content, doc_id):
                    continue

                res_ids.append(doc_id)
                res_metas.append({
                    "path": doc_id,
                    "boosted": is_boosted,
                    "rrf_score": rrf_scores[doc_id]
                })
                res_docs.append(content)
            except Exception:
                continue

        return {
            "ids": [res_ids],
            "metadatas": [res_metas],
            "documents": [res_docs]
        }
