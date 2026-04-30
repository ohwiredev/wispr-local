import ctypes
from ctypes import wintypes
import sys
import time
import logging
import pyperclip

LOGGER = logging.getLogger(__name__)

# --- Win32 Definitions ---
user32 = ctypes.windll.user32

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_CONTROL = 0x11
VK_V = 0x56


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_size_t)),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", INPUT_UNION)]


def _send_input(inputs):
    n = len(inputs)
    input_array = (INPUT * n)(*inputs)
    sent = user32.SendInput(n, ctypes.byref(input_array), ctypes.sizeof(INPUT))
    if sent != n:
        LOGGER.warning("SendInput: requested %d, sent %d", n, sent)


def _make_key_input(vk, flags=0):
    scan = user32.MapVirtualKeyW(vk, 0) if sys.platform == "win32" else 0
    ki = KEYBDINPUT(vk, scan, flags, 0, None)
    return INPUT(INPUT_KEYBOARD, INPUT_UNION(ki=ki))


def _make_unicode_input(char, flags=0):
    ki = KEYBDINPUT(0, ord(char), flags | KEYEVENTF_UNICODE, 0, None)
    return INPUT(INPUT_KEYBOARD, INPUT_UNION(ki=ki))


def _get_foreground_window() -> int:
    """Return the handle of the current foreground window."""
    if sys.platform == "win32":
        return user32.GetForegroundWindow()
    return 0


def _get_window_info(hwnd: int) -> tuple[str, int]:
    """Return the title and PID of the window."""
    if sys.platform == "win32" and hwnd:
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return buf.value, pid.value
    return "", 0


class TextOutputManager:
    def __init__(self, settings):
        self.settings = settings
        self._target_hwnd: int = 0
        self._target_title: str = ""
        self._target_pid: int = 0

    @property
    def _use_paste(self) -> bool:
        return self.settings.get("method", "type") == "paste"

    # ── Window tracking ──────────────────────────────────────────────

    def save_target_window(self):
        """Snapshot the currently focused window info."""
        self._target_hwnd = _get_foreground_window()
        self._target_title, self._target_pid = _get_window_info(self._target_hwnd)
        LOGGER.info("Target window saved: '%s' (PID %s, HWND %s)",
                     self._target_title, self._target_pid, self._target_hwnd)

    def _is_target_window_focused(self) -> bool:
        if self._target_hwnd == 0:
            return True
        curr_hwnd = _get_foreground_window()
        if curr_hwnd == self._target_hwnd:
            return True
        # Robust check via PID (title can change dynamically)
        _, curr_pid = _get_window_info(curr_hwnd)
        if curr_pid == self._target_pid:
            return True
        return False

    # ── Modifier release ─────────────────────────────────────────────

    def _release_modifiers(self):
        """Release all modifier keys to prevent stuck-key issues."""
        vks = [
            0x11, 0xA2, 0xA3,  # VK_CONTROL, VK_LCONTROL, VK_RCONTROL
            0x10, 0xA0, 0xA1,  # VK_SHIFT, VK_LSHIFT, VK_RSHIFT
            0x12, 0xA4, 0xA5,  # VK_MENU, VK_LMENU, VK_RMENU
            0x5B, 0x5C         # LWin, RWin
        ]
        inputs = [_make_key_input(vk, KEYEVENTF_KEYUP) for vk in vks]
        _send_input(inputs)
        time.sleep(0.05)

    # ── Low-level output primitives ──────────────────────────────────

    def _type_unicode(self, text: str):
        """Type text character-by-character using Unicode injection."""
        inputs = []
        for char in text:
            inputs.append(_make_unicode_input(char))
            inputs.append(_make_unicode_input(char, KEYEVENTF_KEYUP))
        _send_input(inputs)

    def _paste_from_clipboard(self):
        """Simulate Ctrl+V using low-level Win32 input."""
        _send_input([_make_key_input(VK_CONTROL)])
        time.sleep(0.05)
        _send_input([_make_key_input(VK_V)])
        time.sleep(0.05)
        _send_input([_make_key_input(VK_V, KEYEVENTF_KEYUP)])
        time.sleep(0.05)
        _send_input([_make_key_input(VK_CONTROL, KEYEVENTF_KEYUP)])

    # ── Public API ───────────────────────────────────────────────────

    def type_text(self, text: str):
        """Output text to the target window.  Falls back to clipboard if
        the target window has lost focus."""
        self._release_modifiers()

        if not self._is_target_window_focused():
            LOGGER.warning("Target window lost focus — copying to clipboard instead")
            pyperclip.copy(text)
            return

        if self._use_paste:
            pyperclip.copy(text)
            time.sleep(0.1)
            self._paste_from_clipboard()
        else:
            self._type_unicode(text)

        # Always keep a copy in the clipboard as safety net
        try:
            pyperclip.copy(text)
        except Exception:
            pass

    def stream_insert(self, text: str):
        """Type text incrementally during live streaming.
        Caller must verify focus before calling."""
        if not text:
            return
        self._type_unicode(text)

    def replace_previous_and_type(self, previous_text: str, new_text: str):
        """Select the previous text and replace it with new text."""
        self._release_modifiers()

        if not self._is_target_window_focused():
            LOGGER.warning("Target window lost focus — copying to clipboard instead")
            pyperclip.copy(new_text)
            return

        # Select previous text with Shift+Left
        VK_SHIFT = 0x10
        VK_LEFT = 0x25
        inputs = [_make_key_input(VK_SHIFT)]
        for _ in range(len(previous_text)):
            inputs.append(_make_key_input(VK_LEFT))
            inputs.append(_make_key_input(VK_LEFT, KEYEVENTF_KEYUP))
        inputs.append(_make_key_input(VK_SHIFT, KEYEVENTF_KEYUP))
        _send_input(inputs)
        time.sleep(0.05)

        # Type replacement
        if self._use_paste:
            pyperclip.copy(new_text)
            time.sleep(0.1)
            self._paste_from_clipboard()
        else:
            self._type_unicode(new_text)

    def update_settings(self, settings):
        self.settings = settings
