"""Cross-reference theme clustering: Louvain over cut embeddings."""
from backend import themes, vectors
from backend.db import get_db
from backend.engines import embeddings
from backend.engines.fakes import FakeEmbeddingEngine


def _media(user, title):
    db = get_db()
    mid = db.execute(
        "INSERT INTO media (title, type, filename, duration, status, added_by) "
        "VALUES (?, 'video', 'source.mp4', 120.0, 'ready', ?)", (title, user["id"])).lastrowid
    tid = db.execute("INSERT INTO tracks (media_id, name, lang_code) VALUES (?, 'en', 'en')",
                     (mid,)).lastrowid
    return mid, tid


def _add_cut(mid, tid, title, texts, *, embed=True):
    """Create a cut whose member segments carry the given lines, embedding them
    so the cut has a usable vector."""
    db = get_db()
    eng = embeddings.get_embedding_engine()
    cut_id = db.execute("INSERT INTO cuts (media_id, title) VALUES (?,?)", (mid, title)).lastrowid
    base = db.execute("SELECT COALESCE(MAX(idx),-1)+1 AS n FROM segments WHERE track_id=?",
                      (tid,)).fetchone()["n"]
    for pos, txt in enumerate(texts):
        idx = base + pos
        sid = db.execute(
            "INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text) "
            "VALUES (?,?,?,?,?,?)", (mid, tid, idx, idx * 2.0, idx * 2.0 + 2.0, txt)).lastrowid
        db.execute("INSERT INTO cut_segments (cut_id, segment_id, position) VALUES (?,?,?)",
                   (cut_id, sid, pos))
        if embed:
            vectors.upsert(sid, mid, txt, eng.embed([txt])[0], eng.name)
    db.commit()
    return cut_id


def _two_theme_library(user):
    """Two interleaved themes (space / cooking) with disjoint, repetition-heavy
    vocab — within-theme cuts are near-identical vectors, cross-theme ~0 — so a
    correct clustering must group by meaning across time, not by adjacency."""
    mid, tid = _media(user, "Mixed talk")
    space_a = _add_cut(mid, tid, "rockets orbit",
                       ["rocket orbit rocket orbit launch", "rocket orbit rocket orbit space"])
    cook_a = _add_cut(mid, tid, "baking bread",
                      ["bread dough bread dough oven", "bread dough bread dough bake"])
    space_b = _add_cut(mid, tid, "orbit rocket again",
                       ["rocket orbit rocket orbit engine", "rocket orbit rocket orbit capsule"])
    cook_b = _add_cut(mid, tid, "oven dough",
                      ["bread dough bread dough rise", "bread dough bread dough loaf"])
    return mid, {"space": {space_a, space_b}, "cook": {cook_a, cook_b}}


def test_cluster_groups_related_cuts(client, user):
    embeddings.set_embedding_engine(FakeEmbeddingEngine())
    try:
        mid, expected = _two_theme_library(user)
        db = get_db()
        scope = themes.cut_ids_for_scope(db, [mid], None)
        res = themes.cluster(db, scope, themes.config_from("balanced"))
        assert res["considered"] == 4
        # the space cuts should land together, and the cooking cuts together —
        # never mixed (proves grouping is by meaning, not time order)
        groups = [set(c["cut_ids"]) for c in res["clusters"]]
        assert expected["space"] in groups
        assert expected["cook"] in groups
    finally:
        embeddings.set_embedding_engine(None)


def test_cluster_preview_commit_list_delete(client, user):
    embeddings.set_embedding_engine(FakeEmbeddingEngine())
    try:
        mid, _ = _two_theme_library(user)
        prev = client.post("/api/clusters/preview", json={"media_ids": [mid]})
        assert prev.status_code == 200, prev.text
        clusters = prev.json()["clusters"]
        assert len(clusters) >= 2

        r = client.post("/api/clusters/commit", json={"clusters": clusters, "replace": True})
        assert r.json()["created"] == len(clusters)

        listed = client.get("/api/clusters").json()["clusters"]
        assert len(listed) == len(clusters)
        assert all(c["members"] for c in listed)

        cid = listed[0]["id"]
        assert client.delete(f"/api/clusters/{cid}").status_code == 200
        assert len(client.get("/api/clusters").json()["clusters"]) == len(clusters) - 1
    finally:
        embeddings.set_embedding_engine(None)


def test_cluster_skips_cuts_without_embeddings(client, user):
    embeddings.set_embedding_engine(FakeEmbeddingEngine())
    try:
        mid, tid = _media(user, "Partial")
        _add_cut(mid, tid, "embedded", ["the rocket reached orbit"], embed=True)
        _add_cut(mid, tid, "bare", ["no vector here"], embed=False)
        db = get_db()
        res = themes.cluster(db, themes.cut_ids_for_scope(db, [mid], None),
                             themes.config_from("balanced"))
        # only the embedded cut is considered; one node can't form a cluster
        assert res["considered"] == 1
        assert res["clusters"] == []
    finally:
        embeddings.set_embedding_engine(None)
