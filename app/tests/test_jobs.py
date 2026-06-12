"""Job-system tests: migration, claim/lease, cancel, retry, crash adoption,
and the import → prepare → transcribe → cut → export pipeline over the API."""
import shutil

from backend import jobs
from backend.db import get_db
from backend import media_ops
from backend.engines import separation
from backend.engines.fakes import FakeSeparationEngine

from .conftest import wait_for


def _job(client, jid):
    return next(j for j in client.get("/api/jobs").json() if j["id"] == jid)


def test_migration_applied(client):
    db = get_db()
    assert db.execute("PRAGMA user_version").fetchone()[0] >= 2
    cols = {r[1] for r in db.execute("PRAGMA table_info(jobs)")}
    assert {"progress", "attempts", "max_attempts", "cancel_requested",
            "worker_id", "lease_until", "target_kind", "target_id"} <= cols
    lang_cols = {r[1] for r in db.execute("PRAGMA table_info(languages)")}
    assert {"code", "name", "tts_engine", "tts_voice"} <= lang_cols
    assert db.execute("SELECT 1 FROM languages WHERE code='en'").fetchone()


def test_languages_crud(client):
    langs = client.get("/api/languages").json()
    assert any(l["code"] == "en" and l["dub_capable"] for l in langs)

    r = client.post("/api/languages", json={
        "code": "sw", "name": "Swahili", "tts_engine": "edge", "tts_voice": ""})
    assert r.status_code == 200
    assert r.json()["dub_capable"] is False

    r = client.patch("/api/languages/sw", json={"tts_voice": "sw-KE-ZuriNeural"})
    assert r.status_code == 200
    assert r.json()["dub_capable"] is True

    assert client.delete("/api/languages/sw").status_code == 200


def test_cancel_running_job(client):
    jid = jobs.enqueue("test_sleep", None, {"seconds": 30})
    wait_for(lambda: _job(client, jid)["status"] == "running")
    r = client.post(f"/api/jobs/{jid}/cancel")
    assert r.status_code == 200
    wait_for(lambda: _job(client, jid)["status"] == "cancelled")
    # finished jobs can't be cancelled again
    assert client.post(f"/api/jobs/{jid}/cancel").status_code == 409


def test_cancel_queued_then_retry(client):
    blocker = jobs.enqueue("test_sleep", None, {"seconds": 30})
    wait_for(lambda: _job(client, blocker)["status"] == "running")
    queued = jobs.enqueue("test_sleep", None, {"seconds": 0})
    assert client.post(f"/api/jobs/{queued}/cancel").json()["status"] == "cancelled"
    assert _job(client, queued)["status"] == "cancelled"

    assert client.post(f"/api/jobs/{queued}/retry").status_code == 200
    assert _job(client, queued)["status"] == "queued"
    client.post(f"/api/jobs/{blocker}/cancel")
    wait_for(lambda: _job(client, queued)["status"] == "done")


def test_expired_lease_is_adopted(client):
    """A running job whose worker died (stale lease) gets re-claimed and run."""
    db = get_db()
    cur = db.execute(
        "INSERT INTO jobs (kind, payload, status, worker_id, lease_until, attempts) "
        "VALUES ('test_sleep', '{\"seconds\": 0}', 'running', 'dead-worker', "
        "datetime('now', '-60 seconds'), 1)")
    db.commit()
    jid = cur.lastrowid
    jobs.wake()
    wait_for(lambda: _job(client, jid)["status"] == "done")
    assert _job(client, jid)["worker_id"] == jobs.WORKER_ID


def test_failed_job_retries_then_fails(client):
    def boom(ctx, payload):
        raise RuntimeError("kaput")
    jobs.HANDLERS["test_boom"] = boom
    jid = jobs.enqueue("test_boom", None, {}, max_attempts=2)
    wait_for(lambda: _job(client, jid)["status"] == "failed")
    j = _job(client, jid)
    assert j["attempts"] == 2
    assert "kaput" in j["detail"]


