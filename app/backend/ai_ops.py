"""AI helpers: embedding-based tag suggestions and prompt-driven recomposition
drafting. All degrade gracefully when no embedding/LLM backend is installed."""
from __future__ import annotations

from . import llm, settings, vectors
from .engines import embeddings


def _get_or_create_folder(db, name: str) -> int:
    name = (name or "AI cuts").strip() or "AI cuts"
    row = db.execute("SELECT id FROM folders WHERE name=?", (name,)).fetchone()
    return row["id"] if row else db.execute(
        "INSERT INTO folders (name) VALUES (?)", (name,)).lastrowid


def _get_or_create_tag(db, name: str) -> int | None:
    name = (name or "").strip().lstrip("#").lower()
    if not name:
        return None
    row = db.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
    return row["id"] if row else db.execute(
        "INSERT INTO tags (name) VALUES (?)", (name,)).lastrowid


def _resolve_track(db, media_id, track_id):
    if track_id is None:
        row = db.execute("SELECT id FROM tracks WHERE media_id=? ORDER BY id LIMIT 1",
                         (media_id,)).fetchone()
        if not row:
            raise RuntimeError("this media has no subtitle track")
        track_id = row["id"]
    return track_id


def ai_cut_plan(db, media_id: int, prompt: str, track_id: int | None = None,
                chunk_lines: int | None = None) -> dict:
    """Propose cuts (no DB writes) — the user reviews/confirms before commit.
    Reads the WHOLE transcript in chunks so small-context local models work."""
    engine = llm.get_llm_engine()
    if engine is None:
        raise RuntimeError("no LLM configured — set a provider (see /api/ai/status)")
    track_id = _resolve_track(db, media_id, track_id)
    segs = db.execute(
        "SELECT id, idx, text FROM segments WHERE track_id=? ORDER BY idx", (track_id,)).fetchall()
    if not segs:
        raise RuntimeError("track has no segments")
    by_idx = {s["idx"]: s for s in segs}
    system = (
        "You turn a transcript into video clips ('cuts'). Each line is 'idx: text'. "
        "Return ONLY JSON: {\"cuts\":[{\"from_idx\":int,\"to_idx\":int,\"title\":str,"
        "\"tags\":[str],\"folder\":str}]}. from_idx..to_idx are inclusive ranges of "
        "consecutive lines (use the idx numbers shown). Pick tight, meaningful spans that "
        "satisfy the goal; give a short title, 1-4 lowercase tags, and a folder grouping "
        "similar cuts. If a chunk has nothing relevant, return an empty list.")

    if chunk_lines is None:
        chunk_lines = int(settings.get("ai_chunk_lines") or 400)
    chunk_lines = max(50, chunk_lines)
    plan, seen = [], set()
    for i in range(0, len(segs), chunk_lines):
        chunk = segs[i:i + chunk_lines]
        listing = "\n".join(f"{s['idx']}: {s['text']}" for s in chunk)
        try:
            result = engine.complete_json(
                system, f"Goal: {prompt}\n\nTranscript (idx: text):\n{listing}")
        except Exception as e:
            raise RuntimeError(f"LLM call failed: {e}")
        for spec in result.get("cuts", []) or []:
            try:
                a, b = int(spec["from_idx"]), int(spec["to_idx"])
            except (KeyError, ValueError, TypeError):
                continue
            if b < a:
                a, b = b, a
            key = (a, b)
            if key in seen:
                continue
            seen.add(key)
            idxs = [i for i in range(a, b + 1) if i in by_idx]
            if not idxs:
                continue
            preview = " ".join(by_idx[i]["text"] for i in idxs)[:200]
            plan.append({
                "from_idx": a, "to_idx": b, "lines": len(idxs),
                "title": ((spec.get("title") or by_idx[idxs[0]]["text"]) or "AI cut").strip()[:80],
                "tags": [t for t in (spec.get("tags") or []) if isinstance(t, str)][:4],
                "folder": (spec.get("folder") or "AI cuts").strip() or "AI cuts",
                "preview": preview,
            })
    return {"track_id": track_id, "plan": plan}


def ai_cut_commit(db, media_id: int, track_id: int, plan: list[dict],
                  created_by: int | None = None) -> dict:
    """Create the cuts from a (user-confirmed) plan — files & tags them."""
    track_id = _resolve_track(db, media_id, track_id)
    segs = db.execute(
        "SELECT id, idx FROM segments WHERE track_id=? ORDER BY idx", (track_id,)).fetchall()
    by_idx = {s["idx"]: s["id"] for s in segs}
    created = []
    for spec in plan or []:
        try:
            a, b = int(spec["from_idx"]), int(spec["to_idx"])
        except (KeyError, ValueError, TypeError):
            continue
        if b < a:
            a, b = b, a
        seg_ids = [by_idx[i] for i in range(a, b + 1) if i in by_idx]
        if not seg_ids:
            continue
        folder = (spec.get("folder") or "AI cuts").strip() or "AI cuts"
        folder_id = _get_or_create_folder(db, folder)
        title = (spec.get("title") or "AI cut").strip()[:80] or "AI cut"
        cut_id = db.execute(
            "INSERT INTO cuts (media_id, title, folder_id, created_by) VALUES (?,?,?,?)",
            (media_id, title, folder_id, created_by)).lastrowid
        for pos, sid in enumerate(seg_ids):
            db.execute("INSERT INTO cut_segments (cut_id, segment_id, position) VALUES (?,?,?)",
                       (cut_id, sid, pos))
        tags = [t for t in (spec.get("tags") or []) if isinstance(t, str)]
        for t in tags:
            tid = _get_or_create_tag(db, t)
            if tid:
                db.execute("INSERT OR IGNORE INTO cut_tags (cut_id, tag_id) VALUES (?,?)",
                           (cut_id, tid))
        created.append({"cut_id": cut_id, "title": title, "folder": folder, "tags": tags})
    db.commit()
    return {"created": len(created), "cuts": created}


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
