"""Segment vector store for semantic search.

A dependency-light store: embeddings live in a SQLite table as float32 BLOBs and
similarity is brute-forced with numpy. That is plenty for tens of thousands of
segments; a `sqlite-vec` ANN index can slot in behind the same interface later
without touching callers.
"""
from __future__ import annotations

import hashlib

import numpy as np

from .db import get_db


def text_hash(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


def _to_blob(vec) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def _from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def upsert(segment_id: int, media_id: int, text: str, vec, model: str):
    db = get_db()
    db.execute("""
        INSERT INTO segment_embeddings (segment_id, media_id, text_hash, dim, vec, model)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(segment_id) DO UPDATE SET
            media_id=excluded.media_id, text_hash=excluded.text_hash,
            dim=excluded.dim, vec=excluded.vec, model=excluded.model""",
        (segment_id, media_id, text_hash(text), len(vec), _to_blob(vec), model))


def current_hashes(media_id: int) -> dict[int, tuple[str, str]]:
    """segment_id → (text_hash, model) already stored for a media."""
    rows = get_db().execute(
        "SELECT segment_id, text_hash, model FROM segment_embeddings WHERE media_id=?",
        (media_id,)).fetchall()
    return {r["segment_id"]: (r["text_hash"], r["model"]) for r in rows}


def delete_segment(segment_id: int):
    get_db().execute("DELETE FROM segment_embeddings WHERE segment_id=?", (segment_id,))


def stats() -> dict:
    db = get_db()
    total = db.execute("SELECT COUNT(*) AS n FROM segments").fetchone()["n"]
    embedded = db.execute("SELECT COUNT(*) AS n FROM segment_embeddings").fetchone()["n"]
    return {"segments": total, "embedded": embedded}


def fetch(ids: list[int]) -> dict[int, np.ndarray]:
    if not ids:
        return {}
    qm = ",".join("?" * len(ids))
    rows = get_db().execute(
        f"SELECT segment_id, vec FROM segment_embeddings WHERE segment_id IN ({qm})",
        ids).fetchall()
    return {r["segment_id"]: _from_blob(r["vec"]) for r in rows}


def mean_vector(ids: list[int]):
    """L2-normalized mean of the stored vectors for `ids`, or None if none stored."""
    vs = list(fetch(ids).values())
    if not vs:
        return None
    m = np.mean(np.vstack(vs), axis=0)
    n = float(np.linalg.norm(m)) or 1.0
    return m / n


def cosine(a, b) -> float:
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    denom = (float(np.linalg.norm(a)) * float(np.linalg.norm(b))) or 1.0
    return float(np.dot(a, b) / denom)


def search(query_vec, limit: int = 60, media_ids: list[int] | None = None,
           track_id: int | None = None, lang: str | None = None) -> list[tuple[int, float]]:
    """Top-(segment_id, cosine) for a query vector via brute-force numpy."""
    db = get_db()
    q = np.asarray(query_vec, dtype=np.float32)
    qn = float(np.linalg.norm(q)) or 1.0
    sql = ("SELECT e.segment_id, e.vec, e.dim FROM segment_embeddings e "
           "JOIN segments s ON s.id = e.segment_id WHERE 1=1")
    params: list = []
    if media_ids:
        sql += f" AND e.media_id IN ({','.join('?' * len(media_ids))})"
        params += list(media_ids)
    if track_id is not None:
        sql += " AND s.track_id = ?"
        params.append(track_id)
    from .search import lang_cond  # restrict to one subtitle language
    clause, cparams = lang_cond(lang)
    sql += clause
    params += cparams
    rows = db.execute(sql, params).fetchall()
    if not rows:
        return []
    dim = len(q)
    ids, mat = [], []
    for r in rows:
        if r["dim"] != dim:
            continue  # different model/version — skip until re-embedded
        ids.append(r["segment_id"])
        mat.append(_from_blob(r["vec"]))
    if not ids:
        return []
    m = np.vstack(mat)
    norms = np.linalg.norm(m, axis=1)
    norms[norms == 0] = 1.0
    sims = (m @ q) / (norms * qn)
    k = min(limit, len(ids))
    top = np.argpartition(-sims, k - 1)[:k]
    top = top[np.argsort(-sims[top])]
    return [(int(ids[i]), float(sims[i])) for i in top]
