import sounddevice as sd
import numpy as np
import logging

LOGGER = logging.getLogger(__name__)


def _trim_silence(audio: np.ndarray, threshold: float = 0.01,
                  margin: int = 1600) -> np.ndarray:
    """Strip leading/trailing silence so Whisper processes less audio."""
    indices = np.where(np.abs(audio) > threshold)[0]
    if len(indices) == 0:
        return np.array([], dtype=np.float32)
    start = max(0, indices[0] - margin)
    end = min(len(audio), indices[-1] + margin)
    return audio[start:end]


class AudioRecorder:
    def __init__(self, settings):
        self.device = settings.get("device", None)
        self.sample_rate = settings.get("sample_rate", 16000)
        self.channels = 1
        self.stream = None
        self._frames = []


    def stop(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        LOGGER.info("Recording stopped")
        if not self._frames:
            return np.array([], dtype=np.float32)
        raw = np.concatenate(self._frames, axis=0).flatten()
        return _trim_silence(raw)

    def _callback(self, indata, frames, time, status):
        if status:
            LOGGER.warning("Audio status: %s", status)
        self._frames.append(indata.copy())

    def update_settings(self, settings):
        self.device = settings.get("device", None)
        self.sample_rate = settings.get("sample_rate", 16000)
