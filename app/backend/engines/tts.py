"""Text-to-speech engines.

EdgeTTS uses the edge-tts package, which streams audio plus WordBoundary
events. Word boundaries are retained now because P2 dubbing will use them for
better segment alignment.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class WordBoundary:
    text: str
    offset_ms: int
    duration_ms: int


@dataclass(frozen=True)
class TTSResult:
    audio_path: Path
    word_boundaries: list[WordBoundary]


class TTSEngine(Protocol):
    name: str

    def synthesize(self, text: str, voice: str, out_path: Path,
                   *, rate: str = "+0%", volume: str = "+0%") -> TTSResult:
        """Generate speech into out_path and return captured word timings."""


class EdgeTTSEngine:
    name = "edge"

    def synthesize(self, text: str, voice: str, out_path: Path,
                   *, rate: str = "+0%", volume: str = "+0%") -> TTSResult:
        return asyncio.run(
            self._synthesize_async(text, voice, out_path, rate=rate, volume=volume))

    async def _synthesize_async(self, text: str, voice: str, out_path: Path,
                                *, rate: str, volume: str) -> TTSResult:
        try:
            import edge_tts
        except ImportError as e:
            raise RuntimeError("edge-tts is not installed. Run: pip install edge-tts") from e

        out_path.parent.mkdir(parents=True, exist_ok=True)
        communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
        boundaries: list[WordBoundary] = []
        with out_path.open("wb") as f:
            async for chunk in communicate.stream():
                kind = chunk.get("type")
                if kind == "audio":
                    f.write(chunk["data"])
                elif kind == "WordBoundary":
                    boundaries.append(WordBoundary(
                        text=chunk.get("text", ""),
                        offset_ms=round((chunk.get("offset", 0) or 0) / 10_000),
                        duration_ms=round((chunk.get("duration", 0) or 0) / 10_000),
                    ))
        return TTSResult(audio_path=out_path, word_boundaries=boundaries)


_default_engine: TTSEngine | None = None


def get_tts_engine() -> TTSEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = EdgeTTSEngine()
    return _default_engine


def set_tts_engine(engine: TTSEngine | None):
    global _default_engine
    _default_engine = engine
