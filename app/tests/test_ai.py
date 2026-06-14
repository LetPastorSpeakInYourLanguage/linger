"""P6.2 auto-cut, P6.3 auto-tag, P6.4 prompt-compose."""
from backend import ai_ops, llm
from backend.db import get_db
from backend.engines import embeddings
from backend.engines.fakes import FakeEmbeddingEngine

from .conftest import wait_for


def _job(client, jid):
    return next(j for j in client.get("/api/jobs").json() if j["id"] == jid)


def _media(user, title, lines):
    db = get_db()
    mid = db.execute(
        "INSERT INTO media (title, type, filename, duration, status, added_by) "
        "VALUES (?, 'video', 'source.mp4', 60.0, 'ready', ?)", (title, user["id"])).lastrowid
    tid = db.execute("INSERT INTO tracks (media_id, name) VALUES (?, 'en')", (mid,)).lastrowid
    for i, (a, b, txt) in enumerate(lines):
        db.execute("INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text) "
                   "VALUES (?,?,?,?,?,?)", (mid, tid, i, a, b, txt))
    db.commit()
    return mid, tid


def test_auto_cut_splits_on_gap_and_sentence(client, user):
    # two sentences with a big pause between them → two cuts
    mid, _ = _media(user, "Autocut clip", [
        (0.0, 1.0, "Hello there."),
        (5.0, 6.0, "A new topic begins here."),
        (6.1, 7.0, "And it continues now."),
    ])
    r = client.post(f"/api/media/{mid}/auto-cut",
                    json={"max_gap_s": 1.0, "min_cut_s": 0.5, "user_id": user["id"]})
    assert r.status_code == 200
    assert r.json()["created"] >= 2
    cuts = client.get(f"/api/cuts?media_id={mid}").json()
    assert cuts and all("auto" in c["tags"] for c in cuts)
    folders = client.get("/api/folders").json()
    assert any(f["name"] == "Auto-cuts" for f in folders)


def test_tag_suggestions_from_embeddings(client, user):
    embeddings.set_embedding_engine(FakeEmbeddingEngine())
    try:
        mid, _ = _media(user, "Tagging clip", [
            (0.0, 1.0, "the dog barked at the mailman"),
            (1.0, 2.0, "puppy played fetch in the yard"),
            (2.0, 3.0, "the stock market rallied today"),
        ])
        client.post(f"/api/media/{mid}/embed")
        wait_for(lambda: get_db().execute(
            "SELECT COUNT(*) c FROM segment_embeddings WHERE media_id=?", (mid,)
        ).fetchone()["c"] >= 3, timeout=30)
        segs = client.get(f"/api/media/{mid}/segments").json()
        # an existing 'dogs' cut establishes the tag centroid
        client.post("/api/cuts", json={"media_id": mid, "title": "dog one",
                    "segment_ids": [segs[0]["id"]], "tags": ["dogs"], "user_id": user["id"]})
        # a new dog-themed cut should get 'dogs' suggested
        target = client.post("/api/cuts", json={"media_id": mid, "title": "dog two",
                    "segment_ids": [segs[1]["id"]], "user_id": user["id"]}).json()
        sug = client.get(f"/api/cuts/{target['id']}/tag-suggestions").json()["suggestions"]
        assert any(s["tag"] == "dogs" for s in sug)
    finally:
        embeddings.set_embedding_engine(None)


class _FakeLLM:
    name = "fake-llm"

    def complete_json(self, system, prompt):
        # reverse the order of whatever ids appear, to prove the LLM path is used
        import re
        ids = [int(x) for x in re.findall(r"^(\d+):", prompt, re.M)]
        return {"cut_ids": list(reversed(ids))}


def test_compose_semantic_then_llm_order(client, user):
    embeddings.set_embedding_engine(FakeEmbeddingEngine())
    llm.set_llm_engine(_FakeLLM())
    try:
        mid, _ = _media(user, "Compose clip", [
            (0.0, 1.0, "ocean waves crash on the sandy beach"),
            (1.0, 2.0, "a sailboat drifts on calm sea water"),
            (2.0, 3.0, "tax policy and quarterly earnings reports"),
        ])
        client.post(f"/api/media/{mid}/embed")
        wait_for(lambda: get_db().execute(
            "SELECT COUNT(*) c FROM segment_embeddings WHERE media_id=?", (mid,)
        ).fetchone()["c"] >= 3, timeout=30)
        segs = client.get(f"/api/media/{mid}/segments").json()
        for i in range(3):
            client.post("/api/cuts", json={"media_id": mid, "title": f"c{i}",
                        "segment_ids": [segs[i]["id"]], "user_id": user["id"]})
        r = client.post("/api/ai/compose", json={
            "prompt": "relaxing scenes by the sea", "create": True, "user_id": user["id"]})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["used_llm"] is True
        assert body["cut_ids"] and "recomp_id" in body
        # the beach/sea cuts should rank above the tax one
        titles = {c["cut_id"]: c["title"] for c in body["candidates"]}
        assert any("c0" == titles.get(cid) or "c1" == titles.get(cid)
                   for cid in body["cut_ids"][:2])
    finally:
        embeddings.set_embedding_engine(None)
        llm.set_llm_engine(None)
