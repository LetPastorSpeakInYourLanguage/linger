"""Algorithmic topic segmentation: live preview + hand-adjust + commit."""
from backend import segmentation
from backend.db import get_db
from backend.engines import embeddings
from backend.engines.fakes import FakeEmbeddingEngine


def _media_with_segments(user, title, lines):
    db = get_db()
    mid = db.execute(
        "INSERT INTO media (title, type, filename, duration, status, added_by) "
        "VALUES (?, 'video', 'source.mp4', 120.0, 'ready', ?)", (title, user["id"])).lastrowid
    tid = db.execute("INSERT INTO tracks (media_id, name, lang_code) VALUES (?, 'en', 'en')",
                     (mid,)).lastrowid
    for i, (a, b, txt) in enumerate(lines):
        db.execute("INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text) "
                   "VALUES (?,?,?,?,?,?)", (mid, tid, i, a, b, txt))
    db.commit()
    return mid, tid


def _two_topic_transcript():
    # Two clearly different topics, ~3s/line, ≥20s & ≥6 lines per side so a
    # boundary is legal. Shared vocab within a topic makes its centroid cohesive.
    dog = ["the dog ran fast across the green field",
           "a puppy sprinted over the grassy meadow",
           "dogs love to run in the open field",
           "the hound raced through the tall grass",
           "puppies playing fetch in the sunny field",
           "the dog chased a ball across the meadow",
           "running dogs enjoy the wide green field",
           "a happy puppy rolled in the grass"]
    money = ["the stock market crashed on tuesday morning",
             "investors sold shares as prices fell sharply",
             "the market lost billions in market value",
             "traders panicked over falling stock prices",
             "the financial markets dropped again today",
             "shares tumbled as investors fled the market",
             "stock prices collapsed across the exchange",
             "the market downturn wiped out investor gains"]
    lines, t = [], 0.0
    for txt in dog + money:
        lines.append((t, t + 3.0, txt))
        t += 3.0
    return lines


def test_preview_finds_topic_boundary(client, user):
    embeddings.set_embedding_engine(FakeEmbeddingEngine())
    try:
        mid, tid = _media_with_segments(user, "Topic clip", _two_topic_transcript())
        r = client.post(f"/api/media/{mid}/segment/preview", json={"preset": "balanced"})
        assert r.status_code == 200, r.text
        data = r.json()
        plan = data["plan"]
        # at least one real split → ≥2 cuts, and the split lands near line 8
        assert len(plan) >= 2
        assert data["params"]["name"] == "balanced"
        assert "min_split_score" in data["param_bounds"]
        boundary = plan[0]["to_idx"]
        assert 5 <= boundary <= 10, f"boundary at {boundary}, expected the topic change ~8"
    finally:
        embeddings.set_embedding_engine(None)


def test_params_override_changes_cut_count(client, user):
    """Lowering thresholds (the live sliders) must yield more, finer cuts."""
    embeddings.set_embedding_engine(FakeEmbeddingEngine())
    try:
        mid, _ = _media_with_segments(user, "Tune clip", _two_topic_transcript())
        coarse = client.post(f"/api/media/{mid}/segment/preview",
                             json={"preset": "coarse"}).json()["plan"]
        fine = client.post(f"/api/media/{mid}/segment/preview", json={
            "preset": "fine",
            "params": {"min_segments": 2, "min_duration_s": 3, "min_split_score": 0.0},
        }).json()["plan"]
        assert len(fine) >= len(coarse)
    finally:
        embeddings.set_embedding_engine(None)


def test_commit_creates_cuts(client, user):
    embeddings.set_embedding_engine(FakeEmbeddingEngine())
    try:
        mid, tid = _media_with_segments(user, "Commit clip", _two_topic_transcript())
        plan = client.post(f"/api/media/{mid}/segment/preview", json={}).json()["plan"]
        r = client.post(f"/api/media/{mid}/segment/commit",
                        json={"track_id": tid, "plan": plan, "folder": "My topics",
                              "user_id": user["id"]})
        assert r.status_code == 200, r.text
        assert r.json()["created"] == len(plan)
        db = get_db()
        n = db.execute("SELECT COUNT(*) AS n FROM cuts WHERE media_id=?", (mid,)).fetchone()["n"]
        assert n == len(plan)
        folder = db.execute(
            "SELECT f.name FROM cuts c JOIN folders f ON f.id=c.folder_id "
            "WHERE c.media_id=? LIMIT 1", (mid,)).fetchone()
        assert folder["name"] == "My topics"
    finally:
        embeddings.set_embedding_engine(None)


def test_preview_without_engine_is_a_clean_400(client, user):
    embeddings.set_embedding_engine(None)
    mid, _ = _media_with_segments(user, "No engine clip",
                                  [(0.0, 1.0, "a line"), (1.0, 2.0, "another line")])
    r = client.post(f"/api/media/{mid}/segment/preview", json={})
    assert r.status_code == 400
    assert "embedding" in r.json()["detail"].lower()
