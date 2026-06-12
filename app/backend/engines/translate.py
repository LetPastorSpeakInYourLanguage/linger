"""Translation engines."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TranslationResult:
    text: str
    source_language: str | None = None
    target_language: str = ""


class TranslateEngine(Protocol):
    name: str

    def translate(self, text: str, target_language: str,
                  source_language: str = "auto") -> TranslationResult:
        """Translate one text block."""

    def translate_many(self, texts: list[str], target_language: str,
                       source_language: str = "auto") -> list[TranslationResult]:
        """Translate multiple blocks while preserving order."""


class GoogleTranslateEngine:
    """Keyless Google Translate via deep-translator."""

    name = "google"

    def translate(self, text: str, target_language: str,
                  source_language: str = "auto") -> TranslationResult:
        try:
            from deep_translator import GoogleTranslator
        except ImportError as e:
            raise RuntimeError(
                "deep-translator is not installed. Run: pip install deep-translator") from e
        translated = GoogleTranslator(source=source_language,
                                      target=target_language).translate(text)
        return TranslationResult(text=translated or "", source_language=source_language,
                                 target_language=target_language)

    def translate_many(self, texts: list[str], target_language: str,
                       source_language: str = "auto") -> list[TranslationResult]:
        return [self.translate(t, target_language, source_language) for t in texts]


_default_engine: TranslateEngine | None = None


def get_translate_engine() -> TranslateEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = GoogleTranslateEngine()
    return _default_engine


def set_translate_engine(engine: TranslateEngine | None):
    global _default_engine
    _default_engine = engine
