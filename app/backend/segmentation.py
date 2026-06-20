"""Algorithmic topic segmentation — turn a transcript into cuts without an LLM.

This is the core of the "AI" you actually want: deterministic, tunable, and
cheap to re-run. It ports the divisive binary-tree topic-segmentation idea
(TreeSeg / embedding-based TextTiling) onto Recomposer's data model, where a
``cut`` is just an ordered span of ``segments``.

How it works
------------
Every segment already has an embedding (``segment_embeddings``). To find the
"natural cuts" we recursively split a span at the boundary where the two sides
are *least* alike — comparing the centroid of a window of lines just before the
boundary against the window just after, and scoring the boundary ``1 - cosine``.
A split is accepted when its score clears an **adaptive threshold**
(``mean + std_weight*std`` of all candidate scores in the span, floored by
``min_split_score``), or when the span is simply too long. ``min_segments`` /
``min_duration_s`` keep cuts from getting trivially short; ``max_depth`` and
``max_segments`` bound the recursion.

Because every heavy computation (embedding each line) happens once and is cached
in the vector store, re-running with different hyperparameters is just float
math on vectors we already have — fast enough to drive live sliders. The same
``propose`` output feeds the preview UI and, after manual tweaks, the existing
confirm-first commit (:func:`backend.ai_ops.ai_cut_commit`).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from . import vectors
from .engines import embeddings


@dataclass(frozen=True)
class SegmentationConfig:
    """Tunable knobs for one segmentation pass. Durations are in seconds."""
    name: str = "balanced"
    min_segments: int = 6          # fewest lines on either side of a boundary
    max_segments: int = 60         # a span longer than this is force-split
    min_duration_s: float = 20.0   # a cut shorter than this can't be made
    window_size: int = 8           # lines averaged on each side of a boundary
    min_split_score: float = 0.16  # hard floor on an accepted boundary score
    adaptive_std_weight: float = 0.25  # threshold = mean + weight*std of scores
    max_depth: int = 6             # recursion bound (≤ 2**depth cuts per doc)

    def to_dict(self) -> dict:
        return asdict(self)


PRESETS: dict[str, SegmentationConfig] = {
    "coarse": SegmentationConfig(
        name="coarse", min_segments=10, max_segments=110, min_duration_s=45.0,
        window_size=12, min_split_score=0.22, adaptive_std_weight=0.35, max_depth=5),
    "balanced": SegmentationConfig(),
    "fine": SegmentationConfig(
        name="fine", min_segments=4, max_segments=40, min_duration_s=10.0,
        window_size=5, min_split_score=0.11, adaptive_std_weight=0.15, max_depth=8),
}

# Bounds the live-tuning sliders clamp to, surfaced to the UI via the preview
# response so the front end doesn't hard-code them.
PARAM_BOUNDS = {
    "min_segments": (1, 40),
    "max_segments": (5, 400),
    "min_duration_s": (1.0, 240.0),
    "window_size": (2, 30),
    "min_split_score": (0.0, 0.8),
    "adaptive_std_weight": (0.0, 1.5),
    "max_depth": (1, 12),
}


def config_from(preset: str | None = None, overrides: dict | None = None) -> SegmentationConfig:
    """Resolve a preset name plus optional per-knob overrides into a config.

    Unknown keys are ignored; known ones are coerced and clamped to PARAM_BOUNDS
    so a slider can never push the engine into a degenerate state."""
    base = PRESETS.get((preset or "balanced"), PRESETS["balanced"])
    if not overrides:
        return base
    values = base.to_dict()
    values["name"] = "custom"
    for key, (lo, hi) in PARAM_BOUNDS.items():
        if key not in overrides or overrides[key] is None:
            continue
        caster = float if isinstance(lo, float) else int
        try:
            val = caster(overrides[key])
        except (TypeError, ValueError):
            continue
        values[key] = min(hi, max(lo, val))
    return SegmentationConfig(**values)


# --------------------------------------------------------------------------- #
# embeddings
# --------------------------------------------------------------------------- #

def _normalize(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype="float32")
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def embeddings_for_track(db, track_id: int) -> tuple[list, np.ndarray]:
    """Ordered (segments, embedding matrix) for a track.

    Pulls cached vectors from the store and, for any line not yet embedded,
    embeds it on the fly and upserts it so later re-runs are instant. Raises if
    no embedding backend is installed (semantic cutting needs one)."""
    segs = db.execute(
        "SELECT id, media_id, idx, start_s, end_s, text FROM segments "
        "WHERE track_id=? ORDER BY idx", (track_id,)).fetchall()
    if not segs:
        raise RuntimeError("track has no segments")

    stored = vectors.fetch([s["id"] for s in segs])
    dim = next((len(v) for v in stored.values()), None)
    missing = [s for s in segs if s["id"] not in stored or len(stored[s["id"]]) != (dim or -1)]
    if missing:
        engine = embeddings.get_embedding_engine()
        if engine is None:
            raise RuntimeError(
                "no embedding engine — install transformers to enable topic cutting")
        vecs = engine.embed([s["text"] for s in missing])
        for s, v in zip(missing, vecs):
            vectors.upsert(s["id"], s["media_id"], s["text"], v, engine.name)
            stored[s["id"]] = np.asarray(v, dtype="float32")
        db.commit()

    matrix = _normalize(np.vstack([stored[s["id"]] for s in segs]))
    return list(segs), matrix


# --------------------------------------------------------------------------- #
# divisive segmentation
# --------------------------------------------------------------------------- #

def _centroid(vectors_slice: np.ndarray) -> np.ndarray:
    if len(vectors_slice) == 0:
        return np.zeros((vectors_slice.shape[1],), dtype="float32")
    return _normalize(np.mean(vectors_slice, axis=0))[0]


def _duration_s(segs, start: int, end: int) -> float:
    if end <= start:
        return 0.0
    return float(segs[end - 1]["end_s"]) - float(segs[start]["start_s"])


def _candidate_scores(matrix, segs, start, end, cfg) -> list[tuple[int, float]]:
    """For every legal boundary in [start, end), score how unlike the windows on
    either side are (``1 - cosine`` of their centroids)."""
    scores: list[tuple[int, float]] = []
    left_min = start + cfg.min_segments
    right_max = end - cfg.min_segments
    for boundary in range(left_min, right_max + 1):
        if (_duration_s(segs, start, boundary) < cfg.min_duration_s
                or _duration_s(segs, boundary, end) < cfg.min_duration_s):
            continue
        left = _centroid(matrix[max(start, boundary - cfg.window_size):boundary])
        right = _centroid(matrix[boundary:min(end, boundary + cfg.window_size)])
        scores.append((boundary, 1.0 - float(np.dot(left, right))))
    return scores


def _best_split(matrix, segs, start, end, cfg) -> tuple[int, float] | None:
    length = end - start
    if length < cfg.min_segments * 2:
        return None
    scores = _candidate_scores(matrix, segs, start, end, cfg)
    if not scores:
        if length > cfg.max_segments:
            return start + length // 2, 0.0
        return None
    values = np.array([s for _, s in scores], dtype="float32")
    boundary, best = max(scores, key=lambda it: it[1])
    cutoff = max(cfg.min_split_score, float(values.mean() + cfg.adaptive_std_weight * values.std()))
    if length > cfg.max_segments or best >= cutoff:
        return boundary, best
    return None


def _split(matrix, segs, start, end, cfg, depth, out: list[tuple[int, int, float]]):
    if end <= start:
        return
    split = None if depth >= cfg.max_depth else _best_split(matrix, segs, start, end, cfg)
    if split is None:
        out.append((start, end, 0.0))
        return
    boundary, score = split
    _split(matrix, segs, start, boundary, cfg, depth + 1, out)
    # the boundary score is recorded on the cut that ends at it
    out[-1] = (out[-1][0], out[-1][1], score)
    _split(matrix, segs, boundary, end, cfg, depth + 1, out)


def propose(db, media_id: int, track_id: int, cfg: SegmentationConfig) -> dict:
    """Run one segmentation pass and return a plan (no DB writes).

    The plan entries share the shape consumed by :func:`ai_ops.ai_cut_commit`
    (``from_idx``/``to_idx``/``title``/``tags``/``folder``) plus ``score`` (the
    boundary strength that ended the cut) and ``segment_ids``/timing for the
    preview. The caller may freely edit the ranges (expand/shrink into
    neighbours) before committing."""
    segs, matrix = embeddings_for_track(db, track_id)
    ranges: list[tuple[int, int, float]] = []
    _split(matrix, segs, 0, len(segs), cfg, 0, ranges)

    plan = []
    for i, (start, end, score) in enumerate(ranges, 1):
        sel = segs[start:end]
        text = " ".join((s["text"] or "").strip() for s in sel if (s["text"] or "").strip())
        plan.append({
            "from_idx": int(sel[0]["idx"]),
            "to_idx": int(sel[-1]["idx"]),
            "segment_ids": [int(s["id"]) for s in sel],
            "lines": len(sel),
            "start_s": float(sel[0]["start_s"]),
            "end_s": float(sel[-1]["end_s"]),
            "score": round(float(score), 4),
            "title": (" ".join((sel[0]["text"] or "").split()[:7]) or f"Cut {i}")[:80],
            "tags": [],
            "folder": "Topic cuts",
            "preview": text[:200],
        })
    return {
        "track_id": track_id,
        "params": cfg.to_dict(),
        "param_bounds": PARAM_BOUNDS,
        "presets": list(PRESETS),
        "plan": plan,
    }
