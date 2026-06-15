"""Convert a cut into a reusable background-audio bed (full or accompaniment)."""
import shutil

from backend import media_ops
from backend.db import get_db
from backend.engines import separation
from backend.engines.fakes import FakeSeparationEngine

from .conftest import wait_for


def _job(client, jid):
    return next(j for j in client.get("/api/jobs").json() if j["id"] == jid)


def _media_with_cut(client, user, sample_video):
    db = get_db()
    mid = db.execute(
        "INSERT INTO media (title, type, filename, duration, status, added_by) "
        "VALUES ('Bedsrc','video','source.mp4',2.0,'ready',?)", (user["id"],)).lastrowid
    shutil.copy2(sample_video, media_ops.media_dir(mid) / "source.mp4")
    tid = db.execute("INSERT INTO tracks (media_id, name) VALUES (?, 'o')", (mid,)).lastrowid
    sid = db.execute("INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text) "
                     "VALUES (?,?,0,0.2,1.8,'hi')", (mid, tid)).lastrowid
    db.commit()
    cut = client.post("/api/cuts", json={"media_id": mid, "title": "Scene",
                      "segment_ids": [sid], "user_id": user["id"]}).json()
    return mid, cut["id"]


def test_cut_to_bg_full_audio(client, user, sample_video):
    _, cut_id = _media_with_cut(client, user, sample_video)
    r = client.post(f"/api/cuts/{cut_id}/to-bg-audio",
                    json={"mode": "full", "user_id": user["id"]})
    assert r.status_code == 200
    asset_id = r.json()["asset_id"]
    wait_for(lambda: _job(client, r.json()["job_id"])["status"] == "done", timeout=60)
    asset = next(a for a in client.get("/api/audio-assets").json() if a["id"] == asset_id)
    assert asset["filename"] and asset["duration_s"] > 0
    # the bed is real, playable audio
    path = media_ops.bg_audio_path(asset["filename"])
    assert path.exists() and media_ops.probe(path)[3]


def test_cut_to_bg_accompaniment_uses_separation(client, user, sample_video):
    _, cut_id = _media_with_cut(client, user, sample_video)
    separation.set_separation_engine(FakeSeparationEngine())
    try:
        r = client.post(f"/api/cuts/{cut_id}/to-bg-audio",
                        json={"mode": "accompaniment", "name": "My bed", "user_id": user["id"]})
        assert r.status_code == 200
        wait_for(lambda: _job(client, r.json()["job_id"])["status"] == "done", timeout=60)
        asset = next(a for a in client.get("/api/audio-assets").json()
                     if a["id"] == r.json()["asset_id"])
        assert asset["name"] == "My bed" and asset["filename"]
    finally:
        separation.set_separation_engine(None)
