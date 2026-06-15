"""Text embedding engines for semantic search.

Two real backends behind one protocol, plus a pluggable default so tests can
swap a fake:

* TransformersEngine — `transformers` + torch with mean pooling. Preferred,
  because it avoids `sentence-transformers`'s newer top-level `torchcodec`
  import, which fails to load on many Windows installs (FFmpeg DLL mismatch).
* SentenceTransformerEngine — used only if `transformers` isn't importable.

If neither is available the app still runs: semantic search stays off and
search falls back to exact + fuzzy. Resolution only does `find_spec` (cheap,
import-safe); the heavy model is loaded lazily on first embed().
"""
from __future__ import annotations

from typing import Protocol

DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
HF_MODEL = f"sentence-transformers/{DEFAULT_MODEL}"


class EmbeddingEngine(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text."""


class TransformersEngine:
    """MiniLM via `transformers` + torch, mean-pooled & L2-normalized."""

    def __init__(self, model_name: str = HF_MODEL):
        self.model_name = model_name
        self.name = f"hf:{DEFAULT_MODEL}"
        self.dim = 384
        self._tok = None
        self._model = None

    def _load(self):
        if self._model is None:
            from transformers import AutoModel, AutoTokenizer
            self._tok = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModel.from_pretrained(self.model_name)
            self._model.eval()
            self.dim = int(self._model.config.hidden_size)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        import torch
        self._load()
        enc = self._tok(texts, padding=True, truncation=True, max_length=256,
                        return_tensors="pt")
        with torch.no_grad():
            out = self._model(**enc)
        mask = enc["attention_mask"].unsqueeze(-1).float()
        summed = (out.last_hidden_state * mask).sum(dim=1)
        counts = mask.sum(dim=1).clamp(min=1e-9)
        emb = torch.nn.functional.normalize(summed / counts, p=2, dim=1)
        return emb.cpu().tolist()


class SentenceTransformerEngine:
    """sentence-transformers fallback (multilingual MiniLM, 384-dim)."""

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


def _resolve() -> EmbeddingEngine | None:
    import importlib.util as u
    try:
        if u.find_spec("torch") and u.find_spec("transformers"):
            return TransformersEngine()
        if u.find_spec("sentence_transformers"):
            return SentenceTransformerEngine()
    except Exception:
        return None
    return None


def get_embedding_engine() -> EmbeddingEngine | None:
    """The active engine, or None when no embedding backend is available."""
    global _default_engine, _resolved
    if _resolved:
        return _default_engine
    _resolved = True
    _default_engine = _resolve()
    return _default_engine


def set_embedding_engine(engine: EmbeddingEngine | None):
    """Override for tests / alternate backends."""
    global _default_engine, _resolved
    _default_engine = engine
    _resolved = True


def available() -> bool:
    return get_embedding_engine() is not None
