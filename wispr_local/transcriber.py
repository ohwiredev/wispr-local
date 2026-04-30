import logging
import threading
from pathlib import Path
from typing import Optional

import numpy as np
import tqdm
from faster_whisper import WhisperModel
from faster_whisper.utils import _MODELS
from huggingface_hub import snapshot_download
from .paths import get_models_path
from .gpu_pack import cuda_available

# Robust tqdm monkeypatching for huggingface_hub
_hf_tqdm_module = None
try:
    import huggingface_hub.utils._progress as _mod
    _hf_tqdm_module = _mod
except ImportError:
    try:
        import huggingface_hub.utils as _mod
        if hasattr(_mod, 'tqdm'):
            _hf_tqdm_module = _mod
    except ImportError:
        pass

LOGGER = logging.getLogger(__name__)


def _make_progress_tqdm(transcriber: "WhisperTranscriber"):
    """Build a tqdm subclass bound to a specific transcriber instance."""

    class _ProgressTqdm(tqdm.tqdm):
        def __init__(self, *args, **kwargs):
            kwargs["disable"] = False
            super().__init__(*args, **kwargs)
            if self.total and self.total > 100_000:
                transcriber.download_total += int(self.total)
                transcriber.load_step = "downloading"
                if transcriber.on_progress:
                    transcriber.on_progress()

        def update(self, n=1):
            result = super().update(n)
            if self.total and self.total > 100_000:
                transcriber.download_current += int(n)
                transcriber.load_step = "downloading"
                if transcriber.on_progress:
                    transcriber.on_progress()
            return result

    return _ProgressTqdm


class WhisperTranscriber:
    def __init__(self, settings, on_progress=None, on_status_change=None):
        self.settings = settings
        self.on_progress = on_progress
        self.on_status_change = on_status_change
        self.model_path = get_models_path()
        self.model: Optional[WhisperModel] = None
        self._lock = threading.Lock()
        self._load_thread = None

        self.load_step = "idle"
        self.load_error: Optional[str] = None
        self.download_current = 0
        self.download_total = 0

        self._load_model()

    def _load_model(self):
        if self._load_thread and self._load_thread.is_alive():
            return
        self._load_thread = threading.Thread(target=self._do_load_model, daemon=True)
        self._load_thread.start()

    def _do_load_model(self):
        with self._lock:
            model_name = self.settings.get("model", "base")
            device = self.settings.get("device", "cpu")
            compute_type = self.settings.get("compute_type", "int8")
            self.load_error = None
            try:
                self.load_step = "checking"
                if self.on_status_change: self.on_status_change()
                
                self.download_current = 0
                self.download_total = 0
                LOGGER.info("Preparing model %s", model_name)
                self.model_path.mkdir(parents=True, exist_ok=True)
                
                # 1. Map to repo ID if it's a known model name
                repo_id = model_name
                if model_name in _MODELS:
                    repo_id = _MODELS[model_name]
                elif "/" not in model_name: # Not a path or repo id
                    if "distil" in model_name:
                        # e.g. distil-large-v3 -> Systran/faster-distil-whisper-large-v3
                        name_part = model_name.replace("distil-", "")
                        repo_id = f"Systran/faster-distil-whisper-{name_part}"
                    else:
                        repo_id = f"Systran/faster-whisper-{model_name}"

                # 2. Explicitly download/verify with our progress class
                try:
                    self.load_step = "verifying"
                    if self.on_status_change: self.on_status_change()
                    
                    # We call snapshot_download directly to ensure progress is captured
                    snapshot_download(
                        repo_id=repo_id,
                        cache_dir=str(self.model_path),
                        tqdm_class=_make_progress_tqdm(self),
                        local_files_only=False
                    )
                except Exception as e:
                    LOGGER.warning("Snapshot download failed/interrupted, attempting offline load: %s", e)

                # 3. Load into WhisperModel
                self.load_step = "loading"
                if self.on_status_change: self.on_status_change()
                
                model = WhisperModel(
                    model_name,
                    device=device,
                    compute_type=compute_type,
                    download_root=str(self.model_path),
                )
                self.model = model
                self.load_step = "ready"
                if self.on_status_change: self.on_status_change()
                    
            except Exception as e:
                LOGGER.exception("Failed to load model: %s", e)
                self.model = None
                self.load_step = "error"
                self.load_error = str(e)
                if self.on_status_change: self.on_status_change()

    def transcribe(self, audio: np.ndarray, on_segment=None) -> str:
        """Transcribe audio. If *on_segment* is provided it is called with the
        cumulative text after each decoded segment (enables streaming UI)."""
        if self.model is None:
            return ""

        segments, _info = self.model.transcribe(
            audio,
            beam_size=1,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=300),
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
        )

        partial = ""
        for seg in segments:
            partial += seg.text
            if on_segment is not None:
                on_segment(partial.strip())

        return partial.strip()

    def update_settings(self, settings):
        old = self.settings
        self.settings = settings
        model_changed = (
            old.get("model") != settings.get("model")
            or old.get("device") != settings.get("device")
            or old.get("compute_type") != settings.get("compute_type")
        )
        if model_changed:
            self._load_model()
