"""Merge partial settings updates and validate transcription options."""

from typing import Any, Dict, FrozenSet

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


def validate_transcription_model(settings: Dict[str, Any]) -> None:
    model = settings.get("transcription", {}).get("model")
    if model is None:
        return
    if model not in WHISPER_MODEL_IDS:
        raise ValueError(
            f"Unsupported transcription model {model!r}. "
            f"Use one from GET /transcription/models."
        )
