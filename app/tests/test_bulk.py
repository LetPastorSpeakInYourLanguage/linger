"""Bulk operations on the Cuts page: tag / folder / delete / translate."""
from backend.db import get_db
from backend.engines import translate
from backend.engines.fakes import FakeTranslateEngine


def _cuts(client, user, n=3):
    db = get_db()
    mid = db.execute(
        "INSERT INTO media (title, type, filename, duration, status, added_by) "
        "VALUES ('Bulk clip','video','source.mp4',30.0,'ready',?)", (user["id"],)).lastrowid
    tid = db.execute("INSERT INTO tracks (media_id, name, lang_code) VALUES (?, 'en','en')",
                     (mid,)).lastrowid
    ids = []
    for i in range(n):
        sid = db.execute("INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text) "
                         "VALUES (?,?,?,?,?,?)", (mid, tid, i, i, i + 1, f"line {i}")).lastrowid
        ids.append(db.execute("INSERT INTO cuts (media_id, title, created_by) VALUES (?,?,?)",
                              (mid, f"cut {i}", user["id"])).lastrowid)
        db.execute("INSERT INTO cut_segments (cut_id, segment_id, position) VALUES (?,?,0)",
                   (ids[-1], sid))
    db.commit()
    return mid, ids


def test_bulk_add_tags_and_set_folder(client, user):
    _, ids = _cuts(client, user)
    r = client.post("/api/cuts/bulk", json={"cut_ids": ids, "action": "add_tags",
                                            "tags": ["epic", "review"]})
    assert r.status_code == 200 and r.json()["affected"] == len(ids)
    cuts = client.get("/api/cuts").json()
    mine = [c for c in cuts if c["id"] in ids]
    assert all("epic" in c["tags"] and "review" in c["tags"] for c in mine)

    r = client.post("/api/cuts/bulk", json={"cut_ids": ids, "action": "set_folder",
                                            "new_folder": "Bulk box"})
    assert r.status_code == 200
    folder = next(f for f in client.get("/api/folders").json() if f["name"] == "Bulk box")
    moved = [c for c in client.get(f"/api/cuts?folder_id={folder['id']}").json() if c["id"] in ids]
    assert len(moved) == len(ids)


def test_bulk_delete(client, user):
    _, ids = _cuts(client, user)
    r = client.post("/api/cuts/bulk", json={"cut_ids": ids, "action": "delete"})
    assert r.status_code == 200 and r.json()["affected"] == len(ids)
    remaining = {c["id"] for c in client.get("/api/cuts").json()}
    assert not (set(ids) & remaining)


def test_bulk_translate(client, user):
    _, ids = _cuts(client, user)
    translate.set_translate_engine(FakeTranslateEngine())
    try:
        r = client.post("/api/cuts/bulk", json={"cut_ids": ids, "action": "translate",
                                                "lang_code": "es", "user_id": user["id"]})
        assert r.status_code == 200 and r.json()["translated"] == len(ids)
        data = client.get(f"/api/cuts/{ids[0]}/translations").json()
        assert any(t["lang_code"] == "es" for t in data["translations"])
    finally:
        translate.set_translate_engine(None)


def test_bulk_requires_selection(client):
    assert client.post("/api/cuts/bulk", json={"cut_ids": [], "action": "delete"}).status_code == 400
