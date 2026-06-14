"""P5 text overlays: ass rendering, timeline-anchored events, burn + vocals_only."""
import shutil

from backend import ass_writer, media_ops, overlay_ops
from backend.db import get_db
from backend.engines import separation
from backend.engines.fakes import FakeSeparationEngine

from .conftest import wait_for


def _job(client, jid):
    return next(j for j in client.get("/api/jobs").json() if j["id"] == jid)


def test_ass_writer_colors_and_times():
    ass = ass_writer.build_ass([{
        "name": "Cap", "style": {"primary_color": "#FFCC00", "alignment": 8},
        "events": [{"start_s": 61.5, "end_s": 63.0, "text": "líne {one}"}]}])
    assert "[V4+ Styles]" in ass and "[Events]" in ass
    assert "&H0000CCFF" in ass            # #FFCC00 → ASS BBGGRR with alpha
    assert "Dialogue: 0,0:01:01.50,0:01:03.00,ov0" in ass
    assert "(one)" in ass                 # braces sanitized so they aren't ASS tags


def _make_recomp_two_cuts(client, user):
    db = get_db()
    cur = db.execute(
        "INSERT INTO media (title, type, filename, duration, status, added_by) "
        "VALUES ('OV src', 'video', 'source.mp4', 5.0, 'ready', ?)", (user["id"],))
    media_id = cur.lastrowid
    tid = db.execute("INSERT INTO tracks (media_id, name, lang_code) VALUES (?, 'en','en')",
                     (media_id,)).lastrowid
    cut_ids = []
    spans = [(0.5, 2.0, "first line"), (3.0, 4.5, "second line")]
    for i, (a, b, txt) in enumerate(spans):
        sid = db.execute("INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text) "
                         "VALUES (?,?,?,?,?,?)", (media_id, tid, i, a, b, txt)).lastrowid
        cid = db.execute("INSERT INTO cuts (media_id, title, created_by) VALUES (?,?,?)",
                         (media_id, f"cut{i}", user["id"])).lastrowid
        db.execute("INSERT INTO cut_segments (cut_id, segment_id, position) VALUES (?,?,0)",
                   (cid, sid))
        cut_ids.append(cid)
    db.commit()
    return media_id, cut_ids


def test_gather_events_on_timeline(client, user):
    _, cut_ids = _make_recomp_two_cuts(client, user)
    recomp = client.post("/api/recompositions",
                         json={"title": "OV recomp", "user_id": user["id"]}).json()
    client.put(f"/api/recompositions/{recomp['id']}/cuts", json={"cut_ids": cut_ids})
    events = overlay_ops.gather_events(get_db(), recomp["id"], "subtitles", "")
    # cut0: dur 1.5 → event at 0.0–1.5; cut1: starts at 1.5 on the timeline
    assert len(events) == 2
    assert abs(events[0]["start_s"] - 0.0) < 1e-6 and abs(events[0]["end_s"] - 1.5) < 1e-6
    assert abs(events[1]["start_s"] - 1.5) < 1e-6 and abs(events[1]["end_s"] - 3.0) < 1e-6
    assert events[1]["text"] == "second line"


def test_overlay_crud_and_sidecar(client, user):
    _, cut_ids = _make_recomp_two_cuts(client, user)
    recomp = client.post("/api/recompositions",
                         json={"title": "OV2", "user_id": user["id"]}).json()
    client.put(f"/api/recompositions/{recomp['id']}/cuts", json={"cut_ids": cut_ids})
    ov = client.post(f"/api/recompositions/{recomp['id']}/overlays", json={
        "name": "Captions", "source": "subtitles",
        "style": {"font_size": 54, "alignment": 2}}).json()
    assert ov["enabled"] and ov["style"]["font_size"] == 54
    assert client.get(f"/api/recompositions/{recomp['id']}/overlays").json()[0]["id"] == ov["id"]
    r = client.get(f"/api/overlays/{ov['id']}.ass")
    assert r.status_code == 200 and "Dialogue:" in r.text and "first line" in r.text
    assert client.patch(f"/api/overlays/{ov['id']}", json={"enabled": False}).json()["enabled"] is False
    assert client.delete(f"/api/overlays/{ov['id']}").status_code == 200


def test_export_burns_overlay(client, user, sample_video):
    media_id, cut_ids = _make_recomp_two_cuts(client, user)
    shutil.copy2(sample_video, media_ops.media_dir(media_id) / "source.mp4")
    recomp = client.post("/api/recompositions",
                         json={"title": "OV burn", "user_id": user["id"]}).json()
    client.put(f"/api/recompositions/{recomp['id']}/cuts", json={"cut_ids": cut_ids[:1]})
    client.post(f"/api/recompositions/{recomp['id']}/overlays",
                json={"name": "Captions", "source": "subtitles"})
    r = client.post(f"/api/recompositions/{recomp['id']}/export")
    assert r.status_code == 200
    wait_for(lambda: _job(client, r.json()["job_id"])["status"] == "done", timeout=90)
    files = client.get(f"/api/recompositions/{recomp['id']}/exports").json()
    assert files and files[0]["size"] > 0
    out = media_ops.EXPORT_DIR / files[0]["filename"]
    info = media_ops.probe(out)
    assert info and info[1]  # has a video stream (overlay was burned in)


def test_export_vocals_only(client, user, sample_video):
    media_id, cut_ids = _make_recomp_two_cuts(client, user)
    shutil.copy2(sample_video, media_ops.media_dir(media_id) / "source.mp4")
    recomp = client.post("/api/recompositions",
                         json={"title": "VO", "user_id": user["id"]}).json()
    client.put(f"/api/recompositions/{recomp['id']}/cuts", json={"cut_ids": cut_ids[:1]})
    separation.set_separation_engine(FakeSeparationEngine())
    try:
        r = client.post(f"/api/recompositions/{recomp['id']}/export",
                        json={"audio_mode": "vocals_only"})
        assert r.status_code == 200
        wait_for(lambda: _job(client, r.json()["job_id"])["status"] == "done", timeout=90)
        files = client.get(f"/api/recompositions/{recomp['id']}/exports").json()
        assert files and files[0]["size"] > 0
    finally:
        separation.set_separation_engine(None)
