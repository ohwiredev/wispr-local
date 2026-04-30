import asyncio
import logging
import threading
import time
from pathlib import Path
from pynput import keyboard
from .audio import AudioRecorder
from .config import SettingsManager
from .correction_resolver import CorrectionResolver
from .transcriber import WhisperTranscriber
from .text_processing import TextProcessor
from .output import TextOutputManager
from .paths import get_models_path
from .settings_util import (
    cuda_available,
    merge_settings,
    validate_transcription_device,
    validate_transcription_model,
)

LOGGER = logging.getLogger(__name__)


import sys
import json


class WisprLocalService:
    def __init__(self, settings_path: Path):
        self.settings_manager = SettingsManager(settings_path)
        self.settings = self.settings_manager.load()
        self.cuda_available = cuda_available()

        self.recorder = AudioRecorder(self.settings["audio"])
        self.last_typed_text = ""
        self.is_recording = False
        self.is_processing = False
        self.partial_text = ""
        self._process_lock = threading.Lock()

        self.model_loading = False
        self.model_loading_name = ""
        self.model_loading_error = None

        self.transcriber = WhisperTranscriber(
            self.settings["transcription"], 
            on_progress=self._publish_status,
            on_status_change=self._publish_status
        )
        if self.transcriber.load_step == "error":
            self.model_loading_error = self.transcriber.load_error

        self.correction_resolver = CorrectionResolver(self.settings["correction"])
        self.text_processor = TextProcessor(
            self.settings["text_processing"],
            correction_resolver=self.correction_resolver,
        )
        self.output_manager = TextOutputManager(self.settings["output"])

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
        print(json.dumps({"event": "wispr-status-update", "data": self._build_status()}), flush=True)

    def _build_status(self) -> dict:
        # Defensive checks for initialization race conditions
        is_recording = getattr(self, "is_recording", False)
        is_processing = getattr(self, "is_processing", False)
        partial_text = getattr(self, "partial_text", "")
        
        status = {
            "type": "status",
            "is_recording": is_recording,
            "is_processing": is_processing,
            "partial_text": partial_text,
            "last_text": getattr(self, "last_typed_text", ""),
        }

        if hasattr(self, "transcriber") and self.transcriber:
            status.update({
                "model_loading": self.transcriber.load_step not in ["ready", "idle", "error"],
                "model_loading_name": self.transcriber.settings.get("model", ""),
                "model_loading_error": self.transcriber.load_error,
                "model_loading_step": self.transcriber.load_step,
                "model_download_current": self.transcriber.download_current,
                "model_download_total": self.transcriber.download_total,
                "cuda_available": getattr(self, "cuda_available", False),
                "downloaded_models": self._get_downloaded_models(),
            })
        
        return status

    def get_status(self) -> dict:
        """Explicitly return current status (used on startup)."""
        return self._build_status()

    def _get_downloaded_models(self) -> list[str]:
        """Scan models directory for downloaded Whisper models."""
        models_path = get_models_path()
        if not models_path.exists():
            return []
        
        downloaded = []
        # Check for folders created by faster-whisper/huggingface-hub
        for item in models_path.iterdir():
            if not item.is_dir():
                continue
            
            name = item.name
            # Faster-whisper uses folders like models--Systran--faster-whisper-tiny
            if name.startswith("models--Systran--faster-whisper-"):
                model_id = name.replace("models--Systran--faster-whisper-", "")
                downloaded.append(model_id)
            elif name.startswith("models--Systran--faster-distil-whisper-"):
                model_id = name.replace("models--Systran--faster-distil-whisper-", "distil-")
                downloaded.append(model_id)
            # Support folders like 'tiny', 'base' if they were manually downloaded or use old structure
            elif any(m in name for m in ["tiny", "base", "small", "medium", "large", "distil"]):
                # Ensure it's a valid faster-whisper model folder
                if (item / "model.bin").exists() and (item / "config.json").exists():
                    downloaded.append(name)
                    
        return list(set(downloaded))

    def start_recording(self):
        if self.is_recording: return
        # Small delay to ensure focus has settled if user just clicked/switched
        time.sleep(0.05)
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
                self.output_manager._release_modifiers()

                def on_segment(partial):
                    """Update UI with partial text — but don't type anything yet."""
                    self.partial_text = partial
                    self._publish_status()

                text = self.transcriber.transcribe(audio, on_segment=on_segment)
                processed = self.text_processor.process(text)

                LOGGER.info("Transcription result: '%s'", processed.text)

                if processed.text:
                    if processed.is_correction and self.last_typed_text:
                        self.output_manager.replace_previous_and_type(
                            self.last_typed_text, processed.text,
                        )
                    else:
                        self.output_manager.type_text(processed.text)
                    self.last_typed_text = processed.text
            except Exception as e:
                LOGGER.exception("Error during audio processing: %s", e)
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
            self.transcriber.update_settings(merged["transcription"])
        else:
            self.transcriber.update_settings(merged["transcription"])
            if self.transcriber.load_step == "error":
                self.model_loading_error = self.transcriber.load_error
            else:
                self.model_loading_error = None


