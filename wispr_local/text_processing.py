import logging
from dataclasses import dataclass

LOGGER = logging.getLogger(__name__)

@dataclass
class ProcessedText:
    text: str
    is_correction: bool

class TextProcessor:
    def __init__(self, settings):
        self.settings = settings
        self.correction_prefixes = ["No,", "I mean,", "Wait,", "Actually,"]

    def process(self, text: str) -> ProcessedText:
        if not text:
            return ProcessedText("", False)

        is_correction = False
        for prefix in self.correction_prefixes:
            if text.startswith(prefix):
                is_correction = True
                text = text[len(prefix):].strip()
                break

        return ProcessedText(text, is_correction)

    def update_settings(self, settings):
        self.settings = settings
