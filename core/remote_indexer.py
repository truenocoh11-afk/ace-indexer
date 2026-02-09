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

def index_dir(path, extensions_str):
    exts = [e.strip() for e in extensions_str.split(',') if e.strip()]
    results = []
    
    # Normalize path
    path = os.path.abspath(os.path.expanduser(path))
    
    if not os.path.exists(path):
        print(json.dumps({"error": f"Path not found: {path}"}))
        return

    for root, _, filenames in os.walk(path):
        # Skip common bulky/hidden dirs
        if any(d in root for d in [".git", "node_modules", "__pycache__", ".ace"]):
            continue
            
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
                        "snippet": content[:2500] # Enough for local contextual embedding
                    })
                except Exception as e:
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
    index_dir(target_path, exts)
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

    def _resolve_ssh_params(self, env_name: str, overrides: dict) -> dict:
        """Determines SSH command parameters based on config file and overrides."""
        config = self._load_remotes_config().get(env_name, {})
        
        # Priority: explicit overrides > config file
        ssh_alias = overrides.get("ssh_alias") or config.get("ssh_alias")
        ssh_host = overrides.get("ssh_host") or config.get("ssh_host")
        identity_file = overrides.get("identity_file") or config.get("identity_file")
        remote_path = overrides.get("remote_path") or config.get("remote_path")
        
        if not (ssh_alias or ssh_host):
            raise ValueError(f"No SSH host or alias found for environment '{env_name}'")
        if not remote_path:
            raise ValueError(f"No remote path specified for environment '{env_name}'")
            
        # Build base SSH command
        ssh_base = ["ssh"]
        if identity_file:
            # Resolve relative to project path if needed
            id_path = Path(identity_file)
            if not id_path.is_absolute():
                id_path = self.project_path / id_path
            ssh_base.extend(["-i", str(id_path)])
            
        target = ssh_alias if ssh_alias else ssh_host
        ssh_base.append(target)
        
        return {
            "ssh_base": ssh_base,
            "remote_path": remote_path,
            "target": target
        }

    def sync_remote(self, env_name: str, **kwargs) -> dict:
        """
        Executes the remote sync flow:
        1. Deploy ephemeral script via SSH stdin
        2. Run script on remote and capture JSON output
        3. Clean up remote script
        """
        params = self._resolve_ssh_params(env_name, kwargs)
        ssh_base = params["ssh_base"]
        remote_path = params["remote_path"]
        
        exts = kwargs.get("file_extensions", ".py,.js,.ts,.html,.css,.json,.md")
        
        # 1. Deploy script
        # Using a heredoc-style cat to avoid needing SCP
        deploy_cmd = (
            f"cat > /tmp/ace_remote_idx.py << 'EOFSCRIPT'\n"
            f"{self.REMOTE_SCRIPT}\n"
            f"EOFSCRIPT"
        )
        try:
            subprocess.run(ssh_base + [deploy_cmd], check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to deploy remote script: {e.stderr}")

        # 2. Execute script
        exec_cmd = f"python3 /tmp/ace_remote_idx.py '{remote_path}' '{exts}'"
        try:
            process = subprocess.run(ssh_base + [exec_cmd], capture_output=True, text=True, check=True)
            output = process.stdout.strip()
            
            # Find the JSON part (in case of MOTD etc)
            json_start = output.find('{"')
            if json_start == -1:
                raise ValueError(f"No valid JSON found in remote output: {output}")
            
            data = json.loads(output[json_start:])
            if "error" in data:
                raise RuntimeError(f"Remote error: {data['error']}")
                
            # Add environment metadata
            data["env_name"] = env_name
            return data
            
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to execute remote indexing: {e.stderr}")
        except json.JSONDecodeError:
            raise RuntimeError(f"Invalid JSON received from remote")
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
