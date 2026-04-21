import pyperclip
from pynput.keyboard import Controller, Key
import time
import logging

LOGGER = logging.getLogger(__name__)

class TextOutputManager:
    def __init__(self, settings):
        self.settings = settings
        self.keyboard = Controller()

    def copy_to_clipboard(self, text: str):
        pyperclip.copy(text)

    def type_text(self, text: str):
        self.keyboard.type(text)

    def replace_previous_and_type(self, previous_text: str, new_text: str):
        # Delete previous text by backspacing
        # This is a bit naive but standard for this type of app
        for _ in range(len(previous_text)):
            self.keyboard.press(Key.backspace)
            self.keyboard.release(Key.backspace)
        
        self.keyboard.type(new_text)

    def update_settings(self, settings):
        self.settings = settings
