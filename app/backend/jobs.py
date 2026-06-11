"""In-process background job queue: one worker thread, jobs persisted in SQLite."""
import queue
import threading
import traceback
from pathlib import Path

from . import media_ops
from .db import get_db

_q: "queue.Queue[int]" = queue.Queue()
_started = False


def enqueue(kind: str, media_id: int) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO jobs (kind, media_id) VALUES (?, ?)", (kind, media_id))
    db.commit()
    _q.put(cur.lastrowid)
    return cur.lastrowid


def _set(job_id: int, status: str, detail: str = ""):
    db = get_db()
    db.execute(
        "UPDATE jobs SET status=?, detail=?, updated_at=datetime('now') WHERE id=?",
        (status, detail, job_id))
    db.commit()


def _set_media(media_id: int, status: str, detail: str = ""):
    db = get_db()
    db.execute("UPDATE media SET status=?, status_detail=? WHERE id=?",
               (status, detail, media_id))
    db.commit()


def _find_source(media_id: int) -> Path | None:
    d = media_ops.media_dir(media_id)
    for f in d.iterdir():
        if f.stem == "source":
            return f
    return None


def _run_transcription(job_id: int, media_id: int):
    source = _find_source(media_id)
    if source is None:
        raise RuntimeError("source media file not found")

    _set(job_id, "running", "extracting audio")
    _set_media(media_id, "extracting_audio")
    wav = media_ops.extract_wav_for_transcription(media_id, source)

    _set(job_id, "running", "loading whisper model")
    _set_media(media_id, "transcribing", "loading model")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError(
            "faster-whisper is not installed. Run: pip install faster-whisper "
            "— or upload a .srt subtitle file instead.")

    model = WhisperModel("small", device="auto", compute_type="auto")
    _set(job_id, "running", "transcribing")
    _set_media(media_id, "transcribing")
    segments_iter, _info = model.transcribe(str(wav), vad_filter=True)

    db = get_db()
    db.execute("DELETE FROM segments WHERE media_id=?", (media_id,))
    idx = 0
    for seg in segments_iter:
        text = seg.text.strip()
        if not text:
            continue
        db.execute(
            "INSERT INTO segments (media_id, idx, start_s, end_s, text) VALUES (?,?,?,?,?)",
            (media_id, idx, round(seg.start, 3), round(seg.end, 3), text))
        idx += 1
        if idx % 25 == 0:
            db.commit()
            _set(job_id, "running", f"transcribing — {idx} segments")
    db.commit()
    media_ops.safe_unlink(wav)
    if idx == 0:
        raise RuntimeError("transcription produced no segments")
    _set_media(media_id, "ready")


def _worker():
    while True:
        job_id = _q.get()
        db = get_db()
        job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if job is None:
            continue
        try:
            if job["kind"] == "transcribe":
                _run_transcription(job_id, job["media_id"])
            else:
                raise RuntimeError(f"unknown job kind {job['kind']}")
            _set(job_id, "done")
        except Exception as e:
            traceback.print_exc()
            _set(job_id, "failed", str(e)[:500])
            if job["media_id"]:
                _set_media(job["media_id"], "error", str(e)[:500])


def start_worker():
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(target=_worker, daemon=True, name="recomposer-worker")
    t.start()
    # re-queue jobs that were interrupted by a previous shutdown
    db = get_db()
    for row in db.execute(
            "SELECT id FROM jobs WHERE status IN ('queued','running') ORDER BY id"):
        _q.put(row["id"])
