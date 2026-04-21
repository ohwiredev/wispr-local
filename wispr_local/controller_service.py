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
from .settings_util import merge_settings, validate_transcription_model

LOGGER = logging.getLogger(__name__)

class WisprLocalService:
    def __init__(self, settings_path: Path):
        self.settings_manager = SettingsManager(settings_path)
        self.settings = self.settings_manager.load()

        self.recorder = AudioRecorder(self.settings["audio"])
        self.transcriber = WhisperTranscriber(self.settings["transcription"])
        self.correction_resolver = CorrectionResolver(self.settings["correction"])
        self.text_processor = TextProcessor(
            self.settings["text_processing"],
            correction_resolver=self.correction_resolver,
        )
        self.output_manager = TextOutputManager(self.settings["output"])

        self.last_typed_text = ""
        self.is_recording = False
        self.is_processing = False
        self._process_lock = threading.Lock()

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

    def start_recording(self):
        if self.is_recording: return
        self.output_manager.save_target_window()
        self.recorder.start()
        self.is_recording = True

    def stop_recording_and_process(self):
        if not self.is_recording: return
        self.is_recording = False
        audio = self.recorder.stop()
        
        if audio.size == 0:
            return

        self.is_processing = True
        threading.Thread(target=self._process, args=(audio,), daemon=True).start()

    def _process(self, audio):
        with self._process_lock:
            try:
                text = self.transcriber.transcribe(audio)
                processed = self.text_processor.process(text)

                if processed.text:
                    self.output_manager.copy_to_clipboard(processed.text)
                    if processed.is_correction and self.last_typed_text:
                        self.output_manager.replace_previous_and_type(self.last_typed_text, processed.text)
                    else:
                        self.output_manager.type_text(processed.text)
                    self.last_typed_text = processed.text
            finally:
                self.is_processing = False

    def update_settings(self, patch: dict):
        """Apply a partial or full settings dict, persist, and refresh components."""
        merged = merge_settings(self.settings_manager.defaults, self.settings)
        merged = merge_settings(merged, patch)
        validate_transcription_model(merged)

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

    def _load_model_async(self, transcription_settings: dict):
        try:
            self.transcriber.update_settings(transcription_settings)
            self.model_loading_error = None
            LOGGER.info("Model %s loaded successfully", self.model_loading_name)
        except Exception as e:
            LOGGER.exception("Failed to load model %s", self.model_loading_name)
            self.model_loading_error = str(e)
        finally:
            self.model_loading = False
