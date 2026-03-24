import os
import sys
import subprocess
import time

def ensure_optimal_onnx():
    """
    Checks if ONNX Runtime GPU is needed and installs it.
    Uses a flag file to ensure this only runs once.
    """
    flag_path = os.path.expanduser("~/.ace/gpu_bootstrapped")
    
    # 1. Idempotency Check
    if os.path.exists(flag_path):
        return

    try:
        # Create .ace directory if it doesn't exist
        os.makedirs(os.path.dirname(flag_path), exist_ok=True)

        # 2. Environment detection
        is_windows = sys.platform == "win32"
        has_nvidia = False
        try:
            res = subprocess.run(["nvidia-smi"], capture_output=True, timeout=10)
            if res.returncode == 0:
                has_nvidia = True
        except:
            pass
            
        # Target package selection: 
        # - Windows: directml is the ultimate zero-config (works on all GPUs, no extra DLLs needed)
        # - Linux/Other with NVIDIA: gpu (requires CUDA/cuDNN)
        target_pkg = None
        if is_windows:
            target_pkg = "onnxruntime-directml"
        elif has_nvidia:
            target_pkg = "onnxruntime-gpu"
        
        if not target_pkg:
            with open(flag_path, "w") as f:
                f.write("cpu")
            return

        # 3. Attempt to install the target package
        sys.stderr.write(f"[ACE] Detected hardware acceleration potential ({target_pkg}). Initializing (first time setup)...\n")
        
        install_success = False
        # Try uv first, then pip
        methods = [
            ["uv", "pip", "install", target_pkg, "--force-reinstall", "-q"],
            [sys.executable, "-m", "pip", "install", target_pkg, "--force-reinstall", "-q", "--no-input"]
        ]
        
        for cmd in methods:
            try:
                # We use a long timeout as the package is large
                process = subprocess.run(cmd, timeout=300, capture_output=True, text=True)
                if process.returncode == 0:
                    install_success = True
                    break
            except Exception:
                continue
        
        if not install_success:
            sys.stderr.write(f"[ACE] Warning: Failed to install {target_pkg}. Falling back to CPU.\n")
            return

        # 4. Verify installation
        try:
            import onnxruntime as ort
            providers = ort.get_available_providers()
            active_p = None
            
            if "DmlExecutionProvider" in providers:
                active_p = "dml"
            elif "CUDAExecutionProvider" in providers:
                active_p = "cuda"
            
            if active_p:
                sys.stderr.write(f"[ACE] Hardware acceleration active ({active_p.upper()}).\n")
                with open(flag_path, "w") as f:
                    f.write(active_p)
            else:
                sys.stderr.write(f"[ACE] {target_pkg} installed but no accelerator provider found. Using CPU.\n")
                with open(flag_path, "w") as f:
                    f.write("cpu")
        except Exception as e:
            sys.stderr.write(f"[ACE] Error during hardware acceleration verification: {e}\n")
            
    except Exception as e:
        sys.stderr.write(f"[ACE] Unexpected error in GPU bootstrap: {e}\n")

if __name__ == "__main__":
    ensure_optimal_onnx()

# --- High-Performance GPU Targeting ---
try:
    from functools import cached_property
    from typing import List, Optional, Any
    import onnxruntime as ort
    from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

    class NvidiaONNXEmbedding(ONNXMiniLM_L6_V2):
        """
        Custom embedding function that forces DirectML to use a specific device_id.
        On hybrid laptops: device_id=0 is often AMD iGPU, device_id=1 is NVIDIA dGPU.
        """
        def __init__(self, device_id: int = 1, preferred_providers: Optional[List[str]] = None):
            # If not specified, we default to DML + CPU
            if preferred_providers is None:
                preferred_providers = ["DmlExecutionProvider", "CPUExecutionProvider"]
            
            super().__init__(preferred_providers=preferred_providers)
            self._device_id = device_id

        @cached_property
        def model(self) -> Any:
            # Replicate ChromaDB's model initialization but with provider_options
            if not set(self._preferred_providers).issubset(set(ort.get_available_providers())):
                 # Fallback to defaults if preferred are not available
                 self._preferred_providers = ort.get_available_providers()

            so = ort.SessionOptions()
            so.log_severity_level = 3
            so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            # Construct provider_options for each provider
            # device_id only applies to DmlExecutionProvider
            p_options = []
            for p in self._preferred_providers:
                if p == "DmlExecutionProvider":
                    p_options.append({"device_id": int(self._device_id)})
                else:
                    p_options.append({})

            model_path = os.path.join(self.DOWNLOAD_PATH, self.EXTRACTED_FOLDER_NAME, "model.onnx")
            
            # Ensure model exists before creating session
            self._download_model_if_not_exists()
            
            try:
                return ort.InferenceSession(
                    model_path,
                    providers=self._preferred_providers,
                    provider_options=p_options,
                    sess_options=so
                )
            except Exception as e:
                sys.stderr.write(f"[NvidiaONNX] Warning: Failed to init with device_id={self._device_id}: {e}. Falling back to default.\n")
                return ort.InferenceSession(
                    model_path,
                    providers=self._preferred_providers,
                    sess_options=so
                )
except ImportError:
    # If chromadb or onnxruntime is missing, this class won't be available
    # but the bootstrap process will handle the installation later.
    pass
