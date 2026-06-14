"""Deterministic engine fakes for tests and offline development."""
from __future__ import annotations

import shutil
import wave
from pathlib import Path

from .separation import SeparationResult
from .translate import TranslationResult
from .tts import TTSResult, WordBoundary


class FakeSeparationEngine:
    name = "fake"

    def separate_vocals(self, input_audio: Path, out_dir: Path,
                        check_cancel=None) -> SeparationResult:
        if check_cancel:
            check_cancel()
        out_dir.mkdir(parents=True, exist_ok=True)
        vocals = out_dir / "vocals.wav"
        accompaniment = out_dir / "accompaniment.wav"
        shutil.copy2(input_audio, vocals)
        shutil.copy2(input_audio, accompaniment)
        return SeparationResult(vocals=vocals, accompaniment=accompaniment)


class FakeTTSEngine:
    name = "fake"

    def synthesize(self, text: str, voice: str, out_path: Path,
                   *, rate: str = "+0%", volume: str = "+0%") -> TTSResult:
        del voice, rate, volume
        out_path.parent.mkdir(parents=True, exist_ok=True)
        words = [w for w in text.split() if w]
        duration_s = max(0.2, len(words) * 0.12)
        sample_rate = 16000
        frames = int(duration_s * sample_rate)
        with wave.open(str(out_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(b"\x00\x00" * frames)
        boundaries = [
            WordBoundary(text=w, offset_ms=i * 120, duration_ms=100)
            for i, w in enumerate(words)
        ]
        return TTSResult(audio_path=out_path, word_boundaries=boundaries)


class FakeEmbeddingEngine:
    """Deterministic bag-of-words hashing embedding: shared words → similar
    vectors, so semantic-search ranking is meaningful in tests without a model."""

    name = "fake-embed"
    dim = 64

    def embed(self, texts: list[str]) -> list[list[float]]:
        import math
        import re
        import zlib
        out = []
        for t in texts:
            vec = [0.0] * self.dim
            for w in re.findall(r"\w+", (t or "").lower()):
                vec[zlib.crc32(w.encode()) % self.dim] += 1.0  # stable across processes
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class FakeTranslateEngine:
    name = "fake"

    def translate(self, text: str, target_language: str,
                  source_language: str = "auto") -> TranslationResult:
        return TranslationResult(text=f"[{target_language}] {text}",
                                 source_language=source_language,
                                 target_language=target_language)

    def translate_many(self, texts: list[str], target_language: str,
                       source_language: str = "auto") -> list[TranslationResult]:
        return [self.translate(t, target_language, source_language) for t in texts]
