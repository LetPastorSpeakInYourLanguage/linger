"""Nested folders: '/'-path names, ancestor materialisation, descendant-aware
filtering, cascading rename, recursive delete."""
from backend.db import get_db


def _media_with_track(user):
    db = get_db()
    mid = db.execute(
        "INSERT INTO media (title, type, filename, duration, status, added_by) "
        "VALUES ('M', 'video', 's.mp4', 60.0, 'ready', ?)", (user["id"],)).lastrowid
    tid = db.execute("INSERT INTO tracks (media_id, name) VALUES (?, 'en')", (mid,)).lastrowid
    db.commit()
    return mid, tid


def test_create_materialises_ancestors(client):
    r = client.post("/api/folders", json={"name": " Movies / Action / Heist "})
    assert r.status_code == 200
    assert r.json()["name"] == "Movies/Action/Heist"
    names = {f["name"] for f in client.get("/api/folders").json()}
    assert {"Movies", "Movies/Action", "Movies/Action/Heist"} <= names


def test_nested_filter_includes_descendants(client, user):
    mid, tid = _media_with_track(user)
    db = get_db()
    # two cuts: one under Movies/Action, one under Movies/Comedy
    action = client.post("/api/folders", json={"name": "Movies/Action"}).json()["id"]
    comedy = client.post("/api/folders", json={"name": "Movies/Comedy"}).json()["id"]
    movies = next(f["id"] for f in client.get("/api/folders").json() if f["name"] == "Movies")
    for fid in (action, comedy):
        sid = db.execute("INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text) "
                         "VALUES (?,?,?,?,?,?)", (mid, tid, fid, fid * 1.0, fid * 1.0 + 1, "x")).lastrowid
        db.execute("INSERT INTO cuts (media_id, title, folder_id) VALUES (?, 'c', ?)", (mid, fid))
        cid = db.execute("SELECT last_insert_rowid() AS i").fetchone()["i"]
        db.execute("INSERT INTO cut_segments (cut_id, segment_id, position) VALUES (?,?,0)", (cid, sid))
    db.commit()

    # filtering by the PARENT returns both descendants' cuts
    both = client.get(f"/api/cuts?folder_ids={movies}").json()
    assert len(both) == 2
    # filtering by a leaf returns just that one
    one = client.get(f"/api/cuts?folder_ids={action}").json()
    assert len(one) == 1


def test_rename_cascades_to_descendants(client):
    client.post("/api/folders", json={"name": "Old/Sub/Leaf"})
    fid = next(f["id"] for f in client.get("/api/folders").json() if f["name"] == "Old")
    assert client.patch(f"/api/folders/{fid}", json={"name": "New"}).status_code == 200
    names = {f["name"] for f in client.get("/api/folders").json()}
    assert "New/Sub/Leaf" in names and not any(n.startswith("Old") for n in names)


def test_recursive_delete(client):
    client.post("/api/folders", json={"name": "Trash/A/B"})
    fid = next(f["id"] for f in client.get("/api/folders").json() if f["name"] == "Trash")
    client.delete(f"/api/folders/{fid}?recursive=1")
    names = {f["name"] for f in client.get("/api/folders").json()}
    assert not any(n.startswith("Trash") for n in names)


def test_flat_names_still_work(client):
    r = client.post("/api/folders", json={"name": "Favourites"})
    assert r.json()["name"] == "Favourites"
    f = next(x for x in client.get("/api/folders").json() if x["name"] == "Favourites")
    assert f["depth"] == 0 and f["leaf"] == "Favourites"
