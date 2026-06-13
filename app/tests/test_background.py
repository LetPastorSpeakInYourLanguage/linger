"""P3 background audio: timeline math, dynamic-length fitting, export mixing."""
import io
import subprocess
import wave

from backend import compose, media_ops
from backend.db import get_db

from .conftest import wait_for


def _job(client, jid):
    return next(j for j in client.get("/api/jobs").json() if j["id"] == jid)


def _wav_seconds(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def test_timeline_and_span_window():
    segs = compose.timeline([2.0, 3.0, 1.0, 4.0])
    assert [s.offset_s for s in segs] == [0.0, 2.0, 5.0, 6.0]
    # cuts 1..2 (0-indexed) → start at 2.0, duration 3.0+1.0 = 4.0
    assert compose.span_window(segs, 1, 2) == (2.0, 4.0)
    # whole thing
    assert compose.span_window(segs, 0, 3) == (0.0, 10.0)
    # clamps out-of-range
    assert compose.span_window(segs, 0, 99) == (0.0, 10.0)


def test_render_layer_fits_exact_duration(tmp_path):
    asset = tmp_path / "bed.wav"   # 1s tone — must be looped/stretched to 3s
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=200:duration=1",
                    "-ac", "2", "-ar", "44100", str(asset)], capture_output=True, check=True)
    for fit in ("loop", "stretch", "trim"):
        out = tmp_path / f"{fit}.wav"
        compose.render_layer(asset, 3.0, fit, 0.5, out)
        assert abs(_wav_seconds(out) - 3.0) < 0.15, fit


def test_asset_structure_edit_and_length_preview(client, user):
    import subprocess as sp
    proc = sp.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=2",
                   "-ac", "2", "-f", "wav", "pipe:1"], capture_output=True, check=True)
    asset = client.post("/api/audio-assets",
                        files={"file": ("bed.wav", proc.stdout, "audio/wav")},
                        data={"name": "Bed", "user_id": user["id"]}).json()
    # save a tweaking structure
    upd = client.patch(f"/api/audio-assets/{asset['id']}", json={
        "trim_start_s": 0.2, "trim_end_s": 1.8, "fade_in_s": 0.3, "fade_out_s": 0.5,
        "default_fit": "loop", "default_gain": 0.4})
    assert upd.status_code == 200
    j = upd.json()
    assert j["trim_start_s"] == 0.2 and j["default_fit"] == "loop"

    # preview at an arbitrary length → a WAV of ~that length
    r = client.get(f"/api/audio-assets/{asset['id']}/preview?length=5&fit=loop")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/")
    out = media_ops.BG_AUDIO_DIR / "previews" / f"{asset['id']}.wav"
    assert abs(_wav_seconds(out) - 5.0) < 0.2


def test_export_with_background_layer(client, user, sample_video):
    db = get_db()
    cur = db.execute(
        "INSERT INTO media (title, type, filename, duration, status, added_by) "
        "VALUES ('BG source', 'video', 'source.mp4', 2.0, 'ready', ?)", (user["id"],))
    media_id = cur.lastrowid
    import shutil
    shutil.copy2(sample_video, media_ops.media_dir(media_id) / "source.mp4")
    tid = db.execute("INSERT INTO tracks (media_id, name) VALUES (?, 'o')", (media_id,)).lastrowid
    sid = db.execute("INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text) "
                     "VALUES (?,?,0,0.2,1.6,'hi')", (media_id, tid)).lastrowid
    db.commit()
    cut = client.post("/api/cuts", json={"media_id": media_id, "title": "bg cut",
                                         "segment_ids": [sid], "user_id": user["id"]}).json()
    recomp = client.post("/api/recompositions",
                         json={"title": "BG recomp", "user_id": user["id"]}).json()
    client.put(f"/api/recompositions/{recomp['id']}/cuts", json={"cut_ids": [cut["id"]]})

    # upload a bed and assign it as a layer over the whole recomposition
    bed = io.BytesIO()
    proc = subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=330:duration=1",
                           "-ac", "2", "-f", "wav", "pipe:1"], capture_output=True, check=True)
    bed.write(proc.stdout)
    asset = client.post("/api/audio-assets",
                        files={"file": ("bed.wav", proc.stdout, "audio/wav")},
                        data={"name": "Bed", "user_id": user["id"]}).json()
    assert asset["id"]

    r = client.put(f"/api/recompositions/{recomp['id']}/audio-layers", json={
        "layers": [{"asset_id": asset["id"], "from_pos": 0, "to_pos": 0,
                    "gain": 0.4, "fit": "loop"}]})
    assert r.status_code == 200
    assert r.json()[0]["fit"] == "loop"

    r = client.post(f"/api/recompositions/{recomp['id']}/export")
    assert r.status_code == 200
    wait_for(lambda: _job(client, r.json()["job_id"])["status"] == "done", timeout=60)
    files = client.get(f"/api/recompositions/{recomp['id']}/exports").json()
    assert files and files[0]["size"] > 0
    # the exported mp4 must carry an audio stream (the mixed bg)
    out = media_ops.EXPORT_DIR / files[0]["filename"]
    info = media_ops.probe(out)
    assert info and info[3], "exported file should have an audio stream"
