import asyncio
import logging
import threading
from pathlib import Path
from pynput import keyboard
from .audio import AudioRecorder
from .config import SettingsManager
from .correction_resolver import CorrectionResolver
from .transcriber import WhisperTranscriber
from .text_processing import TextProcessor
from .output import TextOutputManager
from .settings_util import (
    cuda_available,
    merge_settings,
    validate_transcription_device,
    validate_transcription_model,
)

LOGGER = logging.getLogger(__name__)


class EventBus:
    """Simple pub/sub for SSE clients. Thread-safe across asyncio / threads."""

    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """Must be called once from the asyncio thread (e.g. on startup)."""
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    def publish(self, event: dict):
        """Safely enqueue *event* from any thread."""
        with self._lock:
            subs = list(self._subscribers)

        if not subs:
            return

        loop = self._loop
        if loop is not None and loop.is_running():
            for q in subs:
                loop.call_soon_threadsafe(self._safe_put, q, event)
        else:
            for q in subs:
                self._safe_put(q, event)

    @staticmethod
    def _safe_put(q: asyncio.Queue, event: dict):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


class WisprLocalService:
    def __init__(self, settings_path: Path):
        self.settings_manager = SettingsManager(settings_path)
        self.settings = self.settings_manager.load()
        self.cuda_available = cuda_available()

        self.recorder = AudioRecorder(self.settings["audio"])
        self.transcriber = WhisperTranscriber(self.settings["transcription"])
        if self.transcriber.load_step == "error":
            self.model_loading_error = self.transcriber.load_error
        self.correction_resolver = CorrectionResolver(self.settings["correction"])
        self.text_processor = TextProcessor(
            self.settings["text_processing"],
            correction_resolver=self.correction_resolver,
        )
        self.output_manager = TextOutputManager(self.settings["output"])

        self.last_typed_text = ""
        self.is_recording = False
        self.is_processing = False
        self.partial_text = ""
        self._process_lock = threading.Lock()
        self.events = EventBus()

        self.model_loading = False
        self.model_loading_name = ""
        self.model_loading_error = None

        self._hotkey_map = {
            "right_ctrl": keyboard.Key.ctrl_r,
            "left_ctrl": keyboard.Key.ctrl_l,
            "right_alt": keyboard.Key.alt_r,
            "left_alt": keyboard.Key.alt_l,
            "right_shift": keyboard.Key.shift_r,
            "left_shift": keyboard.Key.shift_l,
        }
        self._active_key = self._hotkey_map.get(
            self.settings.get("hotkey", {}).get("hold_key", "right_ctrl"),
            keyboard.Key.ctrl_r,
        )

        self._listener = None
        self._start_listener()

    def _start_listener(self):
        if self._listener is not None:
            self._listener.stop()

        self._listener = keyboard.Listener(
            on_press=self._handle_press,
            on_release=self._handle_release,
        )
        self._listener.daemon = True
        self._listener.start()
        LOGGER.info("Hotkey listener started for %s", self._active_key)

    def _handle_press(self, key):
        try:
            if key == self._active_key:
                if not self.is_recording:
                    LOGGER.info("Hotkey pressed: Starting recording")
                    self.start_recording()
        except Exception:
            LOGGER.exception("Error in hotkey press handler")

    def _handle_release(self, key):
        try:
            if key == self._active_key:
                if self.is_recording:
                    LOGGER.info("Hotkey released: Stopping recording")
                    self.stop_recording_and_process()
        except Exception:
            LOGGER.exception("Error in hotkey release handler")

    def _publish_status(self):
        self.events.publish(self._build_status())

    def _build_status(self) -> dict:
        return {
            "type": "status",
            "is_recording": self.is_recording,
            "is_processing": self.is_processing,
            "partial_text": self.partial_text,
            "last_text": self.last_typed_text,
            "model_loading": self.model_loading,
            "model_loading_name": self.model_loading_name,
            "model_loading_error": self.model_loading_error,
            "model_loading_step": self.transcriber.load_step,
            "model_download_current": self.transcriber.download_current,
            "model_download_total": self.transcriber.download_total,
            "cuda_available": self.cuda_available,
        }

    def start_recording(self):
        if self.is_recording: return
        self.output_manager.save_target_window()
        self.partial_text = ""
        self.recorder.start()
        self.is_recording = True
        self._publish_status()

    def stop_recording_and_process(self):
        if not self.is_recording: return
        self.is_recording = False
        audio = self.recorder.stop()
        
        if audio.size == 0:
            self._publish_status()
            return

        self.is_processing = True
        self._publish_status()
        threading.Thread(target=self._process, args=(audio,), daemon=True).start()

    def _process(self, audio):
        with self._process_lock:
            try:
                streamed_text = ""
                self.output_manager._release_modifiers()

                def on_segment(partial):
                    nonlocal streamed_text
                    self.partial_text = partial
                    self._publish_status()
                    delta = partial[len(streamed_text):]
                    if delta and self.output_manager._is_target_window_focused():
                        self.output_manager.stream_insert(delta)
                    streamed_text = partial

                text = self.transcriber.transcribe(audio, on_segment=on_segment)
                processed = self.text_processor.process(text)

                if processed.text:
                    self.output_manager.copy_to_clipboard(processed.text)
                    if streamed_text:
                        if processed.text != streamed_text:
                            self.output_manager.replace_previous_and_type(
                                streamed_text, processed.text,
                            )
                    elif processed.is_correction and self.last_typed_text:
                        self.output_manager.replace_previous_and_type(
                            self.last_typed_text, processed.text,
                        )
                    else:
                        self.output_manager.type_text(processed.text)
                    self.last_typed_text = processed.text
            finally:
                self.partial_text = ""
                self.is_processing = False
                self._publish_status()

    def update_settings(self, patch: dict):
        """Apply a partial or full settings dict, persist, and refresh components."""
        merged = merge_settings(self.settings_manager.defaults, self.settings)
        merged = merge_settings(merged, patch)
        validate_transcription_model(merged)
        validate_transcription_device(merged)

        old_model = self.settings.get("transcription", {}).get("model")
        new_model = merged.get("transcription", {}).get("model")
        model_changed = old_model != new_model

        self.settings = merged
        self.settings_manager.save(merged)
        self.recorder.update_settings(merged["audio"])
        self.correction_resolver.update_settings(merged["correction"])
        self.text_processor.update_settings(merged["text_processing"])
        self.output_manager.update_settings(merged["output"])

        new_key = self._hotkey_map.get(
            merged.get("hotkey", {}).get("hold_key", "right_ctrl"),
            keyboard.Key.ctrl_r,
        )
        if new_key != self._active_key:
            self._active_key = new_key
            self._start_listener()

        if model_changed:
            self.model_loading = True
            self.model_loading_name = new_model or ""
            self.model_loading_error = None
            threading.Thread(
                target=self._load_model_async,
                args=(merged["transcription"],),
                daemon=True,
            ).start()
        else:
            self.transcriber.update_settings(merged["transcription"])
            if self.transcriber.load_step == "error":
                self.model_loading_error = self.transcriber.load_error
            else:
                self.model_loading_error = None

    def _load_model_async(self, transcription_settings: dict):
        try:
            self.transcriber.update_settings(transcription_settings)
            if self.transcriber.load_step == "error":
                self.model_loading_error = self.transcriber.load_error or "Failed to load model"
                LOGGER.error("Failed to load model %s: %s", self.model_loading_name, self.model_loading_error)
            else:
                self.model_loading_error = None
                LOGGER.info("Model %s loaded successfully", self.model_loading_name)
        except Exception as e:
            LOGGER.exception("Failed to load model %s", self.model_loading_name)
            self.model_loading_error = str(e)
        finally:
            self.model_loading = False
