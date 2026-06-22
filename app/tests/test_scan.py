"""Bulk ingest: scanning a drop-folder ingests new media, pairs sibling subs,
queues transcription only when subs are missing, and re-scans are idempotent."""
from backend import ingest
from backend.db import get_db


class FakeCtx:
    media_id = None
    def report(self, *a, **k): pass
    def check_cancel(self): pass


def _scan_folder(path, kind="media"):
    db = get_db()
    fid = db.execute("INSERT INTO scan_folders (path, kind) VALUES (?,?)", (str(path), kind)).lastrowid
    db.commit()
    return db.execute("SELECT * FROM scan_folders WHERE id=?", (fid,)).fetchone()


def test_scan_media_pairs_subs_and_skips_on_rescan(client, tmp_path):
    (tmp_path / "movie.mkv").write_bytes(b"not really a video")
    (tmp_path / "movie.en.srt").write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nhello world\n\n", encoding="utf-8")
    (tmp_path / "silent.mp4").write_bytes(b"no subs here")
    db = get_db()
    enq = []
    res = ingest.scan(db, _scan_folder(tmp_path), FakeCtx(), lambda *a, **k: enq.append(a))
    assert res["ingested"] == 2

    movie = db.execute("SELECT * FROM media WHERE title='movie'").fetchone()
    assert db.execute("SELECT COUNT(*) AS n FROM segments WHERE media_id=?",
                      (movie["id"],)).fetchone()["n"] == 1
    # the movie with subs is NOT queued to transcribe; the silent one IS
    by_media = {a[1]: a[2] for a in enq if a[0] == "prepare"}
    assert by_media[movie["id"]]["then_transcribe"] is False
    silent = db.execute("SELECT * FROM media WHERE title='silent'").fetchone()
    assert by_media[silent["id"]]["then_transcribe"] is True

    # re-scan: nothing new
    res2 = ingest.scan(db, _scan_folder(tmp_path), FakeCtx(), lambda *a, **k: None)
    assert res2["ingested"] == 0


def test_scan_folder_endpoints(client, tmp_path):
    (tmp_path / "x.mkv").write_bytes(b"x")
    r = client.post("/api/scan-folders", json={"path": str(tmp_path), "kind": "media"})
    assert r.status_code == 200
    fid = r.json()["id"]
    assert any(f["id"] == fid for f in client.get("/api/scan-folders").json())
    assert client.post(f"/api/scan-folders/{fid}/scan").json().get("job_id")
    client.delete(f"/api/scan-folders/{fid}")
    assert all(f["id"] != fid for f in client.get("/api/scan-folders").json())

    # a non-existent path is rejected
    assert client.post("/api/scan-folders", json={"path": "Z:/nope/nope"}).status_code == 400
