import os
import json
import subprocess
import sys
from pathlib import Path

class RemoteIndexer:
    """
    Orchestrates indexing of remote repositories via SSH without full downloads.
    Deploys an ephemeral script to the VPS, retrieves a JSON index, and cleans up.
    """
    
    # This script runs on the remote VPS (Python 3, standard lib only)
    REMOTE_SCRIPT = """
import os
import json
import hashlib
import sys

def index_dir(path, extensions_str, exclude_dirs_str=""):
    exts = [e.strip() for e in extensions_str.split(',') if e.strip()]
    custom_excludes = [e.strip() for e in exclude_dirs_str.split(',') if e.strip()]
    
    results = []
    
    # Normalize path
    path = os.path.abspath(os.path.expanduser(path))
    
    if not os.path.exists(path):
        print(json.dumps({"error": f"Path not found: {path}"}))
        return

    # Standard + Custom excludes
    skip_dirs = {".git", "node_modules", "__pycache__", ".ace"} | set(custom_excludes)

    for root, dirs, filenames in os.walk(path):
        # Skip excluded dirs in-place to optimize walk
        dirs[:] = [d for d in dirs if d not in skip_dirs]
            
        for f in filenames:
            if any(f.endswith(e) for e in exts):
                full_path = os.path.join(root, f)
                try:
                    # Get basic info and a snippet
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as fp:
                        content = fp.read()
                    
                    results.append({
                        "path": full_path,
                        "size": len(content),
                        "hash": hashlib.md5(content.encode()).hexdigest()[:12],
                        "snippet": content[:2500] 
                    })
                    
                    # Streaming Progress to stderr
                    if len(results) % 25 == 0:
                        sys.stderr.write(f"[PROGRESS] {len(results)} files indexed...\\n")
                        sys.stderr.flush()

                except Exception:
                    pass
                    
    print(json.dumps({
        "files": results,
        "count": len(results),
        "root": path
    }))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing path argument"}))
        sys.exit(1)
    
    target_path = sys.argv[1]
    exts = sys.argv[2] if len(sys.argv) > 2 else ".py,.js,.ts,.html,.css,.json,.md"
    excludes = sys.argv[3] if len(sys.argv) > 3 else ""
    index_dir(target_path, exts, excludes)
"""

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.remotes_config_path = self.project_path / ".ace" / "remotes.json"

    def _load_remotes_config(self) -> dict:
        if self.remotes_config_path.exists():
            try:
                with open(self.remotes_config_path, "r") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _parse_ssh_config_for_alias(self, alias: str) -> dict:
        """Parse ~/.ssh/config to extract IdentityFile and HostName for an alias."""
        ssh_config_path = Path.home() / ".ssh" / "config"
        result = {}
        
        if not ssh_config_path.exists():
            return result
            
        try:
            with open(ssh_config_path, "r") as f:
                current_host = None
                for line in f:
                    line = line.strip()
                    if line.lower().startswith("host "):
                        current_host = line.split()[1]
                    elif current_host == alias:
                        if line.lower().startswith("identityfile"):
                            result["identity_file"] = line.split(None, 1)[1]
                        elif line.lower().startswith("hostname"):
                            result["hostname"] = line.split(None, 1)[1]
                        elif line.lower().startswith("user"):
                            result["user"] = line.split(None, 1)[1]
        except Exception:
            pass
        return result

    def _resolve_ssh_params(self, env_name: str, overrides: dict) -> dict:
        """Determines SSH command parameters based on config file and overrides."""
        config = self._load_remotes_config().get(env_name, {})
        
        # Priority: explicit overrides > config file
        ssh_alias = overrides.get("ssh_alias") or config.get("ssh_alias")
        ssh_host = overrides.get("ssh_host") or config.get("ssh_host")
        identity_file = overrides.get("identity_file") or config.get("identity_file")
        remote_path = overrides.get("remote_path") or config.get("remote_path")
        exclude_dirs = overrides.get("exclude_dirs") or config.get("exclude_dirs", "")
        
        if not (ssh_alias or ssh_host):
            raise ValueError(f"No SSH host or alias found for environment '{env_name}'")
        if not remote_path:
            raise ValueError(f"No remote path specified for environment '{env_name}'")
        
        # If using an alias, try to extract IdentityFile from ~/.ssh/config
        if ssh_alias and not identity_file:
            ssh_config_data = self._parse_ssh_config_for_alias(ssh_alias)
            if "identity_file" in ssh_config_data:
                identity_file = ssh_config_data["identity_file"]
            
        # Build base SSH command with robustness options
        ssh_base = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no"]
        
        if identity_file:
            # Resolve ~ and relative paths
            id_path = Path(identity_file).expanduser()
            if not id_path.is_absolute():
                id_path = self.project_path / id_path
            ssh_base.extend(["-i", str(id_path)])
            
        target = ssh_alias if ssh_alias else ssh_host
        ssh_base.append(target)
        
        return {
            "ssh_base": ssh_base,
            "remote_path": remote_path,
            "target": target,
            "exclude_dirs": exclude_dirs
        }

    def count_remote_files(self, env_name: str, **overrides) -> dict:
        """Phase 1: Fast count of remote files (Dry-Run)."""
        params = self._resolve_ssh_params(env_name, overrides)
        ssh_base = params["ssh_base"]
        remote_path = params["remote_path"]
        
        # Build find command for extensions
        exts = overrides.get("file_extensions") or ".py,.js,.ts,.html,.css,.json,.md"
        ext_list = [e.strip() for e in exts.split(',') if e.strip()]
        
        # Skip certain dirs in count as well
        skip_pattern = "-not -path '*/.*' -not -path '*/node_modules/*' -not -path '*/__pycache__/*'"
        if params["exclude_dirs"]:
            for d in params["exclude_dirs"].split(','):
                skip_pattern += f" -not -path '*/{d.strip()}/*'"

        find_parts = []
        for ext in ext_list:
            find_parts.append(f"-name '*{ext}'")
        
        find_cmd = f"find {remote_path} -type f \\( {' -o '.join(find_parts)} \\) {skip_pattern} | wc -l"
        
        try:
            sys.stderr.write(f"🌐 Connecting for dry-run: {params['target']}...\n")
            process = subprocess.run(ssh_base + [find_cmd], capture_output=True, text=True, check=True, timeout=60)
            count = int(process.stdout.strip())
            return {
                "status": "pending",
                "env_name": env_name,
                "file_count": count,
                "message": f"📊 Found {count} files to index in {env_name}. Proceed with ace_sync_remote_execute?"
            }
        except subprocess.TimeoutExpired:
            raise RuntimeError("SSH command timed out after 60 seconds. Check connection.")
        except Exception as e:
            raise RuntimeError(f"Failed to count remote files: {str(e)}")

    def sync_remote(self, env_name: str, **overrides) -> dict:
        """
        Executes the remote sync flow:
        1. Deploy ephemeral script via SSH stdin
        2. Run script on remote and capture JSON output
        3. Clean up remote script
        """
        params = self._resolve_ssh_params(env_name, overrides)
        ssh_base = params["ssh_base"]
        remote_path = params["remote_path"]
        exclude_dirs = params["exclude_dirs"]
        
        exts = overrides.get("file_extensions") or ".py,.js,.ts,.html,.css,.json,.md"

        # 1. Deploy script
        deploy_cmd = (
            f"cat > /tmp/ace_remote_idx.py << 'EOFSCRIPT'\n"
            f"{self.REMOTE_SCRIPT}\n"
            f"EOFSCRIPT"
        )
        try:
            subprocess.run(ssh_base + [deploy_cmd], check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to deploy remote script: {e.stderr}")

        # 2. Execute script with Streaming Progress
        exec_cmd = f"python3 /tmp/ace_remote_idx.py '{remote_path}' '{exts}' '{exclude_dirs}'"
        
        try:
            sys.stderr.write(f"🚀 Executing remote indexing indexing on {params['target']}...\n")
            
            # Use Popen to read stderr in real-time
            process = subprocess.Popen(
                ssh_base + [exec_cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout_data = []
            
            # Monitoring threads or simple select/loop
            while True:
                # Read stderr for progress messages
                line = process.stderr.readline()
                if line:
                    if "[PROGRESS]" in line:
                        sys.stderr.write(line) # Pipe to local stderr
                    continue
                
                # Read stdout for final JSON
                stdout_line = process.stdout.readline()
                if stdout_line:
                    stdout_data.append(stdout_line)
                
                if process.poll() is not None:
                    # Final read of remaining stdout and stderr
                    stdout_data.append(process.stdout.read())
                    # Read any remaining stderr
                    while True:
                        remaining_stderr_line = process.stderr.readline()
                        if not remaining_stderr_line:
                            break
                        if "[PROGRESS]" in remaining_stderr_line:
                            sys.stderr.write(remaining_stderr_line)
                    break
                    
            process.wait()
            output = "".join(stdout_data).strip()
            
            # Find the JSON part
            json_start = output.find('{"')
            if json_start == -1:
                raise ValueError(f"No valid JSON found in remote output. Stderr: {process.stderr.read()}")
            
            data = json.loads(output[json_start:])
            if "error" in data:
                raise RuntimeError(f"Remote error: {data['error']}")
                
            data["env_name"] = env_name
            return data
            
        except Exception as e:
            raise RuntimeError(f"Failed to execute remote indexing: {str(e)}")
        finally:
            # 3. Cleanup
            subprocess.run(ssh_base + ["rm -f /tmp/ace_remote_idx.py"], check=False)

    def save_remote_cache(self, env_name: str, data: dict):
        """Saves the remote index data to a local cache file."""
        cache_dir = self.project_path / ".ace" / "remote_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        cache_file = cache_dir / f"{env_name}.json"
        with open(cache_file, "w") as f:
            json.dump(data, f, indent=2)
        return cache_file
