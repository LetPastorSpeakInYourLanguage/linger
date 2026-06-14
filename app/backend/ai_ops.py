"""AI helpers: embedding-based tag suggestions and prompt-driven recomposition
drafting. All degrade gracefully when no embedding/LLM backend is installed."""
from __future__ import annotations

from . import llm, vectors
from .engines import embeddings


def tag_suggestions(db, cut_id: int, limit: int = 6) -> list[dict]:
    """Suggest tags whose centroid (mean of the embeddings of cuts already
    wearing them) is closest to this cut — excluding tags it already has."""
    if not embeddings.available():
        return []
    seg_ids = [r["segment_id"] for r in db.execute(
        "SELECT segment_id FROM cut_segments WHERE cut_id=?", (cut_id,))]
    target = vectors.mean_vector(seg_ids)
    if target is None:
        return []
    existing = {r["name"] for r in db.execute(
        "SELECT t.name FROM cut_tags ct JOIN tags t ON t.id=ct.tag_id WHERE ct.cut_id=?",
        (cut_id,))}

    # gather segment ids per tag (across all other cuts)
    by_tag: dict[str, list[int]] = {}
    for r in db.execute("""
            SELECT t.name, cs.segment_id
            FROM cut_tags ct
            JOIN tags t ON t.id = ct.tag_id
            JOIN cut_segments cs ON cs.cut_id = ct.cut_id
            WHERE ct.cut_id <> ?""", (cut_id,)):
        if r["name"] in existing:
            continue
        by_tag.setdefault(r["name"], []).append(r["segment_id"])

    scored = []
    for name, ids in by_tag.items():
        centroid = vectors.mean_vector(ids)
        if centroid is None:
            continue
        scored.append({"tag": name, "score": round(vectors.cosine(target, centroid), 4)})
    scored.sort(key=lambda x: -x["score"])
    return scored[:limit]


def compose(db, prompt: str, limit: int = 12, media_ids: list[int] | None = None) -> dict:
    """Retrieve candidate cuts semantically related to a prompt, then (if an LLM
    is configured) let it pick & order the best ones into a recomposition draft.
    Returns {cut_ids, candidates, used_llm}. No DB writes — the caller decides."""
    engine = embeddings.get_embedding_engine()
    if engine is None:
        return {"cut_ids": [], "candidates": [], "used_llm": False,
                "detail": "semantic search unavailable — install sentence-transformers"}
    qv = engine.embed([prompt])[0]
    # rank cuts by the best semantic hit among their segments
    hits = vectors.search(qv, limit=400, media_ids=media_ids)
    best: dict[int, float] = {}
    for seg_id, sim in hits:
        row = db.execute("SELECT cut_id FROM cut_segments WHERE segment_id=?",
                         (seg_id,)).fetchall()
        for r in row:
            cid = r["cut_id"]
            if sim > best.get(cid, -1):
                best[cid] = sim
    ranked = sorted(best, key=lambda c: -best[c])[:limit]
    candidates = []
    for cid in ranked:
        c = db.execute("SELECT id, title FROM cuts WHERE id=?", (cid,)).fetchone()
        if not c:
            continue
        text = " ".join(r["text"] for r in db.execute(
            "SELECT s.text FROM cut_segments cs JOIN segments s ON s.id=cs.segment_id "
            "WHERE cs.cut_id=? ORDER BY cs.position", (cid,)))
        candidates.append({"cut_id": cid, "title": c["title"], "score": round(best[cid], 4),
                           "text": text[:300]})

    cut_ids = [c["cut_id"] for c in candidates]
    used_llm = False
    engine_llm = llm.get_llm_engine()
    if engine_llm and candidates:
        try:
            listing = "\n".join(
                f'{c["cut_id"]}: {c["title"]} — {c["text"]}' for c in candidates)
            result = engine_llm.complete_json(
                "You arrange short video cuts into a compelling sequence. "
                "Return JSON {\"cut_ids\": [int, ...]} using only the given ids, "
                "ordered best-first, dropping irrelevant ones.",
                f"Goal: {prompt}\n\nCuts:\n{listing}")
            ids = [int(x) for x in result.get("cut_ids", []) if int(x) in set(cut_ids)]
            if ids:
                cut_ids = ids
                used_llm = True
        except Exception:
            pass  # fall back to the semantic order
    return {"cut_ids": cut_ids, "candidates": candidates, "used_llm": used_llm}
