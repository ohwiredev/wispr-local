import sys
import os
import json
import traceback

os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Ensure DLLs in the same directory are found when running as a bundled EXE
if getattr(sys, 'frozen', False):
    exe_dir = os.path.dirname(sys.executable)
    if exe_dir not in os.environ["PATH"]:
        os.environ["PATH"] = exe_dir + os.pathsep + os.environ["PATH"]
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(exe_dir)
    # Also check _MEIPASS for --onefile mode or bundled datas
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        if meipass not in os.environ["PATH"]:
            os.environ["PATH"] = meipass + os.pathsep + os.environ["PATH"]
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(meipass)

from wispr_local.controller_service import WisprLocalService
from wispr_local.paths import get_settings_path, get_app_root
from wispr_local.gpu_pack import get_capabilities, install_gpu_pack

def main():
    service = WisprLocalService(get_settings_path())

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
            
        try:
            req = json.loads(line)
            req_id = req.get("id")
            method = req.get("method")
            params = req.get("params", {})
            
            result = None
            if method == "start_recording":
                service.start_recording()
                result = {"status": "recording"}
            elif method == "stop_recording":
                service.stop_recording_and_process()
                result = {"status": "processing"}
            elif method == "update_settings":
                settings_patch = params.get("settings", {})
                service.update_settings(settings_patch)
                result = {"status": "updated"}
            elif method == "get_capabilities":
                result = get_capabilities()
            elif method == "install_gpu_pack":
                def on_progress(line):
                    print(json.dumps({"event": "gpu-pack-progress", "data": {"line": line}}), flush=True)
                result = install_gpu_pack(on_output=on_progress)
            elif method == "get_status":
                result = service.get_status()
            else:
                if req_id is not None:
                    print(json.dumps({"id": req_id, "error": f"Unknown method: {method}"}), flush=True)
                continue
                
            if req_id is not None:
                print(json.dumps({"id": req_id, "result": result}), flush=True)
                
        except json.JSONDecodeError:
            print(json.dumps({"error": "Invalid JSON"}), flush=True)
        except Exception as e:
            err_msg = str(e)
            try:
                req_id = json.loads(line).get("id")
                if req_id is not None:
                    print(json.dumps({"id": req_id, "error": err_msg}), flush=True)
            except:
                print(json.dumps({"error": err_msg}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_path = get_app_root() / "crash.log"
        with open(log_path, "a") as f:
            f.write(f"\n--- Backend Crash ---\n")
            f.write(traceback.format_exc())
        raise e