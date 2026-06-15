"""P8.1 relinkable media: content hash on import, linked status, sha256 relink."""
import shutil

from backend import media_ops, storage
from backend.db import get_db

from .conftest import wait_for


def _media_status(client, mid):
    return client.get(f"/api/media/{mid}").json()["status"]


def test_import_records_content_hash(client, user, sample_video):
    r = client.post("/api/media/import-path", json={
        "path": str(sample_video), "title": "Hashed", "user_id": user["id"]})
    mid = r.json()["id"]
    wait_for(lambda: _media_status(client, mid) == "ready", timeout=60)
    m = client.get(f"/api/media/{mid}").json()
    assert m["content_hash"] and len(m["content_hash"]) == 64
    assert m["linked"] is True
    # the kept host path was recorded as a relinkable source
    srcs = client.get(f"/api/media/{mid}/sources").json()
    assert any(s["kind"] == "local" and s["locator"] == str(sample_video) for s in srcs)
    assert m["content_hash"] == media_ops.sha256_file(sample_video)


def test_unlinked_then_relink_with_hash_check(client, user, sample_video, tmp_path):
    # a media row whose bytes this instance is missing (shared-DB scenario)
    db = get_db()
    digest = media_ops.sha256_file(sample_video)
    mid = db.execute(
        "INSERT INTO media (title, type, filename, duration, status, added_by, content_hash) "
        "VALUES ('Orphan','video','source.mp4',2.0,'ready',?,?)",
        (user["id"], digest)).lastrowid
    db.commit()
    assert storage.is_linked(mid) is False
    assert client.get(f"/api/media/{mid}").json()["linked"] is False

    # wrong file → rejected on hash mismatch
    wrong = tmp_path / "wrong.mp4"
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=15",
                    "-t", "1", "-pix_fmt", "yuv420p", str(wrong)], capture_output=True, check=True)
    bad = client.post(f"/api/media/{mid}/relink", json={"path": str(wrong)})
    assert bad.status_code == 409

    # correct copy → accepted, prepared into the store, becomes linked
    copy = tmp_path / "mycopy.mp4"
    shutil.copy2(sample_video, copy)
    ok = client.post(f"/api/media/{mid}/relink", json={"path": str(copy)})
    assert ok.status_code == 200, ok.text
    # wait on the authoritative signal (status), which the prepare job sets last
    wait_for(lambda: client.get(f"/api/media/{mid}").json()["status"] == "ready", timeout=60)
    # now the bytes are in the store and the transcript was never touched
    assert client.get(f"/api/media/{mid}").json()["linked"] is True


def test_relink_by_url_records_source(client, user):
    """Relinking from a URL records a 'url' source and queues a re-download
    (no hash gate — a re-encode may differ)."""
    db = get_db()
    mid = db.execute(
        "INSERT INTO media (title, type, filename, status, added_by) "
        "VALUES ('FromUrl','video','',' error',?)", (user["id"],)).lastrowid
    db.commit()
    r = client.post(f"/api/media/{mid}/relink",
                    json={"url": "https://example.com/clip.mp4"})
    assert r.status_code == 200 and r.json()["via"] == "url"
    srcs = client.get(f"/api/media/{mid}/sources").json()
    assert any(s["kind"] == "url" and "example.com" in s["locator"] for s in srcs)
