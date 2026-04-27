import os
import subprocess
import shutil
import sys
from pathlib import Path

def bundle():
    print("Bundling Wispr Backend with PyInstaller (onedir mode)...")
    
    # Resolve paths
    root_dir = Path(__file__).parent.parent.absolute()
    app_py = root_dir / "app.py"
    
    # CUDA DLLs that should be bundled
    cuda_dlls = [
        "cublas64_12.dll",
        "cublasLt64_12.dll",
        "cudnn64_9.dll",
        "cudnn_cnn64_9.dll",
        "cudnn_engines_tensor_ir64_9.dll",
        "cudnn_ops64_9.dll",
        "nvrtc64_120_0.dll",
        "zlibwapi.dll"
    ]
    
    # Base command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--name", "wispr-backend",
        # Include the core package
        "--add-data", f"{root_dir / 'wispr_local'}{os.pathsep}wispr_local",
        # Common hidden imports for our stack
        "--hidden-import", "faster_whisper",
        "--hidden-import", "ctranslate2",
        "--hidden-import", "llama_cpp",
        "--hidden-import", "pynput.keyboard._win32",
        "--hidden-import", "pynput.mouse._win32",
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols",
        "--hidden-import", "uvicorn.protocols.http",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.lifespan",
        "--hidden-import", "uvicorn.lifespan.on",
        # Entry point
        str(app_py)
    ]
    
    # Add CUDA DLLs if they exist in root
    for dll in cuda_dlls:
        dll_path = root_dir / dll
        if dll_path.exists():
            # In onedir mode, putting them in '.' means they end up in the same dir as the EXE
            cmd.extend(["--add-data", f"{dll_path}{os.pathsep}."])
        else:
            print(f"Note: {dll} not found in root, skipping manual add (might be in venv).")

    # Run PyInstaller
    try:
        subprocess.run(cmd, check=True, cwd=str(root_dir))
    except subprocess.CalledProcessError as e:
        print(f"PyInstaller failed with exit code {e.returncode}")
        sys.exit(1)
    
    print("\nBundling complete!")
    print(f"Output directory: {root_dir / 'dist' / 'wispr-backend'}")
    print("Next step: Move this folder to 'src-tauri/resources' and update tauri.conf.json")

if __name__ == "__main__":
    bundle()
