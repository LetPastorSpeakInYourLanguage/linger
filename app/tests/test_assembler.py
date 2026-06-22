"""Assembler backend: uncapped scope + breakdowns, and the draft/final model."""
from backend.db import get_db


def _media(user, title="M"):
    db = get_db()
    mid = db.execute(
        "INSERT INTO media (title, type, filename, duration, status, added_by) "
        "VALUES (?, 'video', 's.mp4', 60.0, 'ready', ?)", (title, user["id"])).lastrowid
    tid = db.execute("INSERT INTO tracks (media_id, name) VALUES (?, 'en')", (mid,)).lastrowid
    db.commit()
    return mid, tid


def _cut(mid, tid, i, folder_id=None, tag=None):
    db = get_db()
    sid = db.execute("INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text) "
                     "VALUES (?,?,?,?,?,?)", (mid, tid, i, i * 1.0, i * 1.0 + 1, f"line {i}")).lastrowid
    cid = db.execute("INSERT INTO cuts (media_id, title, folder_id) VALUES (?,?,?)",
                     (mid, f"cut {i}", folder_id)).lastrowid
    db.execute("INSERT INTO cut_segments (cut_id, segment_id, position) VALUES (?,?,0)", (cid, sid))
    if tag:
        tid2 = db.execute("INSERT INTO tags (name) VALUES (?) ON CONFLICT(name) DO UPDATE SET name=name "
                          "RETURNING id", (tag,)).fetchone()["id"]
        db.execute("INSERT OR IGNORE INTO cut_tags (cut_id, tag_id) VALUES (?,?)", (cid, tid2))
    db.commit()
    return cid


def test_scope_is_uncapped_with_breakdowns(client, user):
    mid, tid = _media(user, "Scope movie")
    fid = client.post("/api/folders", json={"name": "Pool"}).json()["id"]
    for i in range(250):                      # > the old 200 cap
        _cut(mid, tid, i, folder_id=fid, tag=("hero" if i % 2 == 0 else None))
    scope = client.post("/api/assembler/scope", json={"media_ids": str(mid)}).json()
    assert scope["total"] == 250 and len(scope["cut_ids"]) == 250
    assert any(b["count"] == 250 for b in scope["by_folder"])
    assert scope["by_media"][0]["count"] == 250
    assert any(t["name"] == "hero" and t["count"] == 125 for t in scope["by_tag"])
    assert scope["used"] == 0 and scope["unused"] == 250

    # sample returns a handful of full payloads
    sample = client.post("/api/assembler/sample?n=5", json={"media_ids": str(mid)}).json()
    assert len(sample) == 5 and all("segments" in c for c in sample)

    # /api/cuts can also exceed 200 when asked
    big = client.get(f"/api/cuts?media_ids={mid}&limit=1000").json()
    assert len(big) == 250


def test_draft_then_finalize(client, user):
    mid, tid = _media(user, "Draft movie")
    c1, c2 = _cut(mid, tid, 1), _cut(mid, tid, 2)
    d = client.post("/api/recompositions",
                    json={"title": "My draft", "user_id": user["id"], "status": "draft",
                          "cut_ids": [c1, c2]}).json()
    assert d["status"] == "draft" and d["cut_count"] == 2

    # drafts are hidden from the default (Studio) listing, visible under status=draft
    finals = client.get("/api/recompositions").json()
    assert all(r["id"] != d["id"] for r in finals)
    drafts = client.get("/api/recompositions?status=draft").json()
    assert any(r["id"] == d["id"] for r in drafts)

    # finalize → now shows in the Studio listing
    client.patch(f"/api/recompositions/{d['id']}", json={"status": "final"})
    finals2 = client.get("/api/recompositions").json()
    assert any(r["id"] == d["id"] for r in finals2)
