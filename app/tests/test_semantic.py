"""P6.1 semantic search: embed job, vector store, and hybrid RRF ranking."""
from backend import search, vectors
from backend.db import get_db
from backend.engines import embeddings
from backend.engines.fakes import FakeEmbeddingEngine

from .conftest import wait_for


def _job(client, jid):
    return next(j for j in client.get("/api/jobs").json() if j["id"] == jid)


def _media_with_segments(user, title, lines):
    db = get_db()
    mid = db.execute(
        "INSERT INTO media (title, type, filename, duration, status, added_by) "
        "VALUES (?, 'video', 'source.mp4', 30.0, 'ready', ?)", (title, user["id"])).lastrowid
    tid = db.execute("INSERT INTO tracks (media_id, name) VALUES (?, 'en')", (mid,)).lastrowid
    for i, (a, b, txt) in enumerate(lines):
        db.execute("INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text) "
                   "VALUES (?,?,?,?,?,?)", (mid, tid, i, a, b, txt))
    db.commit()
    return mid


def test_fake_embedding_similarity():
    eng = FakeEmbeddingEngine()
    cat1, cat2, phys = eng.embed([
        "the cat sat on the soft mat",
        "a cat is on a mat",
        "quantum physics lecture notes"])
    import numpy as np
    cos = lambda a, b: float(np.dot(a, b))
    assert cos(cat1, cat2) > cos(cat1, phys)  # shared words → closer


def test_embed_job_and_smart_search(client, user):
    embeddings.set_embedding_engine(FakeEmbeddingEngine())
    try:
        mid = _media_with_segments(user, "Semantic clip", [
            (0.0, 2.0, "the dog ran across the green field"),
            (2.0, 4.0, "a puppy sprinted over the grassy meadow"),
            (4.0, 6.0, "the stock market crashed on tuesday"),
        ])
        r = client.post(f"/api/media/{mid}/embed")
        assert r.status_code == 200
        wait_for(lambda: _job(client, r.json()["job_id"])["status"] == "done", timeout=30)

        st = client.get("/api/embed/status").json()
        assert st["available"] and st["embedded"] >= 3

        # smart search: a query sharing words with seg 2 ranks the related lines
        res = client.get("/api/search/segments",
                         params={"q": "dog running in a field", "smart": 1}).json()
        assert res, "smart search returned nothing"
        texts = [r["text"] for r in res]
        assert "the dog ran across the green field" in texts
        assert any("methods" in r for r in res)  # smart annotates contributing methods
    finally:
        embeddings.set_embedding_engine(None)


def test_embed_only_reembeds_changed(client, user):
    embeddings.set_embedding_engine(FakeEmbeddingEngine())
    try:
        mid = _media_with_segments(user, "Reembed clip", [(0.0, 1.0, "hello world")])
        r = client.post(f"/api/media/{mid}/embed")
        wait_for(lambda: _job(client, r.json()["job_id"])["status"] == "done", timeout=30)
        before = get_db().execute(
            "SELECT text_hash FROM segment_embeddings WHERE media_id=?", (mid,)).fetchone()
        # a second pass with no changes is a no-op (still 1 row, same hash)
        r2 = client.post(f"/api/media/{mid}/embed")
        wait_for(lambda: _job(client, r2.json()["job_id"])["status"] == "done", timeout=30)
        rows = get_db().execute(
            "SELECT text_hash FROM segment_embeddings WHERE media_id=?", (mid,)).fetchall()
        assert len(rows) == 1 and rows[0]["text_hash"] == before["text_hash"]
    finally:
        embeddings.set_embedding_engine(None)


def test_smart_search_without_engine_falls_back(client, user):
    embeddings.set_embedding_engine(None)  # no engine → smart degrades, no crash
    _media_with_segments(user, "Fallback clip", [(0.0, 1.0, "unique falconry term")])
    res = client.get("/api/search/segments",
                     params={"q": "falconry", "smart": 1}).json()
    assert any("falconry" in r["text"] for r in res)
