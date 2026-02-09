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
                        "type": "code"
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

    def _rerank_results(self, final_ids: list, rrf_scores: dict, query_keywords: list) -> list:
        """Re-rank final fusion results by counting literal keyword matches in content."""
        if not query_keywords:
            return final_ids, rrf_scores
            
        boosted_scores = rrf_scores.copy()
        
        # Only re-rank the top candidates to avoid excessive I/O
        candidates = final_ids[:15]
        
        for filepath in candidates:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().lower()
                
                # Count keyword hits
                hits = sum(1 for kw in query_keywords if kw in content)
                # Apply boost: RRF scores are small, so 0.1 per hit is significant
                boosted_scores[filepath] += (hits * 0.1)
            except Exception:
                continue
        
        # Re-sort ALL ids by boosted score
        # (Though only candidates were changed, we sort everything to keep consistency)
        new_sorted_ids = sorted(final_ids, key=lambda x: boosted_scores[x], reverse=True)
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

    def _declaration_boost(self, final_ids: list, rrf_scores: dict, identifiers: list) -> tuple:
        """
        [v0.6.0] Boost files that contain actual DECLARATIONS of queried identifiers.
        
        This specifically targets the "birth certificate" of a variable, not just mentions.
        Includes mitigations for test files and over-ranking.
        """
        if not identifiers:
            return final_ids, rrf_scores
        
        # Test/mock path patterns (reduced boost for these)
        TEST_PATH_PATTERNS = [
            r'[/\\]tests?[/\\]', r'[/\\]specs?[/\\]', r'[/\\]__tests?__[/\\]',
            r'[/\\]mocks?[/\\]', r'[/\\]fixtures?[/\\]',
            r'\.test\.', r'\.spec\.', r'\.mock\.'
        ]
        
        # Declaration patterns for common languages
        DECL_PATTERNS = [
            # JavaScript/TypeScript
            r'(?:let|const|var)\s+{ident}\s*[=:;]',
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
            # General
            r'function\s+{ident}\s*\(',
            r'{ident}\s*=\s*function\s*\(',
            r'{ident}\s*=\s*\([^)]*\)\s*=>',
            # CSS/SCSS/LESS
            r'\.{ident}\s*\{',    # Class selector
            r'\#{ident}\s*\{',    # ID selector
            r'@{ident}\s+',       # At-rule
            r'--{ident}\s*:',     # CSS Variable
            
            # Go (Golang)
            r'func\s+{ident}\s*\(',
            r'type\s+{ident}\s+(?:struct|interface)',
            r'{ident}\s*:=\s*',
            
            # Rust
            r'(?:let|const)\s+(?:mut\s+)?{ident}\s*[=:]',
            r'fn\s+{ident}\s*[\(<]',
            r'(?:struct|enum|trait|mod)\s+{ident}',
            r'macro_rules!\s+{ident}',

            # Terraform (HCL)
            r'(?:resource|module|variable|output)\s+"[^"]+"\s+"{ident}"', 
            r'(?:variable|module|output)\s+"{ident}"',
            
            # SQL
            r'CREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|VIEW|PROCEDURE|FUNCTION|INDEX)\s+(?:IF\s+NOT\s+EXISTS\s+)?{ident}',

            # HTML & Web Components
            r'id=["\']{ident}["\']',              # id="app"
            r'name=["\']{ident}["\']',            # name="email"
            r'slot=["\']{ident}["\']',            # slot="header"
            
            # Frameworks (React, Vue, Angular)
            r'ref=["\']{ident}["\']',             # ref="myInput" (Vue/React)
            r'#{ident}\b',                        # #myVar (Angular template var)
            
            # Testing / Data Attributes
            r'data-test-?id=["\']{ident}["\']',   # data-testid="submit-btn"
        ]
        
        MAX_BOOST = 1.5  # Cap to prevent over-ranking
        
        boosted_scores = rrf_scores.copy()
        candidates = final_ids[:30]
        
        for filepath in candidates:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # Check if this is a test/mock file
                is_test = any(re.search(p, filepath, re.IGNORECASE) for p in TEST_PATH_PATTERNS)
                base_boost = 0.3 if is_test else 1.0
                
                file_boost = 0
                for ident in identifiers:
                    for pattern_template in DECL_PATTERNS:
                        pattern = pattern_template.format(ident=re.escape(ident))
                        if re.search(pattern, content, re.MULTILINE):
                            file_boost += base_boost
                            prefix = "[TEST] " if is_test else ""
                            sys.stderr.write(
                                f"[Indexer] {prefix}Declaration boost +{base_boost}: "
                                f"{os.path.basename(filepath)} declares '{ident}'\n"
                            )
                            break  # One boost per identifier per file
                
                # Apply capped boost
                if file_boost > 0:
                    boosted_scores[filepath] += min(file_boost, MAX_BOOST)
                
            except Exception:
                continue
        
        # Re-sort ALL ids by boosted score
        new_sorted_ids = sorted(final_ids, key=lambda x: boosted_scores.get(x, 0), reverse=True)
        return new_sorted_ids, boosted_scores

    def _word_boost(self, final_ids: list, rrf_scores: dict, identifiers: list) -> tuple:
        """Boost files that contain any of the extracted identifiers."""
        if not identifiers:
            return final_ids, rrf_scores
        
        boosted_scores = rrf_scores.copy()
        # Check top 30 files for identifier hits
        candidates = final_ids[:30]
        
        for filepath in candidates:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                hits = 0
                for ident in identifiers:
                    # Case-sensitive check for identifiers is usually better for code
                    if ident in content:
                        hits += 1
                
                # Apply a significant boost per identifier match
                if hits > 0:
                    boosted_scores[filepath] += (hits * 0.5)
            except Exception:
                continue
        
        # Re-sort ALL ids by boosted score
        new_sorted_ids = sorted(final_ids, key=lambda x: boosted_scores[x], reverse=True)
        return new_sorted_ids, boosted_scores

    def _grep_search(self, project_path: str, query_text: str, file_pattern: str = None) -> list:
        """Internal fast grep for literal string matches in indexed files."""
        matches = []
        _, hashes_path = self._get_paths(project_path)
        known_files = self._load_hashes(hashes_path)
        
        query_text_lower = query_text.lower()
        
        for filepath in known_files:
            if not self._matches_file_pattern(filepath, project_path, file_pattern):
                continue
            
            try:
                # Basic check for file existence (might have been moved/deleted but still in hashes)
                if not os.path.exists(filepath):
                    continue

                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    if query_text_lower in content.lower():
                        matches.append({"id": filepath})
            except Exception:
                continue
        
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
        # ... [omitted identical logic] ...
        for path in known_hashes:
            filename = os.path.basename(path)
            if not self._matches_file_pattern(path, project_path, file_pattern):
                continue
            filename_lower = filename.lower()
            rel_path = os.path.relpath(path, project_path).lower()
            match_score = 0
            if query_lower == filename_lower: match_score = 10
            elif query_lower in filename_lower: match_score = 5
            elif query_lower in rel_path: match_score = 2
            if match_score > 0:
                filename_matches.append({"id": path, "score": match_score})
        
        filename_matches = sorted(filename_matches, key=lambda x: x["score"], reverse=True)

        # 2. Hybrid Search: Literal (Grep) vs Semantic (Vector)
        vector_results = []
        if query_type == 'literal':
            literal_results = self._grep_search(project_path, query_text, file_pattern)
            try:
                client = chromadb.PersistentClient(path=os.path.join(indices_dir, "chroma_db"))
                collection = client.get_collection(name="project_context")
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
                    existing["score"] += 15
                else:
                    filename_matches.append({"id": match["id"], "score": 8})
        else:
            try:
                client = chromadb.PersistentClient(path=os.path.join(indices_dir, "chroma_db"))
                collection = client.get_collection(name="project_context")
                v_res = collection.query(query_texts=[query_text], n_results=n_results * 10)
                ids = v_res.get("ids", [[]])[0]
                for vid in ids:
                    if not self._matches_file_pattern(vid, project_path, file_pattern):
                        continue
                    vector_results.append({"id": vid})
            except Exception:
                pass
            literal_results = self._grep_search(project_path, query_text, file_pattern)
            for match in literal_results:
                if not any(v["id"] == match["id"] for v in vector_results):
                    filename_matches.append({"id": match["id"], "score": 3})

        # 3. Fusion (Weighted RRF)
        final_ids, rrf_scores = self._weighted_rrf(filename_matches, vector_results, w_file=50.0, w_vec=1.0)
        identifiers = self._extract_identifiers(query_text)
        if identifiers:
            final_ids, rrf_scores = self._word_boost(final_ids, rrf_scores, identifiers)
            final_ids, rrf_scores = self._declaration_boost(final_ids, rrf_scores, identifiers)
        if query_type == 'conceptual':
            keywords = self._extract_keywords(query_text)
            final_ids, rrf_scores = self._rerank_results(final_ids, rrf_scores, keywords)

        # 4. Filter & Build Final Response
        res_ids = []
        res_metas = []
        res_docs = []
        for doc_id in final_ids:
            if len(res_ids) >= n_results: break
            try:
                is_boosted = any(os.path.normpath(f["id"]) == os.path.normpath(doc_id) for f in filename_matches)
                with open(doc_id, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                if not is_boosted and self._is_low_quality(content, doc_id):
                    continue
                
                # [Fase B: Literal Match Detection]
                is_literal = False
                if query_text.lower() in content.lower():
                    is_literal = True
                else:
                    # Check if at least one identifier is literally there
                    is_literal = any(ident.lower() in content.lower() for ident in identifiers)

                res_ids.append(doc_id)
                res_metas.append({
                    "path": doc_id,
                    "boosted": is_boosted,
                    "literal_match": is_literal,
                    "rrf_score": rrf_scores[doc_id]
                })
                res_docs.append(content)
            except Exception:
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