def test_import_prepare_transcribe_pipeline(client, user, sample_video):
    r = client.post("/api/media/import-path", json={
        "path": str(sample_video), "title": "Test clip",
        "user_id": user["id"], "whisper_model": "tiny"})
    assert r.status_code == 200
    media_id = r.json()["id"]

    wait_for(lambda: client.get(f"/api/media/{media_id}").json()["status"] == "ready")
    # the model choice rode the prepare → transcribe chain into the track name
    tracks = client.get(f"/api/media/{media_id}/tracks").json()
    assert any(t["name"] == "WhisperX (tiny)" for t in tracks)
    # the user's original file was not consumed
    assert sample_video.exists()


def test_per_job_model_override(client, user, sample_video):
    media = next(m for m in client.get("/api/media").json() if m["title"] == "Test clip")
    r = client.post(f"/api/media/{media['id']}/transcribe",
                    json={"model": "base", "language": "en"})
    assert r.status_code == 200
    wait_for(lambda: _job(client, r.json()["job_id"])["status"] == "done")
    tracks = client.get(f"/api/media/{media['id']}/tracks").json()
    assert any(t["name"] == "WhisperX (base)" for t in tracks)


def test_cut_recomposition_export(client, user):
    media = next(m for m in client.get("/api/media").json() if m["title"] == "Test clip")
    segs = client.get(f"/api/media/{media['id']}/segments").json()
    cut = client.post("/api/cuts", json={
        "media_id": media["id"], "title": "Test cut",
        "segment_ids": [segs[0]["id"]], "user_id": user["id"]}).json()
    recomp = client.post("/api/recompositions",
                         json={"title": "Test recomp", "user_id": user["id"]}).json()
    client.put(f"/api/recompositions/{recomp['id']}/cuts", json={"cut_ids": [cut["id"]]})

    r = client.post(f"/api/recompositions/{recomp['id']}/export")
    assert r.status_code == 200
    jid = r.json()["job_id"]
    j = _job(client, jid)
    assert j["target_kind"] == "recomposition" and j["target_id"] == recomp["id"]

    wait_for(lambda: _job(client, jid)["status"] == "done", timeout=60)
    files = client.get(f"/api/recompositions/{recomp['id']}/exports").json()
    assert files and files[0]["size"] > 0
    assert files[0]["filename"].endswith(".mp4")


def test_separate_cut_job_uses_cached_window(client, user, sample_video):
    db = get_db()
    cur = db.execute(
        "INSERT INTO media (title, type, filename, duration, status, added_by) "
        "VALUES ('Stem source', 'video', 'source.mp4', 2.0, 'ready', ?)",
        (user["id"],))
    media_id = cur.lastrowid
    d = media_ops.media_dir(media_id)
    shutil.copy2(sample_video, d / "source.mp4")
    track_id = db.execute(
        "INSERT INTO tracks (media_id, name) VALUES (?, 'Original')",
        (media_id,)).lastrowid
    seg_id = db.execute(
        "INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text) "
        "VALUES (?,?,?,?,?,?)",
        (media_id, track_id, 0, 0.2, 1.4, "fake transcript line")).lastrowid
    cut_id = db.execute(
        "INSERT INTO cuts (media_id, title, created_by) VALUES (?, 'Stem cut', ?)",
        (media_id, user["id"])).lastrowid
    db.execute("INSERT INTO cut_segments (cut_id, segment_id, position) VALUES (?,?,0)",
               (cut_id, seg_id))
    db.commit()

    separation.set_separation_engine(FakeSeparationEngine())
    try:
        r = client.post(f"/api/cuts/{cut_id}/separate")
        assert r.status_code == 200
        jid = r.json()["job_id"]
        wait_for(lambda: _job(client, jid)["status"] == "done", timeout=60)
        status = client.get(f"/api/cuts/{cut_id}/stems").json()
        assert status["exists"] is True
        assert status["start_s"] == 0.0
        assert status["end_s"] == 2.0

        cached = client.post(f"/api/cuts/{cut_id}/separate").json()
        assert cached["status"] == "ready"
        assert cached["cached"] is True
    finally:
        separation.set_separation_engine(None)
