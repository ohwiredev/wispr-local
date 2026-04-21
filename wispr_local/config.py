import copy
import json
from pathlib import Path
from typing import Any, Dict

from .settings_util import merge_settings


class SettingsManager:
    def __init__(self, path: Path):
        self.path = path
        self.defaults: Dict[str, Any] = {
            "hotkey": {"hold_key": "right_ctrl"},
            "audio": {"sample_rate": 16000, "device": None},
            "transcription": {"model": "base", "device": "cpu", "compute_type": "int8"},
            "text_processing": {},
            "correction": {
                "enabled": True,
                "repo_id": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
                "model_filename": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
            },
            "output": {"method": "paste"},
        }

    def load(self) -> Dict[str, Any]:
        """Load saved settings and fill missing sections from defaults."""
        defaults = copy.deepcopy(self.defaults)
        if not self.path.exists():
            return defaults
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except Exception:
            return defaults
        if not isinstance(saved, dict):
            return defaults
        return merge_settings(defaults, saved)

    def save(self, settings: Dict[str, Any]):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4)
