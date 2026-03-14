import os
import hashlib
import fnmatch
import sys

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

class FileScanner:
    # Standard noise patterns (Explicit Blacklist)
    IGNORED_PATTERNS = [
        "*.min.js", "*.min.css", "*.map",
        "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
        "*.svg", "*.png", "*.jpg", "*.jpeg", "*.gif", "*.ico",
        "*.zip", "*.tar", "*.gz", "*.rar", "*.7z", "*.pdf", 
        "*.exe", "*.dll", "*.so", "*.dylib", "*.bin",
        "*.pyc", "*.pyo"
    ]
    
    # [v0.8.2] Exhaustive hard-block set — never traverse these directories
    BLOCKED_DIRS = {
        # ACE / VCS
        '.ace', '.git', '.svn', '.hg',
        # Virtual environments (all naming conventions)
        'venv', '.venv', 'env', '.env', 'virtualenv', '.virtualenv',
        # Python cache / test artifacts
        '__pycache__', '.mypy_cache', '.pytest_cache', '.tox', '.cache',
        'site-packages', 'dist-packages', 'lib', 'lib64',
        # Build / dist
        'dist', 'build', 'out', 'bin', 'obj', 'target', 'release', 'debug',
        # Package managers
        'node_modules', 'bower_components', 'jspm_packages',
        'vendor', 'Pods', 'packages', 'wheels',
        # IDE
        '.idea', '.vscode', '.eclipse', '.settings',
        # Mobile / Game
        'Builds', 'Library', 'Temp', 'DerivedData',
    }

    def compute_file_hash(self, filepath: str) -> str:
        hasher = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception:
            return ""

    def is_binary_file(self, filepath: str) -> bool:
        """Check first 1024 bytes for null byte to detect binary files."""
        try:
            with open(filepath, "rb") as f:
                chunk = f.read(1024)
                return b'\0' in chunk
        except Exception:
            return True # If we can't read it, assume it's not text code

    def should_ignore(self, filepath: str, gitignore: GitignoreParser) -> bool:
        filename = os.path.basename(filepath)
        
        # 1. Explicit Pattern Blacklist
        for pattern in self.IGNORED_PATTERNS:
            if fnmatch.fnmatch(filename, pattern):
                sys.stderr.write(f"[Scanner] Ignoring {filename} (Matched pattern: {pattern})\n")
                return True
        
        # 2. Gitignore Check
        if gitignore.match(filepath):
            sys.stderr.write(f"[Scanner] Ignoring {filename} (Matched .gitignore)\n")
            return True
            
        # 3. Binary Check
        if self.is_binary_file(filepath):
            sys.stderr.write(f"[Scanner] Ignoring {filename} (Detected Binary)\n")
            return True
            
        return False

    def scan_files(self, project_path: str, known_hashes: dict, force: bool = False, extra_ignore_dirs: list = None):
        """Walk project files and detect changes/deletions."""
        new_hashes = {}
        files_to_index = []
        ids_to_delete = []
        
        gitignore = GitignoreParser(project_path)
        blocked_effective = self.BLOCKED_DIRS | set(extra_ignore_dirs or [])

        for root, dirs, files in os.walk(project_path):
            # Prune directories
            dirs[:] = [d for d in dirs if d not in blocked_effective]
            
            if gitignore.match(root):
                dirs[:] = []
                continue

            for file in files:
                filepath = os.path.join(root, file).replace("\\", "/") # Universal paths
                
                if self.should_ignore(filepath, gitignore):
                    continue
                
                # Whitelist Extensions
                if not file.endswith((
                    ".html", ".htm", ".css", ".scss", ".less", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte",
                    ".py", ".php", ".rb", ".go", ".java", ".cs", ".rs", ".kt", ".swift", ".dart", ".sh",
                    ".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".env", ".sql", ".md", ".txt"
                )): continue
                
                current_hash = self.compute_file_hash(filepath)
                new_hashes[filepath] = current_hash
                
                if force or known_hashes.get(filepath) != current_hash:
                    files_to_index.append(filepath)
        
        # Detect deleted files
        for path in known_hashes:
            if path not in new_hashes:
                ids_to_delete.append(path)
                
        return files_to_index, ids_to_delete, new_hashes

    def list_files_on_disk(self, project_path: str) -> list:
        """Utility for index status check."""
        files_on_disk = []
        gitignore = GitignoreParser(project_path)
        for root, dirs, files in os.walk(project_path):
            # Basic pruning for performance
            if ".ace" in dirs: dirs.remove(".ace")
            if ".git" in dirs: dirs.remove(".git")
            
            if gitignore.match(root):
                dirs[:] = []
                continue
                
            for file in files:
                filepath = os.path.join(root, file).replace("\\", "/")
                if not self.should_ignore(filepath, gitignore):
                    if file.endswith((".html", ".htm", ".css", ".scss", ".less", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".py", ".php", ".rb", ".go", ".java", ".cs", ".rs", ".kt", ".swift", ".dart", ".sh", ".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".env", ".sql", ".md", ".txt")):
                        files_on_disk.append(filepath)
        return files_on_disk
