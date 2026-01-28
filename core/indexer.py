import os
import hashlib
import json
import chromadb
import fnmatch
from chromadb.config import Settings
from .skeletonizer import Skeletonizer

class GitignoreParser:
    """Simple parser for .gitignore patterns."""
    def __init__(self, root_path: str):
        self.root_path = root_path
        self.patterns = []
        self._load_gitignore()

    def _load_gitignore(self):
        gitignore_path = os.path.join(self.root_path, ".gitignore")
        if not os.path.exists(gitignore_path):
            return
        
        with open(gitignore_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"): continue
                self.patterns.append(line)

    def match(self, filepath: str) -> bool:
        """Returns True if the filepath matches any ignore pattern."""
        rel_path = os.path.relpath(filepath, self.root_path)
        # Normalize for windows
        rel_path = rel_path.replace(os.sep, "/")
        
        for pattern in self.patterns:
            # Handle directory specific patterns (ending with /)
            if pattern.endswith("/"):
                # Check if file is IN that directory
                if rel_path.startswith(pattern) or f"/{pattern}" in rel_path:
                    return True
            
            # Simple fnmatch
            if fnmatch.fnmatch(rel_path, pattern):
                return True
            # Match basename
            if fnmatch.fnmatch(os.path.basename(filepath), pattern):
                return True
        return False

class Indexer:
    def __init__(self):
        # Indexer is now stateless regarding "data_dir". 
        # It calculates paths based on the project being indexed.
        self.skeletonizer = Skeletonizer()
        
        # Standard noise patterns (Explicit Blacklist)
        self.IGNORED_PATTERNS = [
            "*.min.js", "*.min.css", "*.map",
            "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
            "*.svg", "*.png", "*.jpg", "*.jpeg", "*.gif", "*.ico",
            "*.zip", "*.tar", "*.gz", "*.rar", "*.7z", "*.pdf", 
            "*.exe", "*.dll", "*.so", "*.dylib", "*.bin",
            "*.pyc", "*.pyo"
        ]

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

    def _is_binary_file(self, filepath: str) -> bool:
        """Check first 1024 bytes for null byte to detect binary files."""
        try:
            with open(filepath, "rb") as f:
                chunk = f.read(1024)
                return b'\0' in chunk
        except Exception:
            return True # If we can't read it, assume it's not text code

    def _should_ignore(self, filepath: str, gitignore: GitignoreParser) -> bool:
        filename = os.path.basename(filepath)
        
        # 1. Explicit Pattern Blacklist
        for pattern in self.IGNORED_PATTERNS:
            if fnmatch.fnmatch(filename, pattern):
                print(f"[Indexer] Ignoring {filename} (Matched pattern: {pattern})")
                return True
        
        # 2. Gitignore Check
        if gitignore.match(filepath):
            print(f"[Indexer] Ignoring {filename} (Matched .gitignore)")
            return True
            
        # 3. Binary Check
        if self._is_binary_file(filepath):
            print(f"[Indexer] Ignoring {filename} (Detected Binary)")
            return True
            
        return False

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
        
        # Initialize Gitignore Parser
        gitignore = GitignoreParser(project_path)

        # Walk files
        for root, dirs, files in os.walk(project_path):
            # Always exclude .ace
            if ".ace" in dirs: dirs.remove(".ace")
            if ".git" in dirs: dirs.remove(".git")
            
            # Don't manually remove 'dist', 'node_modules' etc here.
            # We let .gitignore handle it, OR we rely on efficient skipping below.
            # However, for huge dirs like node_modules, it's efficient to skip walking them if gitignored.
            # Optimization: Check if current root is ignored
            if gitignore.match(root):
                # If the directory itself is ignored, clear subdirs to stop recursion
                dirs[:] = []
                continue

            for file in files:
                filepath = os.path.join(root, file)
                
                # Check against our Robust Filters
                if self._should_ignore(filepath, gitignore):
                    continue
                
                # Allowed extensions check (Whitelist)
                if not file.endswith((
                    # Frontend / Web
                    ".html", ".htm", ".css", ".scss", ".less", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte",
                    # Backend / Scripting
                    ".py", ".php", ".rb", ".go", ".java", ".cs", ".rs", ".kt", ".swift", ".dart", ".sh",
                    # Data / Config
                    ".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".env", ".sql", ".md", ".txt"
                )): continue
                
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
        """Fallback Heuristic for search time filtering."""
        if not content: return True
        # If it passed index time filters, it's mostly okay, but check for extreme minification just in case
        lines = content.splitlines()
        if lines:
            avg_len = len(content) / len(lines)
            if avg_len > 1000: return True # Very generous limit, only for truly minified garbage
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
        # HUGE BOOST (50.0) ensures filename matches preserve their rank order above vector results
        final_ids, rrf_scores = self._weighted_rrf(filename_matches, vector_results, w_file=50.0, w_vec=1.0)
        
        # 4. Filter & Build Final Response
        res_ids = []
        res_metas = []
        res_docs = []
        
        # Re-fetch content and metadata for the winners
        for doc_id in final_ids:
            if len(res_ids) >= n_results: break
            
            try:
                # Meta check (Robust normalization)
                # We check if doc_id is in the list of filename_matches IDs
                is_boosted = any(os.path.normpath(f["id"]) == os.path.normpath(doc_id) for f in filename_matches)
                
                with open(doc_id, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                
                # Anti-Flooding Filter: Only apply to NON-BOOSTED files
                # If it's a priority match, we show it even if it looks "low quality" (user knows best)
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
