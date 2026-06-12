"""Job-system tests: migration, claim/lease, cancel, retry, crash adoption,
and the import → prepare → transcribe → cut → export pipeline over the API."""
import shutil

from backend import jobs
from backend.db import get_db
from backend import media_ops
from backend.engines import separation, translate, tts
from backend.engines.fakes import (
    FakeSeparationEngine,
    FakeTTSEngine,
    FakeTranslateEngine,
)

from .conftest import wait_for


def _job(client, jid):
    return next(j for j in client.get("/api/jobs").json() if j["id"] == jid)


def test_migration_applied(client):
    db = get_db()
    assert db.execute("PRAGMA user_version").fetchone()[0] >= 3
    cols = {r[1] for r in db.execute("PRAGMA table_info(jobs)")}
    assert {"progress", "attempts", "max_attempts", "cancel_requested",
            "worker_id", "lease_until", "target_kind", "target_id"} <= cols
    track_cols = {r[1] for r in db.execute("PRAGMA table_info(tracks)")}
    assert "lang_code" in track_cols
    lang_cols = {r[1] for r in db.execute("PRAGMA table_info(languages)")}
    assert {"code", "name", "tts_engine", "tts_voice"} <= lang_cols
    assert db.execute("SELECT 1 FROM languages WHERE code='en'").fetchone()
    assert db.execute("SELECT name FROM sqlite_master WHERE name='cut_translations'").fetchone()
    rc_cols = {r[1] for r in db.execute("PRAGMA table_info(recomp_cuts)")}
    assert {"audio_mode", "dub_id"} <= rc_cols


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


def test_translate_edit_dub_select_and_export(client, user, sample_video):
    db = get_db()
    cur = db.execute(
        "INSERT INTO media (title, type, filename, duration, status, added_by) "
        "VALUES ('Dub source', 'video', 'source.mp4', 2.0, 'ready', ?)",
        (user["id"],))
    media_id = cur.lastrowid
    d = media_ops.media_dir(media_id)
    shutil.copy2(sample_video, d / "source.mp4")
    track_id = db.execute(
        "INSERT INTO tracks (media_id, name, lang_code) VALUES (?, 'English', 'en')",
        (media_id,)).lastrowid
    seg_id = db.execute(
        "INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text) "
        "VALUES (?,?,?,?,?,?)",
        (media_id, track_id, 0, 0.2, 1.4, "hello there")).lastrowid
    cut_id = db.execute(
        "INSERT INTO cuts (media_id, title, created_by) VALUES (?, 'Dub cut', ?)",
        (media_id, user["id"])).lastrowid
    db.execute("INSERT INTO cut_segments (cut_id, segment_id, position) VALUES (?,?,0)",
               (cut_id, seg_id))
    db.commit()

    separation.set_separation_engine(FakeSeparationEngine())
    translate.set_translate_engine(FakeTranslateEngine())
    tts.set_tts_engine(FakeTTSEngine())
    try:
        tr = client.post(f"/api/cuts/{cut_id}/translations", json={
            "lang_code": "es", "source": "auto", "user_id": user["id"]})
        assert tr.status_code == 200, tr.text
        translation = tr.json()
        assert translation["lang_code"] == "es"
        assert translation["segments"][0]["text"] == "[es] hello there"

        edited = client.patch(
            f"/api/translations/{translation['id']}/segments/{seg_id}",
            json={"text": "hola editada"})
        assert edited.status_code == 200
        assert edited.json()["segments"][0]["text"] == "hola editada"

        r = client.post(f"/api/translations/{translation['id']}/dub")
        assert r.status_code == 200, r.text
        dub_id = r.json()["dub"]["id"]
        jid = r.json()["job_id"]
        wait_for(lambda: _job(client, jid)["status"] == "done", timeout=60)

        data = client.get(f"/api/cuts/{cut_id}/translations").json()
        dub = data["translations"][0]["dubs"][0]
        assert dub["id"] == dub_id
        assert dub["status"] == "done"
        audio = client.get(f"/api/dubs/{dub_id}/audio")
        assert audio.status_code == 200
        assert len(audio.content) > 100

        recomp = client.post("/api/recompositions",
                             json={"title": "Dub recomp", "user_id": user["id"]}).json()
        seq = client.put(f"/api/recompositions/{recomp['id']}/cuts", json={
            "items": [{"cut_id": cut_id, "audio_mode": "dub", "dub_id": dub_id}]
        })
        assert seq.status_code == 200, seq.text
        assert seq.json()["cuts"][0]["audio_mode"] == "dub"
        assert seq.json()["cuts"][0]["dub_id"] == dub_id

        r = client.post(f"/api/recompositions/{recomp['id']}/export")
        assert r.status_code == 200, r.text
        wait_for(lambda: _job(client, r.json()["job_id"])["status"] == "done", timeout=60)
        files = client.get(f"/api/recompositions/{recomp['id']}/exports").json()
        assert files and files[0]["size"] > 0

        r = client.post(f"/api/recompositions/{recomp['id']}/export", json={
            "audio_mode": "target_dub",
            "target_lang": "es",
            "quality": "480p",
        })
        assert r.status_code == 200, r.text
        wait_for(lambda: _job(client, r.json()["job_id"])["status"] == "done", timeout=60)
        files = client.get(f"/api/recompositions/{recomp['id']}/exports").json()
        assert len(files) >= 2
        deleted = client.delete(f"/api/exports/{files[0]['filename']}")
        assert deleted.status_code == 200, deleted.text
        remaining = client.get(f"/api/recompositions/{recomp['id']}/exports").json()
        assert all(f["filename"] != files[0]["filename"] for f in remaining)
    finally:
        separation.set_separation_engine(None)
        translate.set_translate_engine(None)
        tts.set_tts_engine(None)


