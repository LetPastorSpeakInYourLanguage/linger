"""Dubbing fixes: real vocal removal (no silent passthrough) and gender voices."""
import shutil
import subprocess
import wave

import numpy as np

from backend import gender, media_ops
from backend.db import get_db
from backend.engines import separation, translate, tts
from backend.engines.fakes import (
    FakeSeparationEngine, FakeTTSEngine, FakeTranslateEngine,
)
from backend.engines.separation import CenterCancelEngine, _save_wav

from .conftest import wait_for


def _job(client, jid):
    return next(j for j in client.get("/api/jobs").json() if j["id"] == jid)


class CapturingTTS(FakeTTSEngine):
    """Fake TTS that records which voice was requested for each line."""
    def __init__(self):
        self.calls = []

    def synthesize(self, text, voice, out_path, *, rate="+0%", volume="+0%"):
        self.calls.append((text, voice))
        return super().synthesize(text, voice, out_path, rate=rate, volume=volume)


def _stereo_voiceish_wav(path, sr=22050, dur=1.5, left_hz=180.0):
    """A stereo clip with a centred 'voice' tone (same in L+R) plus different
    side content, so centre-cancellation has something real to remove."""
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    centre = 0.5 * np.sin(2 * np.pi * left_hz * t)        # 'vocal', centred
    side_l = 0.3 * np.sin(2 * np.pi * 320 * t)            # 'music' L
    side_r = 0.3 * np.sin(2 * np.pi * 90 * t)             # 'music' R
    left = np.clip(centre + side_l, -1, 1)
    right = np.clip(centre + side_r, -1, 1)
    stereo = (np.stack([left, right], axis=1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(stereo.tobytes())


def _rms_of_centre(path):
    """RMS of the (L+R)/2 centre signal — where vocals live."""
    with wave.open(str(path), "rb") as w:
        ch = w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    if ch == 2:
        data = data.reshape(-1, 2)
        centre = data.mean(axis=1)
    else:
        centre = data
    return float(np.sqrt(np.mean(centre ** 2)))


def test_center_cancel_actually_removes_centre_vocals(tmp_path):
    src = tmp_path / "mix.wav"
    _stereo_voiceish_wav(src)
    out = tmp_path / "stems"
    result = CenterCancelEngine().separate_vocals(src, out)
    assert result.accompaniment.exists() and result.vocals.exists()
    # the centred 'vocal' energy must drop sharply in the accompaniment —
    # the whole point: it is NOT a passthrough of the original mix
    assert _rms_of_centre(result.accompaniment) < 0.3 * _rms_of_centre(src)


def test_save_wav_writes_valid_pcm_without_torchaudio(tmp_path):
    """The demucs stem writer must produce a valid WAV from a [C, T] array using
    only numpy + stdlib (the fix for torchaudio's missing save backend)."""
    sr = 22050
    arr = np.stack([np.sin(np.linspace(0, 6.28 * 200, sr)),       # L
                    np.sin(np.linspace(0, 6.28 * 120, sr))])      # R, shape [2, T]
    out = tmp_path / "stem.wav"
    _save_wav(arr, sr, out)
    with wave.open(str(out), "rb") as w:
        assert w.getnchannels() == 2
        assert w.getframerate() == sr
        assert w.getsampwidth() == 2
        assert w.getnframes() == sr


def test_center_cancel_refuses_mono(tmp_path):
    mono = tmp_path / "mono.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=200",
                    "-t", "1", "-ac", "1", str(mono)], capture_output=True, check=True)
    out = tmp_path / "stems"
    try:
        CenterCancelEngine().separate_vocals(mono, out)
        assert False, "mono should be refused, not silently passed through"
    except RuntimeError as e:
        assert "demucs" in str(e).lower()


def test_gender_estimate_low_vs_high_pitch(tmp_path):
    male = tmp_path / "male.wav"
    female = tmp_path / "female.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=110",
                    "-t", "1.5", "-ar", "22050", "-ac", "1", str(male)],
                   capture_output=True, check=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=230",
                    "-t", "1.5", "-ar", "22050", "-ac", "1", str(female)],
                   capture_output=True, check=True)
    assert gender.estimate_gender(male) == "M"
    assert gender.estimate_gender(female) == "F"


def _make_media_with_cut(client, user, sample_video, title, lines):
    """Insert a ready media + one cut covering `lines` [(start,end,text,gender)]."""
    db = get_db()
    media_id = db.execute(
        "INSERT INTO media (title, type, filename, duration, status, added_by) "
        "VALUES (?, 'video', 'source.mp4', 5.0, 'ready', ?)",
        (title, user["id"])).lastrowid
    shutil.copy2(sample_video, media_ops.media_dir(media_id) / "source.mp4")
    track_id = db.execute(
        "INSERT INTO tracks (media_id, name, lang_code) VALUES (?, 'English', 'en')",
        (media_id,)).lastrowid
    seg_ids = []
    for i, (start, end, text, g) in enumerate(lines):
        seg_ids.append(db.execute(
            "INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text, gender) "
            "VALUES (?,?,?,?,?,?,?)",
            (media_id, track_id, i, start, end, text, g)).lastrowid)
    cut_id = db.execute(
        "INSERT INTO cuts (media_id, title, created_by) VALUES (?, ?, ?)",
        (media_id, f"{title} cut", user["id"])).lastrowid
    for pos, sid in enumerate(seg_ids):
        db.execute("INSERT INTO cut_segments (cut_id, segment_id, position) VALUES (?,?,?)",
                   (cut_id, sid, pos))
    db.commit()
    return media_id, cut_id


