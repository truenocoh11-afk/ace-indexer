import os
import hashlib
import json
import chromadb
import fnmatch
import re
from chromadb.config import Settings
import sys
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
                sys.stderr.write(f"[Indexer] Ignoring {filename} (Matched pattern: {pattern})\n")
                return True
        
        # 2. Gitignore Check
        if gitignore.match(filepath):
            sys.stderr.write(f"[Indexer] Ignoring {filename} (Matched .gitignore)\n")
            return True
            
        # 3. Binary Check
        if self._is_binary_file(filepath):
            sys.stderr.write(f"[Indexer] Ignoring {filename} (Detected Binary)\n")
            return True
            
        return False

    def index_project(self, project_path: str, force: bool = False):
        sys.stderr.write(f"[Indexer] Indexing project: {project_path}\n")
        
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
            # 1. Universal Hard Blocks (Never index these, regardless of gitignore)
            if ".ace" in dirs: dirs.remove(".ace")
            if ".git" in dirs: dirs.remove(".git")
            if "node_modules" in dirs: dirs.remove("node_modules")
            if "venv" in dirs: dirs.remove("venv")
            if "__pycache__" in dirs: dirs.remove("__pycache__")
            if ".idea" in dirs: dirs.remove(".idea")
            if ".vscode" in dirs: dirs.remove(".vscode")
            
            # 2. Gitignore & Optimization
            # Check if current root is ignored by gitignore
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
            sys.stderr.write(f"[Indexer] Removing {len(ids_to_delete)} stale files.\n")
            collection.delete(ids=ids_to_delete)

        # Process Additions/Updates
        if files_to_index:
            sys.stderr.write(f"[Indexer] Indexing {len(files_to_index)} new/changed files.\n")
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
                        "type": "code",
                        "ident_bag": " ".join(self._extract_identifiers(content))
                    })
                    ids.append(filepath)
                except Exception as e:
                    sys.stderr.write(f"Error indexing {filepath}: {e}\n")

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

    def index_remote_data(self, project_path: str, remote_data: dict):
        """Incorporate remote file snippets into the local vector index."""
        sys.stderr.write(f"[Indexer] Indexing remote data for env: {remote_data.get('env_name')}\n")
        
        indices_dir, _ = self._get_paths(project_path)
        client = chromadb.PersistentClient(path=os.path.join(indices_dir, "chroma_db"))
        collection = client.get_or_create_collection(name="project_context")
        
        env_name = remote_data.get("env_name", "remote")
        files = remote_data.get("files", [])
        
        documents = []
        metadatas = []
        ids = []
        
        for f in files:
            path = f["path"]
            snippet = f["snippet"]
            
            # Use a unique ID for remote files to avoid collision with local ones
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
            
        return {"indexed": len(documents), "env": env_name}


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
        """[v0.8.0] Weighted RRF with min-max normalization.
        Scores are normalized to [0, 1] range after fusion for stable ranking.
        """
        raw_scores = {}
        for rank, item in enumerate(filename_results, start=1):
            path = item["id"]
            raw_scores[path] = raw_scores.get(path, 0.0) + (w_file / (k + rank))

        for rank, item in enumerate(vector_results, start=1):
            path = item["id"]
            raw_scores[path] = raw_scores.get(path, 0.0) + (w_vec / (k + rank))

        # Min-max normalize to [0, 1]
        if raw_scores:
            max_s = max(raw_scores.values())
            min_s = min(raw_scores.values())
            span = max_s - min_s if max_s != min_s else 1.0
            scores = {p: (s - min_s) / span for p, s in raw_scores.items()}
        else:
            scores = raw_scores

        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        return sorted_ids, scores

    def get_index_status(self, project_path: str):
        indices_dir, hashes_path = self._get_paths(project_path)
        
        if not os.path.exists(hashes_path):
            return {"status": "error", "message": "Index does not exist for this project."}
            
        known_hashes = self._load_hashes(hashes_path)
        last_update = os.path.getmtime(hashes_path)
        
        # Check for files on disk not in index
        files_on_disk = []
        gitignore = GitignoreParser(project_path)
        for root, dirs, files in os.walk(project_path):
            if ".ace" in dirs: dirs.remove(".ace")
            if ".git" in dirs: dirs.remove(".git")
            if "node_modules" in dirs: dirs.remove("node_modules")
            
            if gitignore.match(root):
                dirs[:] = []
                continue
                
            for file in files:
                filepath = os.path.join(root, file)
                if not self._should_ignore(filepath, gitignore):
                    # Check Whitelist
                    if file.endswith((".html", ".htm", ".css", ".scss", ".less", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".py", ".php", ".rb", ".go", ".java", ".cs", ".rs", ".kt", ".swift", ".dart", ".sh", ".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".env", ".sql", ".md", ".txt")):
                        files_on_disk.append(filepath)
        
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
            # Normalize pattern to use forward slashes
            norm_pattern = pattern.replace('\\', '/')
            
            def matches(filepath):
                # Normalize filepath to use forward slashes for consistent matching
                norm_path = filepath.replace('\\', '/')
                # Try matching against full path first
                if fnmatch.fnmatch(norm_path, norm_pattern):
                    return True
                # Also try matching just the filename (for simple patterns like "*.py")
                if fnmatch.fnmatch(os.path.basename(filepath), pattern):
                    return True
                return False
            
            files = [f for f in files if matches(f)]
            
        return files

    def _classify_query(self, query: str) -> str:
        """
        Returns: 'literal' | 'conceptual'
        """
        # [v0.3.1] Check EACH WORD in query for code patterns
        words = query.split()
        
        # Patterns that indicate a code literal (applied to each word)
        word_patterns = [
            r'^[a-z]+[A-Z]',           # camelCase: lastAgentStats
            r'^[A-Z][a-z]+[A-Z]',      # PascalCase: UserService
            r'[a-z]_[a-z]',            # snake_case: user_id
            r'^[A-Z][A-Z0-9_]+$',      # CONSTANTE: MAX_RETRIES
        ]
        
        for word in words:
            for p in word_patterns:
                if re.search(p, word):
                    return 'literal'
        
        # Global patterns (applied to full query)
        global_patterns = [
            r'\(',                     # Function call: handleRequest(
            r'\.',                     # Member access: this.value
            r'\[',                     # Array access: items[0]
            r'/',                      # File path: monitor/server.js
        ]
        
        for p in global_patterns:
            if re.search(p, query):
                return 'literal'
        
        # If it's a long natural language phrase, likely conceptual
        if len(words) > 3:
            return 'conceptual'
        
        # Default to literal for short phrases that might be code
        return 'literal'

    def _matches_file_pattern(self, filepath: str, project_path: str, file_pattern: str) -> bool:
        """Check if file matches pattern. Supports both filename and path patterns."""
        if not file_pattern:
            return True
        
        filename = os.path.basename(filepath)
        rel_path = os.path.relpath(filepath, project_path).replace(os.sep, '/')
        
        # Try matching against filename first (most common case)
        if fnmatch.fnmatch(filename, file_pattern):
            return True
        
        # Try matching against relative path (for patterns like "monitor/server.js")
        if fnmatch.fnmatch(rel_path, file_pattern):
            return True
        
        # Try matching against relative path with wildcards (for patterns like "*/server.js")
        if fnmatch.fnmatch(rel_path, f"*/{file_pattern}"):
            return True
        
        return False

    def _extract_keywords(self, query: str) -> list:
        """Extract meaningful keywords from query, removing stopwords."""
        stopwords = {'the', 'a', 'an', 'of', 'to', 'for', 'in', 'on', 'is', 'are', 'was', 'were', 'and', 'with', 'about', 'logic', 'calculate', 'initialization'}
        words = re.findall(r'\w+', query.lower())
        return [w for w in words if w not in stopwords and len(w) > 2]

    def _rerank_results(self, final_ids: list, rrf_scores: dict, query_keywords: list, metadatas_lookup: dict) -> tuple:
        """[v0.7.0] Re-rank final results using ident_bag metadata instead of Disk I/O."""
        if not query_keywords:
            return final_ids, rrf_scores
            
        boosted_scores = rrf_scores.copy()
        candidates = final_ids[:15]
        
        for filepath in candidates:
            try:
                # Use metadata ident_bag (lowercase) for keyword matching
                ident_bag = metadatas_lookup.get(filepath, {}).get("ident_bag", "").lower()
                
                hits = sum(1 for kw in query_keywords if kw.lower() in ident_bag)
                boosted_scores[filepath] += (hits * 0.1)
            except Exception:
                continue
        
        new_sorted_ids = sorted(final_ids, key=lambda x: boosted_scores.get(x, 0), reverse=True)
        return new_sorted_ids, boosted_scores

    def _extract_identifiers(self, query: str) -> list:
        """Extract code identifiers from query (camelCase, snake_case, PascalCase)."""
        # Patterns for common code identifier styles (without word boundaries for better matching)
        patterns = [
            r'[a-z]+[A-Z][a-zA-Z0-9]*',      # camelCase: lastAgentStats
            r'[A-Z][a-z]+[A-Z][a-zA-Z0-9]*', # PascalCase: StateManager
            r'[a-z]+_[a-z0-9_]+',            # snake_case: last_agent_stats
            r'[A-Z]{2}[A-Z0-9_]+',           # CONSTANT_CASE: TLE_URL (at least 2 caps)
        ]
        identifiers = []
        for p in patterns:
            matches = re.findall(p, query)
            identifiers.extend(matches)
        
        # Deduplicate while preserving order
        return list(dict.fromkeys(identifiers))

    def _declaration_boost(self, final_ids: list, rrf_scores: dict, identifiers: list, metadatas_lookup: dict) -> tuple:
        """
        [v0.7.0] RAM-ONLY Declaration Boost.
        Uses 'skeleton' from metadata to avoid reading files from disk.
        """
        if not identifiers:
            return final_ids, rrf_scores
        
        # Test/mock path patterns (reduced boost for these)
        TEST_PATH_PATTERNS = [
            r'[/\]tests?[/\]', r'[/specs?]', r'[/__tests?__]',
            r'[/mocks?]', r'[/fixtures?]',
            r'\.test\.', r'\.spec\.', r'\.mock\.'
        ]
        
        # Declaration patterns for common languages
        DECL_PATTERNS = [
            # JavaScript/TypeScript
            r'(?:let|const|var)\s+{ident}\s*[=:]',
            r'export\s+(?:let|const|var)\s+{ident}',
            r'export\s+(?:default\s+)?(?:function|class)\s+{ident}',
            r'(?:public|private|protected)?\s*{ident}\s*[=:]',
            # Python
            r'^{ident}\s*=\s*',
            r'^{ident}\s*:\s*\w+\s*=',
            r'self\.{ident}\s*=',
            r'def\s+{ident}\s*\(',
            r'class\s+{ident}\s*[\(:]',
            r'async\s+def\s+{ident}\s*\(',
            # [Simplified patterns for skeleton matching]
            r'function\s+{ident}\s*\(',
            # Rust/Go
            r'fn\s+{ident}\b',
            r'func\s+{ident}\b',
        ]
        
        MAX_BOOST = 1.5
        boosted_scores = rrf_scores.copy()
        candidates = final_ids[:30]
        
        for filepath in candidates:
            try:
                # Use skeleton metadata instead of full content
                skeleton_content = metadatas_lookup.get(filepath, {}).get("skeleton", "")
                if not skeleton_content:
                    continue

                is_test = any(re.search(p, filepath, re.IGNORECASE) for p in TEST_PATH_PATTERNS)
                base_boost = 0.3 if is_test else 1.0
                
                file_boost = 0
                for ident in identifiers:
                    for pattern_template in DECL_PATTERNS:
                        pattern = pattern_template.format(ident=re.escape(ident))
                        if re.search(pattern, skeleton_content, re.MULTILINE):
                            file_boost += base_boost
                            break
                
                if file_boost > 0:
                    boosted_scores[filepath] += min(file_boost, MAX_BOOST)
                
            except Exception:
                continue
        
        new_sorted_ids = sorted(final_ids, key=lambda x: boosted_scores.get(x, 0), reverse=True)
        return new_sorted_ids, boosted_scores

    def _word_boost(self, final_ids: list, rrf_scores: dict, identifiers: list, metadatas_lookup: dict) -> tuple:
        """[v0.7.0] RAM-ONLY identifier boost using ident_bag."""
        if not identifiers:
            return final_ids, rrf_scores
        
        boosted_scores = rrf_scores.copy()
        candidates = final_ids[:30]
        
        for filepath in candidates:
            try:
                ident_bag = metadatas_lookup.get(filepath, {}).get("ident_bag", "")
                if not ident_bag:
                    continue

                hits = 0
                for ident in identifiers:
                    if ident in ident_bag:
                        hits += 1
                
                if hits > 0:
                    boosted_scores[filepath] += (hits * 0.5)
            except Exception:
                continue
        
        new_sorted_ids = sorted(final_ids, key=lambda x: boosted_scores.get(x, 0), reverse=True)
        return new_sorted_ids, boosted_scores

    def _grep_search(self, project_path: str, query_text: str, file_pattern: str = None, collection=None) -> list:
        """[v0.8.0] Chroma-Native literal search. Zero disk I/O.
        
        Uses `where_document={"$contains": query}` to search the full content
        already stored in ChromaDB, without reading any file from disk.
        Falls back to disk grep if `collection` is None.
        """
        matches = []

        if collection is None:
            # Fallback: legacy disk grep (safety net if Chroma unavailable)
            indices_dir, hashes_path = self._get_paths(project_path)
            known_files = self._load_hashes(hashes_path)
            query_text_lower = query_text.lower()
            for filepath in known_files:
                if not self._matches_file_pattern(filepath, project_path, file_pattern): continue
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        if query_text_lower in content.lower():
                            matches.append({"id": filepath, "remote": False, "line": 0})
                except Exception: continue
            return matches

        # [v0.8.0] Primary path: search stored documents in ChromaDB
        try:
            # $contains is case-sensitive in Chroma, so we search both cases
            # For identifiers this is fine; for case-insensitive we compound with $or
            res = collection.get(
                where_document={"$contains": query_text},
                include=["metadatas"]
            )
            for mid, meta in zip(res["ids"], res["metadatas"]):
                path = meta.get("path", mid)
                is_remote = meta.get("remote", False)
                if file_pattern and not self._matches_file_pattern(path, project_path, file_pattern):
                    continue
                matches.append({"id": mid, "remote": is_remote, "line": 0})
        except Exception as e:
            sys.stderr.write(f"[Indexer] where_document search failed: {e}\n")

        return matches


    def _is_index_too_old(self, project_path: str) -> bool:
        """Determina si el índice necesita una actualización automática."""
        indices_dir, hashes_path = self._get_paths(project_path)
        
        # Si no hay hashes, no hay índice
        if not os.path.exists(hashes_path):
            return True
            
        # Si el índice tiene más de 24 horas, re-chequear (opcional, pero ayuda)
        last_update = os.path.getmtime(hashes_path)
        import time
        if time.time() - last_update > 86400: # 1 día
            return True
            
        # [Crucial] Si el índice está vacío (0 archivos), intentar re-indexar
        hashes = self._load_hashes(hashes_path)
        if not hashes:
            return True
            
        return False

    def query(self, project_path: str, query_text: str, n_results: int = 5, file_pattern: str = None):
        indices_dir, hashes_path = self._get_paths(project_path)
        
        # [Fase A: Auto-Index]
        if self._is_index_too_old(project_path):
            sys.stderr.write(f"[Indexer] Index is stale or missing. Auto-indexing: {project_path}\n")
            self.index_project(project_path)

        if not os.path.exists(indices_dir):
             return {"ids": [], "metadatas": [], "documents": []}

        # [v0.3.0] Smart Query Classification
        query_type = self._classify_query(query_text)
        sys.stderr.write(f"[Indexer] Classified query '{query_text}' as: {query_type}\n")

        # 1. Filename Search (Keyword) - Persistent Across Types
        known_hashes = self._load_hashes(hashes_path)
        filename_matches = []
        query_lower = query_text.lower()
        
        # Local paths
        all_paths = [(p, False, None) for p in known_hashes.keys()]
        
        # [v0.7.0] Single, shared Chroma client for the entire query lifetime
        collection = None
        try:
            client = chromadb.PersistentClient(path=os.path.join(indices_dir, "chroma_db"))
            collection = client.get_collection(name="project_context")
            remotes = collection.get(where={"remote": True}, include=["metadatas"])
            for meta, rid in zip(remotes["metadatas"], remotes["ids"]):
                all_paths.append((meta["path"], True, rid))
        except Exception:
            pass

        for path, is_remote, rid in all_paths:
            filename = os.path.basename(path)
            # Use rid for remote files internally
            internal_id = rid if is_remote else path
            
            if not self._matches_file_pattern(path, project_path, file_pattern):
                continue
            
            filename_lower = filename.lower()
            # For remote files, we can't always do rel_path easily if it's outside project
            rel_path = path.lower() if is_remote else os.path.relpath(path, project_path).lower()
            
            match_score = 0
            if query_lower == filename_lower: match_score = 10
            elif query_lower in filename_lower: match_score = 5
            elif query_lower in rel_path: match_score = 2
            
            if match_score > 0:
                filename_matches.append({"id": internal_id, "score": match_score, "remote": is_remote})
        
        filename_matches = sorted(filename_matches, key=lambda x: x["score"], reverse=True)


        # 2. Hybrid Search: Literal (Grep) vs Semantic (Vector)
        vector_results = []
        if query_type == 'literal':
            literal_results = self._grep_search(project_path, query_text, file_pattern, collection=collection)
            try:
                if collection:
                    v_res = collection.query(query_texts=[query_text], n_results=n_results * 5)
                    ids = v_res.get("ids", [[]])[0]
                    for vid in ids:
                        if not self._matches_file_pattern(vid, project_path, file_pattern):
                            continue
                        vector_results.append({"id": vid})
            except Exception:
                pass
            for match in literal_results:
                existing = next((f for f in filename_matches if f["id"] == match["id"]), None)
                if existing:
                    existing["score"] += 1.0
                else:
                    filename_matches.append({"id": match["id"], "score": 0.8, "remote": match.get("remote", False)})
        else:
            try:
                if collection:
                    v_res = collection.query(query_texts=[query_text], n_results=n_results * 10)
                    ids = v_res.get("ids", [[]])[0]
                    for vid in ids:
                        if not self._matches_file_pattern(vid, project_path, file_pattern):
                            continue
                        vector_results.append({"id": vid})
            except Exception:
                pass
            literal_results = self._grep_search(project_path, query_text, file_pattern, collection=collection)
            for match in literal_results:
                if not any(v["id"] == match["id"] for v in vector_results):
                    filename_matches.append({"id": match["id"], "score": 3, "remote": match.get("remote", False)})

        # 3. Fusion (Weighted RRF)
        final_ids, rrf_scores = self._weighted_rrf(filename_matches, vector_results, w_file=50.0, w_vec=1.0)
        
        # [v0.7.0] V3 RAM-BASED SCORING: Pre-fetch metadatas for top 30 candidates
        metadatas_lookup = {}
        if final_ids and collection:
            try:
                boost_candidates = final_ids[:30]
                meta_res = collection.get(ids=boost_candidates, include=["metadatas"])
                metadatas_lookup = {mid: meta for mid, meta in zip(meta_res["ids"], meta_res["metadatas"])}
            except Exception as e:
                sys.stderr.write(f"[Indexer] Warning: Could not pre-fetch metadatas: {e}\n")

        identifiers = self._extract_identifiers(query_text)
        if identifiers:
            final_ids, rrf_scores = self._word_boost(final_ids, rrf_scores, identifiers, metadatas_lookup)
            final_ids, rrf_scores = self._declaration_boost(final_ids, rrf_scores, identifiers, metadatas_lookup)
            
        if query_type == 'conceptual':
            keywords = self._extract_keywords(query_text)
            final_ids, rrf_scores = self._rerank_results(final_ids, rrf_scores, keywords, metadatas_lookup)

        # 4. Filter & Build Final Response
        res_ids = []
        res_metas = []
        res_docs = []
        for doc_id in final_ids:
            if len(res_ids) >= n_results: break
            try:
                # Find if it's remote in our tracking lists
                filename_item = next((f for f in filename_matches if f["id"] == doc_id), None)
                is_remote = filename_item["remote"] if filename_item else doc_id.startswith("remote://")
                
                content = ""
                is_boosted = any(f["id"] == doc_id for f in filename_matches)
                
                # Reuse the shared collection handle
                _chroma_col = collection

                if not is_remote:
                    # LOCAL FILE
                    with open(doc_id, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    if not is_boosted and self._is_low_quality(content, doc_id):
                        continue
                    display_path = doc_id
                    env_name = None
                    # [V3: Recover skeleton from Chroma for semantic snippets]
                    try:
                        _sk_entry = _chroma_col.get(ids=[doc_id], include=["metadatas"])
                        skeleton_text = _sk_entry["metadatas"][0].get("skeleton", "") if _sk_entry["metadatas"] else ""
                    except Exception:
                        skeleton_text = ""
                else:
                    # REMOTE FILE (Load from Chroma)
                    try:
                        remote_entry = _chroma_col.get(ids=[doc_id], include=["documents", "metadatas"])
                        if not remote_entry["documents"]: continue
                        content = remote_entry["documents"][0]
                        display_path = remote_entry["metadatas"][0]["path"]
                        env_name = remote_entry["metadatas"][0]["env"]
                        skeleton_text = ""
                    except Exception:
                        continue

                # [Fase B: Literal Match Detection]
                is_literal = False
                if query_text.lower() in content.lower():
                    is_literal = True
                else:
                    is_literal = any(ident.lower() in content.lower() for ident in identifiers)

                # [V3: Line Tracking — enrichment at result-build time]
                match_line = 0
                if not is_remote:
                    qt_lower = query_text.lower()
                    match_line = next(
                        (i + 1 for i, l in enumerate(content.splitlines()) if qt_lower in l.lower()),
                        0
                    )
                    if match_line == 0 and identifiers:
                        for ident in identifiers:
                            found = next(
                                (i + 1 for i, l in enumerate(content.splitlines()) if ident.lower() in l.lower()),
                                0
                            )
                            if found:
                                match_line = found
                                break

                res_ids.append(doc_id)
                res_metas.append({
                    "path": display_path,
                    "boosted": is_boosted,
                    "literal_match": is_literal,
                    "remote": is_remote,
                    "env": env_name,
                    "rrf_score": rrf_scores[doc_id],
                    "line": match_line,
                    "skeleton": skeleton_text
                })
                res_docs.append(content)
            except Exception as e:
                sys.stderr.write(f"Error processing result {doc_id}: {e}\n")
                continue


        if not res_ids:
            # ... [omitted helpful suggestion logic] ...

            # Detect files on disk for helpful suggestion
            gitignore = GitignoreParser(project_path)
            # Just check if at least ONE file exists that matches the pattern but isn't indexed
            disk_sample = []
            for root, dirs, files in os.walk(project_path):
                if ".ace" in dirs: dirs.remove(".ace")
                if ".git" in dirs: dirs.remove(".git")
                if gitignore.match(root):
                    dirs[:] = []
                    continue
                for file in files:
                    if file_pattern and not fnmatch.fnmatch(file, file_pattern): continue
                    fpath = os.path.join(root, file)
                    if fpath not in known_hashes and not self._should_ignore(fpath, gitignore):
                        disk_sample.append(fpath)
                        if len(disk_sample) >= 3: break
                if len(disk_sample) >= 3: break

            res_metas = [{
                "status": "no_results",
                "indexed_files": len(known_hashes),
                "pattern": file_pattern or "*",
                "missing_files": disk_sample
            }]

        return {
            "ids": [res_ids],
            "metadatas": [res_metas],
            "documents": [res_docs]
        }
