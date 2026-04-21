"""Merge partial settings updates and validate transcription options."""

import logging
from typing import Any, Dict, FrozenSet

LOGGER = logging.getLogger(__name__)

# Sizes supported by faster-whisper via Hugging Face / local names (common set).
WHISPER_MODEL_IDS: FrozenSet[str] = frozenset(
    {
        "tiny",
        "tiny.en",
        "base",
        "base.en",
        "small",
        "small.en",
        "medium",
        "medium.en",
        "large-v1",
        "large-v2",
        "large-v3",
        "distil-large-v2",
        "distil-large-v3",
    }
)


def merge_settings(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-merge patch into base (dict values recurse; other values replace)."""
    out: Dict[str, Any] = dict(base)
    for key, value in patch.items():
        if (
            key in out
            and isinstance(out[key], dict)
            and isinstance(value, dict)
        ):
            out[key] = merge_settings(out[key], value)
        else:
            out[key] = value
    return out


def cuda_available() -> bool:
    """True if CTranslate2 can use at least one CUDA device (faster-whisper GPU)."""
    try:
        import ctranslate2

        fn = getattr(ctranslate2, "get_cuda_device_count", None)
        if fn is None:
            return False
        return int(fn()) > 0
    except Exception:
        LOGGER.debug("CUDA not available or ctranslate2 check failed", exc_info=True)
        return False


def validate_transcription_model(settings: Dict[str, Any]) -> None:
    model = settings.get("transcription", {}).get("model")
    if model is None:
        return
    if model not in WHISPER_MODEL_IDS:
        raise ValueError(
            f"Unsupported transcription model {model!r}. "
            f"Use one from GET /transcription/models."
        )


def validate_transcription_device(settings: Dict[str, Any]) -> None:
    txn = settings.get("transcription") or {}
    device = txn.get("device")
    if device is None:
        return
    if device not in ("cpu", "cuda"):
        raise ValueError(
            f"Unsupported transcription device {device!r}. Use 'cpu' or 'cuda'."
        )
    if device == "cuda" and not cuda_available():
        raise ValueError(
            "CUDA is not available. Install a GPU-enabled CTranslate2 build and "
            "NVIDIA drivers, or choose CPU."
        )