def test_gendered_voices_per_segment(client, user, sample_video):
    """A male line and a female line in one cut should request different voices."""
    _, cut_id = _make_media_with_cut(client, user, sample_video, "Gendered",
                                     [(0.2, 1.0, "he speaks", "M"),
                                      (1.2, 2.0, "she speaks", "F")])
    cap = CapturingTTS()
    separation.set_separation_engine(FakeSeparationEngine())
    translate.set_translate_engine(FakeTranslateEngine())
    tts.set_tts_engine(cap)
    try:
        tr = client.post(f"/api/cuts/{cut_id}/translations", json={
            "lang_code": "es", "source": "auto", "user_id": user["id"]}).json()
        r = client.post(f"/api/translations/{tr['id']}/dub")
        wait_for(lambda: _job(client, r.json()["job_id"])["status"] == "done", timeout=60)
        voices = {v for _, v in cap.calls}
        # es male = es-ES-AlvaroNeural, female = es-ES-ElviraNeural (seeded)
        assert "es-ES-AlvaroNeural" in voices, cap.calls
        assert "es-ES-ElviraNeural" in voices, cap.calls
    finally:
        separation.set_separation_engine(None)
        translate.set_translate_engine(None)
        tts.set_tts_engine(None)


def test_dub_voice_gender_override_forces_one_voice(client, user, sample_video):
    """Forcing voice_gender='M' must use the male voice for every line, even a
    line whose speaker was detected/marked female."""
    _, cut_id = _make_media_with_cut(client, user, sample_video, "Forced",
                                     [(0.2, 1.0, "line one", "M"),
                                      (1.2, 2.0, "line two", "F")])
    cap = CapturingTTS()
    separation.set_separation_engine(FakeSeparationEngine())
    translate.set_translate_engine(FakeTranslateEngine())
    tts.set_tts_engine(cap)
    try:
        tr = client.post(f"/api/cuts/{cut_id}/translations", json={
            "lang_code": "es", "source": "auto", "user_id": user["id"]}).json()
        r = client.post(f"/api/translations/{tr['id']}/dub", json={"voice_gender": "M"})
        wait_for(lambda: _job(client, r.json()["job_id"])["status"] == "done", timeout=60)
        assert {v for _, v in cap.calls} == {"es-ES-AlvaroNeural"}, cap.calls
        dub = client.get(f"/api/cuts/{cut_id}/translations").json()["translations"][0]["dubs"][0]
        assert dub["voice_gender"] == "M"
    finally:
        separation.set_separation_engine(None)
        translate.set_translate_engine(None)
        tts.set_tts_engine(None)


def test_segment_gender_override_persists_and_drives_voice(client, user, sample_video):
    """A manual per-segment gender override is recorded and used by an auto dub."""
    _, cut_id = _make_media_with_cut(client, user, sample_video, "SegOverride",
                                     [(0.2, 1.4, "ambiguous line", None)])
    seg = client.get(f"/api/cuts/{cut_id}/translations").json()["source_segments"][0]
    upd = client.patch(f"/api/segments/{seg['id']}", json={"gender": "F"}).json()
    assert upd["gender"] == "F" and upd["gender_source"] == "manual"

    cap = CapturingTTS()
    separation.set_separation_engine(FakeSeparationEngine())
    translate.set_translate_engine(FakeTranslateEngine())
    tts.set_tts_engine(cap)
    try:
        tr = client.post(f"/api/cuts/{cut_id}/translations", json={
            "lang_code": "es", "source": "auto", "user_id": user["id"]}).json()
        r = client.post(f"/api/translations/{tr['id']}/dub")  # auto
        wait_for(lambda: _job(client, r.json()["job_id"])["status"] == "done", timeout=60)
        assert {v for _, v in cap.calls} == {"es-ES-ElviraNeural"}, cap.calls
    finally:
        separation.set_separation_engine(None)
        translate.set_translate_engine(None)
        tts.set_tts_engine(None)


def test_recomposition_dub_export_orchestrates_everything(client, user, sample_video):
    """One export call at recomposition level must translate AND dub every cut,
    even though no translations/dubs existed beforehand."""
    _, cut1 = _make_media_with_cut(client, user, sample_video, "Orch1",
                                   [(0.2, 1.2, "first line", "M")])
    _, cut2 = _make_media_with_cut(client, user, sample_video, "Orch2",
                                   [(0.2, 1.2, "second line", "F")])
    recomp = client.post("/api/recompositions",
                         json={"title": "Orchestrated", "user_id": user["id"]}).json()
    client.put(f"/api/recompositions/{recomp['id']}/cuts",
               json={"cut_ids": [cut1, cut2]})

    separation.set_separation_engine(FakeSeparationEngine())
    translate.set_translate_engine(FakeTranslateEngine())
    tts.set_tts_engine(FakeTTSEngine())
    try:
        # no translations/dubs exist yet — the export must create them
        assert client.get(f"/api/cuts/{cut1}/translations").json()["translations"] == []
        r = client.post(f"/api/recompositions/{recomp['id']}/export", json={
            "audio_mode": "dub", "target_lang": "ar",
            "keep_accompaniment": True, "keep_source_vocals": False,
            "quality": "480p", "user_id": user["id"]})
        assert r.status_code == 200, r.text
        wait_for(lambda: _job(client, r.json()["job_id"])["status"] == "done", timeout=120)

        for cid in (cut1, cut2):
            data = client.get(f"/api/cuts/{cid}/translations").json()
            assert data["translations"], f"cut {cid} got no translation"
            assert data["translations"][0]["lang_code"] == "ar"
            assert data["translations"][0]["dubs"], f"cut {cid} got no dub"
        files = client.get(f"/api/recompositions/{recomp['id']}/exports").json()
        assert files and files[0]["size"] > 0
    finally:
        separation.set_separation_engine(None)
        translate.set_translate_engine(None)
        tts.set_tts_engine(None)
