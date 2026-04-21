import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path

from huggingface_hub import hf_hub_download

LOGGER = logging.getLogger(__name__)

# ── Correction markers ────────────────────────────────────────────────
# Phrases that signal the speaker is correcting themselves.
_MARKERS = [
    "I mean", "I meant", "actually", "no wait", "wait no", "no no",
    "no actually", "no sorry", "no rather",
    "sorry", "rather", "scratch that", "or rather", "well actually",
    "let me rephrase", "correction", "not that", "instead",
]
_MARKERS_SORTED = sorted(_MARKERS, key=len, reverse=True)
_MARKER_ALT = "|".join(re.escape(m) for m in _MARKERS_SORTED)

# Internal correction: marker preceded by comma/semicolon (avoids false
# positives like "I actually think …" where "actually" is an adverb).
_CORRECTION_RE = re.compile(
    r"[,;]\s*\b(?:" + _MARKER_ALT + r")\b[,;]?\s*",
    re.IGNORECASE,
)

# Start-of-utterance correction (e.g. "I mean, email Andrew" as a second
# recording that corrects the previous one).
_START_MARKER_RE = re.compile(
    r"^\s*\b(?:" + _MARKER_ALT + r")\b\s*[,;]?\s*",
    re.IGNORECASE,
)

# Quick presence check — no punctuation requirement.
_HAS_MARKER_RE = re.compile(
    r"\b(?:" + _MARKER_ALT + r")\b", re.IGNORECASE
)

SYSTEM_PROMPT = """\
You are a dictation cleanup assistant. The user's speech has already been partially \
cleaned by a rule engine. Your job is to do a final pass: fix any remaining \
self-corrections, remove filler like "instead" at the end, and make sure the \
sentence reads naturally.

Examples:
- "Send it to David instead." -> "Send it to David."
- "Email Ryan." -> "Email Ryan."
- "Book a flight to London. Next Saturday for Paris." -> "Book a flight to Paris for next Saturday."
- "Set the meeting for Thursday at 3pm." -> "Set the meeting for Thursday at 3pm."
- "The project is due on Mon, I mean Friday." -> "The project is due on Friday."
- "I need to buy milk and eggs." -> "I need to buy milk and eggs."

Rules:
- Return ONLY the corrected text, no explanation
- Preserve punctuation
- If the text is already clean, return it unchanged
- Remove trailing "instead" when the sentence is a replacement for something else
- Fix garbled or reordered phrases so the sentence reads naturally"""

DEFAULT_REPO = "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
DEFAULT_FILENAME = "qwen2.5-0.5b-instruct-q4_k_m.gguf"


@dataclass
class CorrectionResult:
    text: str
    is_correction: bool


def has_correction_markers(text: str) -> bool:
    """Fast check for presence of any correction signal phrase."""
    return bool(_HAS_MARKER_RE.search(text))


def _find_entity_start(clause_words, correction_first_word, is_first_clause):
    """Locate where the entity being corrected begins in the clause.

    Scans the clause backwards looking for a word that matches the
    "type" of the correction's leading word (both numeric, or both
    capitalised proper-noun-like).  Falls back to the last word.
    """
    if not clause_words or not correction_first_word:
        return None

    corr_is_digit = correction_first_word[0].isdigit()
    corr_is_upper = correction_first_word[0].isupper()

    for i in range(len(clause_words) - 1, -1, -1):
        word = clause_words[i]
        if not word:
            continue
        if is_first_clause and i == 0:
            continue
        if corr_is_digit and word[0].isdigit():
            return i
        if corr_is_upper and word[0].isupper():
            return i

    return len(clause_words) - 1


