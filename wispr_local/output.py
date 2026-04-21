import ctypes
import sys
import time
import logging

import pyperclip
from pynput.keyboard import Controller, Key

LOGGER = logging.getLogger(__name__)

_MODIFIER_KEYS = [
    Key.ctrl_l, Key.ctrl_r,
    Key.alt_l, Key.alt_r,
    Key.shift_l, Key.shift_r,
    Key.cmd,
]


def _get_foreground_window() -> int:
    """Return the handle of the current foreground window (Windows only)."""
    if sys.platform == "win32":
        return ctypes.windll.user32.GetForegroundWindow()
    return 0


class TextOutputManager:
    def __init__(self, settings):
        self.settings = settings
        self.keyboard = Controller()
        self._target_hwnd: int = 0

    @property
    def _use_paste(self) -> bool:
        return self.settings.get("method", "type") == "paste"

    def save_target_window(self):
        """Snapshot the currently focused window so we can verify it later."""
        self._target_hwnd = _get_foreground_window()

    def _is_target_window_focused(self) -> bool:
        if self._target_hwnd == 0:
            return True
        return _get_foreground_window() == self._target_hwnd

    def _release_modifiers(self):
        """Release all modifier keys to prevent shortcut interference."""
        for mod in _MODIFIER_KEYS:
            try:
                self.keyboard.release(mod)
            except Exception:
                pass
        time.sleep(0.02)

    def _paste_from_clipboard(self):
        """Simulate Ctrl+V to paste clipboard contents."""
        self.keyboard.press(Key.ctrl_l)
        self.keyboard.press('v')
        self.keyboard.release('v')
        self.keyboard.release(Key.ctrl_l)

    def copy_to_clipboard(self, text: str):
        pyperclip.copy(text)

    def type_text(self, text: str):
        self._release_modifiers()
        if not self._is_target_window_focused():
            LOGGER.warning(
                "Focus changed since recording started — "
                "skipping auto-type (text is on clipboard, paste with Ctrl+V)"
            )
            return
        self._insert(text)

    def _insert(self, text: str):
        """Insert text at the cursor without any modifier/focus checks."""
        if self._use_paste:
            pyperclip.copy(text)
            self._paste_from_clipboard()
        else:
            self.keyboard.type(text)

    def stream_insert(self, text: str):
        """Type a delta chunk during streaming — skips modifier release."""
        self._insert(text)

    def _select_previous_text(self, length: int):
        """Select *length* characters to the left using Shift+Left word jumps."""
        if length <= 0:
            return
        # Use Ctrl+Shift+Left to select word-by-word (much faster than per-char)
        # Estimate: average word ~5 chars. Over-select, then we replace anyway.
        word_jumps = max(1, (length + 4) // 5)
        for _ in range(word_jumps):
            self.keyboard.press(Key.ctrl_l)
            self.keyboard.press(Key.shift_l)
            self.keyboard.press(Key.left)
            self.keyboard.release(Key.left)
            self.keyboard.release(Key.shift_l)
            self.keyboard.release(Key.ctrl_l)

    def replace_previous_and_type(self, previous_text: str, new_text: str):
        self._release_modifiers()
        if not self._is_target_window_focused():
            LOGGER.warning(
                "Focus changed since recording started — "
                "skipping auto-type (text is on clipboard, paste with Ctrl+V)"
            )
            return

        self._select_previous_text(len(previous_text))

        if self._use_paste:
            pyperclip.copy(new_text)
            self._paste_from_clipboard()
        else:
            self.keyboard.type(new_text)

    def update_settings(self, settings):
        self.settings = settings
