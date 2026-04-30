"""Optional GPU pack: install CUDA-capable wheels via pip (configured by env).

Used when the base distribution ships CPU-only CTranslate2; maintainers set
``WISPR_GPU_PIP_INSTALL_ARGS`` so users can pull GPU binaries on demand.

Environment (packaged / production):

- ``WISPR_GPU_PIP_INSTALL_ARGS`` — Arguments appended after ``python -m pip install``,
  e.g. ``--upgrade ctranslate2`` or, with an extra index,
  ``--upgrade ctranslate2 --extra-index-url https://...`` (quote paths with spaces).
- ``WISPR_GPU_PACK_USER_HINT`` — Optional short line of help text for the Settings UI.

If ``WISPR_GPU_PIP_INSTALL_ARGS`` is unset, :func:`gpu_pack_install_configured` is false
and the installer control is hidden.
"""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
import sys
from typing import Any, Dict

from .settings_util import cuda_available

LOGGER = logging.getLogger(__name__)

_ENV_PIP_ARGS = "WISPR_GPU_PIP_INSTALL_ARGS"
_ENV_USER_HINT = "WISPR_GPU_PACK_USER_HINT"


def _pip_install_argv() -> list[str] | None:
    raw = os.environ.get(_ENV_PIP_ARGS, "").strip()
    if not raw:
        return None
    try:
        extra = shlex.split(raw, posix=os.name != "nt")
    except ValueError as e:
        LOGGER.warning("Invalid %s: %s", _ENV_PIP_ARGS, e)
        return None
    if not extra:
        return None
    return [sys.executable, "-m", "pip", "install", *extra]


def nvidia_smi_on_path() -> bool:
    return shutil.which("nvidia-smi") is not None


def gpu_pack_install_configured() -> bool:
    return _pip_install_argv() is not None


def get_capabilities() -> Dict[str, Any]:
    hint = os.environ.get(_ENV_USER_HINT, "").strip() or None
    return {
        "cuda_available": cuda_available(),
        "nvidia_smi_found": nvidia_smi_on_path(),
        "gpu_pack_install_configured": gpu_pack_install_configured(),
        "gpu_pack_user_hint": hint,
    }


def install_gpu_pack(on_output=None) -> Dict[str, Any]:
    """Run pip install for GPU pack. Caller must restart the process to load new libs."""
    argv = _pip_install_argv()
    if argv is None:
        return {
            "ok": False,
            "error": "GPU pack install is not configured. Set WISPR_GPU_PIP_INSTALL_ARGS.",
        }
    if not nvidia_smi_on_path():
        LOGGER.warning("nvidia-smi not found; GPU pack install may still be requested")
    
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        
        stdout_tail = []
        for line in proc.stdout:
            if on_output:
                on_output(line.strip())
            stdout_tail.append(line)
            if len(stdout_tail) > 100:
                stdout_tail.pop(0)
                
        proc.wait(timeout=900)
        
    except subprocess.TimeoutExpired:
        if 'proc' in locals():
            proc.kill()
        return {"ok": False, "error": "pip install timed out (15 min)."}
    except OSError as e:
        return {"ok": False, "error": str(e)}

    if proc.returncode != 0:
        tail_out = "".join(stdout_tail)
        LOGGER.error("GPU pack pip failed rc=%s\n%s", proc.returncode, tail_out)
        return {
            "ok": False,
            "error": f"pip exited with code {proc.returncode}. Check logs.",
            "stdout_tail": tail_out,
        }

    LOGGER.info("GPU pack pip install finished successfully")
    return {
        "ok": True,
        "message": "GPU libraries installed. Restart the Wispr backend for CUDA to take effect.",
    }
