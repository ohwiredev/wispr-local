import logging
from dataclasses import dataclass

from .correction_resolver import (
    CorrectionResolver,
    CorrectionResult,
    has_correction_markers,
    resolve_rule_based,
)

LOGGER = logging.getLogger(__name__)


@dataclass
class ProcessedText:
    text: str
    is_correction: bool


class TextProcessor:
    def __init__(self, settings, correction_resolver: CorrectionResolver | None = None):
        self.settings = settings
        self.correction_resolver = correction_resolver

    def process(self, text: str) -> ProcessedText:
        if not text:
            return ProcessedText("", False)

        if self.correction_resolver:
            result: CorrectionResult = self.correction_resolver.resolve(text)
            return ProcessedText(result.text, result.is_correction)

        return self._rule_fallback(text)

    def _rule_fallback(self, text: str) -> ProcessedText:
        """Lightweight fallback when the CorrectionResolver is not available."""
        if not has_correction_markers(text):
            return ProcessedText(text, False)
        corrected = resolve_rule_based(text)
        is_correction = corrected != text
        return ProcessedText(corrected, is_correction)

    def update_settings(self, settings):
        self.settings = settings