def resolve_rule_based(text: str) -> str:
    """Resolve speech self-corrections using pattern matching.

    Processes correction markers right-to-left.  For each marker it tries
    two strategies in order:

    1. **Anchor match** – if the first word of the correction phrase also
       appears earlier in the sentence, replace from that earlier
       occurrence onward (handles "email Brian, I mean email Andrew").
    2. **Word-count swap** – otherwise replace the last *N* words of the
       preceding clause, where *N* = number of words in the correction
       (handles "due on Monday, I mean Friday").
    """
    # Strip a leading correction marker (whole utterance is a correction
    # of a previous one, e.g. "I mean, email Andrew").
    m = _START_MARKER_RE.match(text)
    if m:
        text = text[m.end():]

    for _ in range(10):
        matches = list(_CORRECTION_RE.finditer(text))
        if not matches:
            break

        match = matches[-1]
        before = text[: match.start()]
        after = text[match.end() :]

        if not after.strip():
            text = before.rstrip(" ,;")
            continue

        after_stripped = after.lstrip()
        after_words = after_stripped.split()
        first_word = re.sub(r"[.,!?;:]+$", "", after_words[0])

        if not first_word:
            text = before + after
            continue

        # Strategy 1: find the same leading word earlier in *before*
        word_re = re.compile(r"\b" + re.escape(first_word) + r"\b", re.IGNORECASE)
        hits = list(word_re.finditer(before))

        if hits:
            pos = hits[-1].start()
            text = before[:pos] + after_stripped
            continue

        # Strategy 2: find the entity being corrected by type-matching
        # the correction's first word against clause words.
        before_clean = before.rstrip(" ,;")
        boundary = max(
            before_clean.rfind(","),
            before_clean.rfind("."),
            before_clean.rfind(";"),
        )

        if boundary >= 0:
            clause = before_clean[boundary + 1 :].strip()
            prefix = before_clean[: boundary + 1] + " "
        else:
            clause = before_clean
            prefix = ""

        clause_words = clause.split()
        entity_start = _find_entity_start(
            clause_words, first_word, is_first_clause=(boundary < 0)
        )

        if entity_start is not None:
            kept = " ".join(clause_words[:entity_start])
            if kept:
                text = prefix + kept + " " + after_stripped
            else:
                text = (prefix.rstrip() + " " + after_stripped).lstrip()
        else:
            text = (prefix.rstrip() + " " + after_stripped).lstrip()

    # Strip trailing "instead" — signals correction of a previous utterance
    text = re.sub(r"\s+instead\s*[.!?]?\s*$", ".", text, flags=re.IGNORECASE)

    text = re.sub(r" {2,}", " ", text).strip()

    if text and text[0].islower():
        text = text[0].upper() + text[1:]

    return text


class CorrectionResolver:
    def __init__(self, settings: dict):
        self.enabled: bool = settings.get("enabled", True)
        self.repo_id: str = settings.get("repo_id", DEFAULT_REPO)
        self.model_filename: str = settings.get("model_filename", DEFAULT_FILENAME)
        self.models_dir = Path("models")

        self._llm = None
        self._lock = threading.Lock()

        if self.enabled:
            self._load_model()

    def _load_model(self):
        from llama_cpp import Llama

        with self._lock:
            try:
                LOGGER.info(
                    "Downloading/verifying correction model %s", self.model_filename
                )
                model_path = hf_hub_download(
                    repo_id=self.repo_id,
                    filename=self.model_filename,
                    local_dir=str(self.models_dir / "correction"),
                )
                LOGGER.info("Loading correction model from %s", model_path)
                self._llm = Llama(
                    model_path=model_path,
                    n_ctx=512,
                    n_threads=4,
                    verbose=False,
                )
                LOGGER.info("Correction model loaded successfully")
            except Exception:
                LOGGER.exception("Failed to load correction model")
                self._llm = None

    def resolve(self, raw_text: str) -> CorrectionResult:
        if not raw_text:
            return CorrectionResult(raw_text, False)

        # Stage 1 — instant rule-based pre-processing
        stage1 = resolve_rule_based(raw_text)

        # Stage 2 — LLM refinement on the (possibly cleaned) text
        if self.enabled and self._llm is not None:
            try:
                stage2 = self._generate(stage1).strip()
                if stage2:
                    is_correction = stage2 != raw_text
                    if is_correction:
                        LOGGER.info(
                            "Pipeline: %r -> [rules] %r -> [LLM] %r",
                            raw_text, stage1, stage2,
                        )
                    return CorrectionResult(stage2, is_correction)
            except Exception:
                LOGGER.warning("LLM stage failed, using rule output", exc_info=True)

        # LLM unavailable — use rule-based result directly
        is_correction = stage1 != raw_text
        if is_correction:
            LOGGER.info("Rule-only correction: %r -> %r", raw_text, stage1)
        return CorrectionResult(stage1, is_correction)

    def _generate(self, text: str) -> str:
        result = self._llm.create_chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            max_tokens=len(text.split()) * 3,
            temperature=0,
        )
        return result["choices"][0]["message"]["content"]

    def update_settings(self, settings: dict):
        old_repo = self.repo_id
        old_filename = self.model_filename
        was_enabled = self.enabled

        self.enabled = settings.get("enabled", True)
        self.repo_id = settings.get("repo_id", DEFAULT_REPO)
        self.model_filename = settings.get("model_filename", DEFAULT_FILENAME)

        model_changed = old_repo != self.repo_id or old_filename != self.model_filename
        newly_enabled = self.enabled and not was_enabled

        if self.enabled and (model_changed or newly_enabled):
            self._load_model()
        elif not self.enabled:
            self._llm = None
