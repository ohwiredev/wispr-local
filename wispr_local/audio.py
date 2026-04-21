import sounddevice as sd
import numpy as np
import logging

LOGGER = logging.getLogger(__name__)

class AudioRecorder:
    def __init__(self, settings):
        self.device = settings.get("device", None)
        self.sample_rate = settings.get("sample_rate", 16000)
        self.channels = 1
        self.stream = None
        self._frames = []

    def start(self):
        self._frames = []
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            device=self.device,
            channels=self.channels,
            callback=self._callback
        )
        self.stream.start()
        LOGGER.info("Recording started")

    def stop(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        LOGGER.info("Recording stopped")
        if not self._frames:
            return np.array([], dtype=np.float32)
        return np.concatenate(self._frames, axis=0).flatten()

    def _callback(self, indata, frames, time, status):
        if status:
            LOGGER.warning("Audio status: %s", status)
        self._frames.append(indata.copy())

    def update_settings(self, settings):
        self.device = settings.get("device", None)
        self.sample_rate = settings.get("sample_rate", 16000)