def test_translate_track_and_recomposition_jobs(client, user, sample_video):
    db = get_db()
    cur = db.execute(
        "INSERT INTO media (title, type, filename, duration, status, added_by) "
        "VALUES ('Translation source', 'video', 'source.mp4', 2.0, 'ready', ?)",
        (user["id"],))
    media_id = cur.lastrowid
    d = media_ops.media_dir(media_id)
    shutil.copy2(sample_video, d / "source.mp4")
    track_id = db.execute(
        "INSERT INTO tracks (media_id, name, lang_code) VALUES (?, 'English', 'en')",
        (media_id,)).lastrowid
    seg_ids = []
    for i, (start, end, text) in enumerate([
        (0.1, 0.7, "first line"),
        (0.8, 1.5, "second line"),
    ]):
        seg_ids.append(db.execute(
            "INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text) "
            "VALUES (?,?,?,?,?,?)",
            (media_id, track_id, i, start, end, text)).lastrowid)
    cut_ids = []
    for i, sid in enumerate(seg_ids):
        cut_id = db.execute(
            "INSERT INTO cuts (media_id, title, created_by) VALUES (?,?,?)",
            (media_id, f"Translate cut {i + 1}", user["id"])).lastrowid
        db.execute("INSERT INTO cut_segments (cut_id, segment_id, position) VALUES (?,?,0)",
                   (cut_id, sid))
        cut_ids.append(cut_id)
    db.commit()
    recomp = client.post("/api/recompositions",
                         json={"title": "Translate recomp", "user_id": user["id"]}).json()
    client.put(f"/api/recompositions/{recomp['id']}/cuts", json={"cut_ids": cut_ids})

    translate.set_translate_engine(FakeTranslateEngine())
    try:
        r = client.post(f"/api/tracks/{track_id}/translate", json={
            "target_lang": "es",
            "source_language": "en",
            "name": "Spanish",
        })
        assert r.status_code == 200, r.text
        wait_for(lambda: _job(client, r.json()["job_id"])["status"] == "done", timeout=30)
        tracks = client.get(f"/api/media/{media_id}/tracks").json()
        translated_track = next(t for t in tracks if t["name"] == "Spanish")
        assert translated_track["lang_code"] == "es"
        segs = client.get(
            f"/api/media/{media_id}/segments?track_id={translated_track['id']}").json()
        assert [s["text"] for s in segs] == ["[es] first line", "[es] second line"]

        r = client.post(f"/api/recompositions/{recomp['id']}/translations", json={
            "lang_code": "es",
            "source_language": "en",
            "user_id": user["id"],
        })
        assert r.status_code == 200, r.text
        wait_for(lambda: _job(client, r.json()["job_id"])["status"] == "done", timeout=30)
        for cut_id in cut_ids:
            data = client.get(f"/api/cuts/{cut_id}/translations").json()
            assert data["translations"][0]["lang_code"] == "es"
            assert data["translations"][0]["segments"][0]["text"].startswith("[es] ")
    finally:
        translate.set_translate_engine(None)
