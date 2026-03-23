import os
import re
import fnmatch
import sys
import json
from core.exact_search import TrigramIndex

class SearchEngine:
    def __init__(self):
        # Noise patterns used for location-based penalties
        self.NOISE_PATH_PATTERNS = [
            r'[\\/]data[\\/]hashes[\\/]',
            r'[\\/]data[\\/]cache[\\/]',
            r'[\\/]backup[s]?[\\/]',
            r'[\\/]legacy[\\/]',
            r'\.(bak|old|orig)$',
        ]

    def classify_query(self, query: str) -> str:
        """
        Returns: 'literal' | 'conceptual' | 'symbol'
        """
        words = query.split()
        
        # Patterns that indicate a code literal (applied to each word)
        word_patterns = [
            r'^[a-z]+[A-Z]',           # camelCase
            r'^[A-Z][a-z]+[A-Z]',      # PascalCase
            r'^[A-Z][a-z]+$',          # PascalCase simple
            r'[a-zA-Z0-9]_[a-zA-Z0-9]',  # snake_case
            r'^_[a-zA-Z0-9_]+',        # Python private/magic
            r'^[A-Z][A-Z0-9_]+$',      # CONSTANTE
        ]
        
        for word in words:
            for p in word_patterns:
                if re.search(p, word):
                    return 'symbol'
        
        # Global patterns (applied to full query)
        global_patterns = [
            r'\(',                     # Function call
            r'\.',                     # Member access
            r'\[',                     # Array access
            r'/',                      # File path
        ]
        
        for p in global_patterns:
            if re.search(p, query):
                return 'literal'
        
        if len(words) > 3:
            return 'conceptual'
        
        return 'literal'

    def weighted_rrf(self, filename_results: list, vector_results: list, k: int = 60, w_file: float = 3.0, w_vec: float = 1.0) -> list:
        """Weighted RRF with min-max normalization."""
        raw_scores = {}
        for rank, item in enumerate(filename_results, start=1):
            path = item["id"]
            raw_scores[path] = raw_scores.get(path, 0.0) + (w_file / (k + rank))

        for rank, item in enumerate(vector_results, start=1):
            path = item["id"]
            raw_scores[path] = raw_scores.get(path, 0.0) + (w_vec / (k + rank))

        if raw_scores:
            max_s = max(raw_scores.values())
            min_s = min(raw_scores.values())
            span = max_s - min_s if max_s != min_s else 1.0
            scores = {p: (s - min_s) / span for p, s in raw_scores.items()}
        else:
            scores = raw_scores

        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        return sorted_ids, scores

    def rerank_results(self, final_ids: list, rrf_scores: dict, query_keywords: list, metadatas_lookup: dict) -> tuple:
        """Re-rank results using ident_bag metadata."""
        if not query_keywords:
            return final_ids, rrf_scores
            
        boosted_scores = rrf_scores.copy()
        candidates = final_ids[:15]
        
        for filepath in candidates:
            try:
                ident_bag = metadatas_lookup.get(filepath, {}).get("ident_bag", "").lower()
                hits = sum(1 for kw in query_keywords if kw.lower() in ident_bag)
                boosted_scores[filepath] += (hits * 0.25)
                
                basename = os.path.basename(filepath).lower()
                if any(basename.startswith(p) for p in ('temp_', 'debug_', 'test_', 'old_', 'bak_')):
                    boosted_scores[filepath] -= 0.2
            except Exception:
                continue
        
        new_sorted_ids = sorted(final_ids, key=lambda x: boosted_scores.get(x, 0), reverse=True)
        return new_sorted_ids, boosted_scores

    def path_penalty(self, filepath: str, is_remote: bool = False, workspace_only: bool = True) -> float:
        penalty = 0.0
        for pattern in self.NOISE_PATH_PATTERNS:
            if re.search(pattern, filepath, re.IGNORECASE):
                penalty -= 0.3
                break
        if is_remote and workspace_only:
            penalty -= 0.15
        return penalty

    def extract_identifiers(self, query: str) -> list:
        patterns = [
            r'[a-z]+[A-Z][a-zA-Z0-9]*',      # camelCase
            r'[A-Z][a-z]+[A-Z][a-zA-Z0-9]*', # PascalCase
            r'[a-z]+_[a-z0-9_]+',            # snake_case
            r'[A-Z]{2}[A-Z0-9_]+',           # CONSTANT_CASE
        ]
        identifiers = []
        for p in patterns:
            matches = re.findall(p, query)
            identifiers.extend(matches)
        return list(dict.fromkeys(identifiers))

    def extract_keywords(self, query: str) -> list:
        stopwords = {'the', 'a', 'an', 'of', 'to', 'for', 'in', 'on', 'is', 'are', 'was', 'were', 'and', 'with', 'about', 'logic', 'calculate', 'initialization'}
        words = re.findall(r'\w+', query.lower())
        return [w for w in words if w not in stopwords and len(w) > 2]

    def declaration_boost(self, final_ids: list, rrf_scores: dict, identifiers: list, metadatas_lookup: dict) -> tuple:
        if not identifiers:
            return final_ids, rrf_scores
        
        TEST_PATH_PATTERNS = [
            r'[/\]tests?[/\]', r'[/specs?]', r'[/__tests?__]',
            r'[/mocks?]', r'[/fixtures?]',
            r'\.test\.', r'\.spec\.', r'\.mock\.'
        ]
        
        DECL_PATTERNS = [
            r'(?:let|const|var)\s+{ident}\s*[=:]',
            r'export\s+(?:let|const|var)\s+{ident}',
            r'export\s+(?:default\s+)?(?:function|class)\s+{ident}',
            r'(?:public|private|protected)?\s*{ident}\s*[=:]',
            r'^{ident}\s*=\s*',
            r'^{ident}\s*:\s*\w+\s*=',
            r'self\.{ident}\s*=',
            r'def\s+{ident}\s*\(',
            r'class\s+{ident}\s*[\(:]',
            r'async\s+def\s+{ident}\s*\(',
            r'function\s+{ident}\s*\(',
            r'fn\s+{ident}\b',
            r'func\s+{ident}\b',
        ]
        
        MAX_BOOST = 1.5
        boosted_scores = rrf_scores.copy()
        candidates = final_ids[:30]
        
        for filepath in candidates:
            try:
                skeleton_content = metadatas_lookup.get(filepath, {}).get("skeleton", "")
                if not skeleton_content: continue

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
            except Exception: continue
        
        new_sorted_ids = sorted(final_ids, key=lambda x: boosted_scores.get(x, 0), reverse=True)
        return new_sorted_ids, boosted_scores

    def word_boost(self, final_ids: list, rrf_scores: dict, identifiers: list, metadatas_lookup: dict) -> tuple:
        if not identifiers:
            return final_ids, rrf_scores
        
        boosted_scores = rrf_scores.copy()
        candidates = final_ids[:30]
        
        for filepath in candidates:
            try:
                ident_bag = metadatas_lookup.get(filepath, {}).get("ident_bag", "")
                if not ident_bag: continue

                hits = sum(1 for ident in identifiers if ident in ident_bag)
                if hits > 0:
                    boosted_scores[filepath] += (hits * 0.5)
            except Exception: continue
        
        new_sorted_ids = sorted(final_ids, key=lambda x: boosted_scores.get(x, 0), reverse=True)
        return new_sorted_ids, boosted_scores

    def matches_file_pattern(self, filepath: str, project_path: str, file_pattern: str) -> bool:
        if not file_pattern:
            return True
        
        filename = os.path.basename(filepath)
        try:
            rel_path = os.path.relpath(filepath, project_path).replace(os.sep, '/')
        except ValueError:
            rel_path = filepath.replace(os.sep, '/')
            
        if fnmatch.fnmatch(filename, file_pattern): return True
        if fnmatch.fnmatch(rel_path, file_pattern): return True
        if fnmatch.fnmatch(rel_path, f"*/{file_pattern}"): return True
        
        return False

    def is_low_quality(self, content: str, path: str) -> bool:
        if not content: return True
        lines = content.splitlines()
        if lines:
            avg_len = len(content) / len(lines)
            if avg_len > 1000: return True
        return False

    def grep_search(self, project_path: str, query_text: str, file_pattern: str = None, collection=None, workspace_only: bool = True) -> list:
        matches = []
        if collection is None:
            return []

        try:
            # Phase 5: Trigram Index Lookup 
            # Derive DB path from collection persist path if possible
            # Standard ACE path: <indices>/<project_hash>/chroma_db
            try:
                persist_path = collection._client._server.settings.persist_directory
                trigram_db = os.path.join(os.path.dirname(persist_path), "trigram_index.db")
            except:
                # Fallback to a default location if derivation fails
                indices_root = os.path.join(os.path.expanduser("~"), ".ace", "indices")
                import hashlib
                project_hash = hashlib.sha256(project_path.encode()).hexdigest()[:12]
                trigram_db = os.path.join(indices_root, project_hash, "trigram_index.db")

            where_meta = {"remote": False} if workspace_only else None
            
            if len(query_text) < 3:
                # Phase 6: Fallback for short queries where trigram index fails
                res = collection.get(
                    where_document={"$contains": query_text},
                    where=where_meta,
                    include=["metadatas"]
                )
            else:
                index = TrigramIndex(trigram_db)
                candidate_ids = index.find_candidates(query_text)
                
                if not candidate_ids:
                    return []

                # Fetch metadatas only for candidate IDs
                res = collection.get(
                    ids=candidate_ids,
                    where=where_meta,
                    include=["metadatas"]
                )
            
            for mid, meta in zip(res["ids"], res["metadatas"]):
                path = meta.get("path", mid)
                is_remote = meta.get("remote", False)
                if file_pattern and not self.matches_file_pattern(path, project_path, file_pattern):
                    continue
                matches.append({"id": mid, "remote": is_remote, "line": meta.get("line", 0)})
        except Exception as e:
            sys.stderr.write(f"[SearchEngine] Trigram grep search failed: {e}\n")
            return []

        return matches
