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
                if not file.endswith((".py", ".js", ".ts", ".md", ".txt")): continue
                
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

    def query(self, project_path: str, query_text: str, n_results: int = 5):
        indices_dir, hashes_path = self._get_paths(project_path)
        
        # If .ace doesn't exist, we can't query
        if not os.path.exists(indices_dir):
             return {"ids": [], "metadatas": [], "documents": []}

        # 1. Filename Boost (Keyword Search on Paths)
        # We scan the known hashes (which are the full paths) for matches
        known_hashes = self._load_hashes(hashes_path)
        filename_matches = []
        query_lower = query_text.lower()
        
        for path in known_hashes:
            filename = os.path.basename(path).lower()
            # Exact match or partial match on filename gets a boost
            if query_lower in filename or filename in query_lower:
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    filename_matches.append({
                        "id": path,
                        "metadata": {"path": path, "type": "code", "boosted": True},
                        "document": content
                    })
                except Exception:
                    continue
        
        # 2. Vector Search (Semantic)
        client = chromadb.PersistentClient(path=os.path.join(indices_dir, "chroma_db"))
        vector_ids = []
        vector_metadatas = []
        vector_documents = []

        try:
            collection = client.get_collection(name="project_context")
            results = collection.query(
                query_texts=[query_text],
                n_results=n_results
            )
            # Flatten results
            vector_ids = results.get("ids", [[]])[0]
            vector_metadatas = results.get("metadatas", [[]])[0]
            vector_documents = results.get("documents", [[]])[0]
        except Exception:
            pass

        # 3. Merge Results
        final_ids = []
        final_metadatas = []
        final_documents = []
        seen_paths = set()

        # Boosted/Filename matches first
        for item in filename_matches:
            if item["id"] not in seen_paths:
                final_ids.append(item["id"])
                final_metadatas.append(item["metadata"])
                final_documents.append(item["document"])
                seen_paths.add(item["id"])

        # Then vector results (if not already seen)
        for vid, vmeta, vdoc in zip(vector_ids, vector_metadatas, vector_documents):
            if vid not in seen_paths:
                final_ids.append(vid)
                final_metadatas.append(vmeta)
                final_documents.append(vdoc)
                seen_paths.add(vid)

        # Truncate to total n_results if needed (or keep a bit more if boosted)
        return {
            "ids": [final_ids],
            "metadatas": [final_metadatas],
            "documents": [final_documents]
        }
