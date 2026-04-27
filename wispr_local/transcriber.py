import logging
import threading
from pathlib import Path
from typing import Optional

import numpy as np
import tqdm
from faster_whisper import WhisperModel
from faster_whisper.utils import _MODELS
from huggingface_hub import snapshot_download

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

        def update(self, n=1):
            result = super().update(n)
            if self.total and self.total > 100_000:
                transcriber.download_current += int(n)
                transcriber.load_step = "downloading"
            return result

    return _ProgressTqdm


class WhisperTranscriber:
    def __init__(self, settings):
        self.settings = settings
        self.model_path = Path("models")
        self.model: Optional[WhisperModel] = None
        self._lock = threading.Lock()

        self.load_step = "idle"
        self.load_error: Optional[str] = None
        self.download_current = 0
        self.download_total = 0

        self._load_model()

    def _load_model(self):
        with self._lock:
            model_name = self.settings.get("model", "base")
            device = self.settings.get("device", "cpu")
            compute_type = self.settings.get("compute_type", "int8")
            self.load_error = None
            try:
                self.load_step = "checking"
                self.download_current = 0
                self.download_total = 0
                LOGGER.info("Loading model %s on %s (%s)", model_name, device, compute_type)


                self.model = model
                self.load_step = "ready"
            except Exception as e:
                LOGGER.exception("Failed to load model: %s", e)
                self.model = None
                self.load_step = "error"
                self.load_error = str(e)

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
