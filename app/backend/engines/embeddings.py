"""Text embedding engines for semantic search.

A small protocol with a real `sentence-transformers` implementation (lazy, the
multilingual MiniLM model) and a pluggable default so tests can swap a fake.
If the package isn't installed the app still runs — semantic search simply
stays unavailable and search falls back to exact + fuzzy.
"""
from __future__ import annotations

from typing import Protocol

DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


class EmbeddingEngine(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text."""


class SentenceTransformerEngine:
    """sentence-transformers MiniLM — multilingual, 384-dim, runs on CPU."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name
        self.name = f"st:{model_name}"
        self._model = None
        self._dim = 384

    @property
    def dim(self) -> int:
        return self._dim

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            self._dim = self._model.get_sentence_embedding_dimension()
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        vecs = model.encode(texts, normalize_embeddings=True,
                            convert_to_numpy=True, show_progress_bar=False)
        return [v.tolist() for v in vecs]


_default_engine: EmbeddingEngine | None = None
_resolved = False


def get_embedding_engine() -> EmbeddingEngine | None:
    """The active engine, or None when no embedding backend is available."""
    global _default_engine, _resolved
    if _resolved:
        return _default_engine
    _resolved = True
    import importlib.util
    if importlib.util.find_spec("sentence_transformers") is not None:
        _default_engine = SentenceTransformerEngine()
    return _default_engine


def set_embedding_engine(engine: EmbeddingEngine | None):
    """Override for tests / alternate backends."""
    global _default_engine, _resolved
    _default_engine = engine
    _resolved = True


def available() -> bool:
    return get_embedding_engine() is not None
