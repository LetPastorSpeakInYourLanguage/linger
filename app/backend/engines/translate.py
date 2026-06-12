"""Translation engines."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
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
    """Keyless Google Translate with provider fallbacks.

    The preferred package is deep-translator, but development installs often
    only have the core backend dependencies. Keep a small urllib fallback so
    auto subtitle/cut translation fails only when every provider is unavailable.
    """

    name = "google"
    _max_batch_chars = 4200

    def translate(self, text: str, target_language: str,
                  source_language: str = "auto") -> TranslationResult:
        translated = self._translate_text(text, target_language, source_language)
        return TranslationResult(text=translated or "", source_language=source_language,
                                 target_language=target_language)

    def translate_many(self, texts: list[str], target_language: str,
                       source_language: str = "auto") -> list[TranslationResult]:
        out: list[TranslationResult | None] = [None] * len(texts)
        batch: list[tuple[int, str]] = []
        batch_chars = 0

        def flush():
            nonlocal batch, batch_chars
            if not batch:
                return
            raw = "\n".join(t for _, t in batch)
            translated = self.translate(raw, target_language, source_language).text
            lines = translated.splitlines()
            if len(lines) != len(batch):
                lines = [
                    self.translate(t, target_language, source_language).text
                    for _, t in batch
                ]
            for (idx, _), line in zip(batch, lines):
                out[idx] = TranslationResult(text=line or "",
                                             source_language=source_language,
                                             target_language=target_language)
            batch = []
            batch_chars = 0

        for idx, text in enumerate(texts):
            clean = (text or "").strip()
            if not clean:
                out[idx] = TranslationResult(text="", source_language=source_language,
                                             target_language=target_language)
                continue
            next_chars = len(clean) + (1 if batch else 0)
            if batch and batch_chars + next_chars > self._max_batch_chars:
                flush()
            batch.append((idx, clean))
            batch_chars += next_chars
        flush()
        return [r or TranslationResult(text="", source_language=source_language,
                                       target_language=target_language)
                for r in out]

    def _translate_text(self, text: str, target_language: str,
                        source_language: str) -> str:
        if not (text or "").strip():
            return ""
        errors: list[str] = []

        try:
            from deep_translator import GoogleTranslator
            translated = GoogleTranslator(source=source_language,
                                          target=target_language).translate(text)
            if translated is not None:
                return translated
        except ImportError as e:
            errors.append(f"deep-translator missing: {e}")
        except Exception as e:
            errors.append(f"deep-translator failed: {e}")

        try:
            from mtranslate import translate as mtranslate
            translated = mtranslate(text, target_language, source_language)
            if translated is not None:
                return translated
        except ImportError as e:
            errors.append(f"mtranslate missing: {e}")
        except Exception as e:
            errors.append(f"mtranslate failed: {e}")

        try:
            return self._translate_gtx(text, target_language, source_language)
        except Exception as e:
            errors.append(f"google gtx failed: {e}")

        raise RuntimeError(
            "translation failed. Install deep-translator or mtranslate, or check "
            f"network access. Details: {'; '.join(errors)}")

    def _translate_gtx(self, text: str, target_language: str,
                       source_language: str) -> str:
        params = urllib.parse.urlencode({
            "client": "gtx",
            "sl": source_language or "auto",
            "tl": target_language,
            "dt": "t",
        })
        body = urllib.parse.urlencode({"q": text}).encode("utf-8")
        req = urllib.request.Request(
            f"https://translate.googleapis.com/translate_a/single?{params}",
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "User-Agent": "Mozilla/5.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as res:
            data = json.loads(res.read().decode("utf-8"))
        chunks = data[0] if data else []
        return "".join((chunk[0] or "") for chunk in chunks if chunk)


_default_engine: TranslateEngine | None = None


def get_translate_engine() -> TranslateEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = GoogleTranslateEngine()
    return _default_engine


def set_translate_engine(engine: TranslateEngine | None):
    global _default_engine
    _default_engine = engine
