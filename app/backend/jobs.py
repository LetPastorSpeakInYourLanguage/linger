"""In-process background job queue: one worker thread, jobs persisted in SQLite.

Job kinds:
  download    payload: {"url", "then_transcribe"}       — yt-dlp fetch into media dir
  prepare     payload: {"src", "keep_src", "then_transcribe"} — ffmpeg remux/re-encode
  transcribe  payload: {}                                — faster-whisper
Jobs chain: download → prepare → (transcribe if no subtitles were provided).
"""
import json
import os
import queue
import threading
import traceback
from pathlib import Path

from . import media_ops
from .db import get_db

_q: "queue.Queue[int]" = queue.Queue()
_started = False


def log(msg: str):
    print(f"  [recomposer] {msg}", flush=True)


def enqueue(kind: str, media_id: int, payload: dict | None = None) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO jobs (kind, media_id, payload) VALUES (?, ?, ?)",
        (kind, media_id, json.dumps(payload or {})))
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


def _media_title(media_id: int) -> str:
    row = get_db().execute("SELECT title FROM media WHERE id=?", (media_id,)).fetchone()
    return row["title"] if row else f"media {media_id}"


def _find_source(media_id: int) -> Path | None:
    d = media_ops.media_dir(media_id)
    for f in d.iterdir():
        if f.stem == "source":
            return f
    return None


# ------------------------------------------------------------- download

def _run_download(job_id: int, media_id: int, payload: dict):
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError("yt-dlp is not installed. Run: pip install yt-dlp")

    title = _media_title(media_id)
    url = payload["url"]
    dest = media_ops.media_dir(media_id)
    log(f"downloading '{title}': {url}")
    _set_media(media_id, "downloading")

    last = [-10.0]

    def hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                pct = d.get("downloaded_bytes", 0) / total * 100
                if pct - last[0] >= 2:
                    last[0] = pct
                    msg = f"downloading {pct:.0f}%"
                    _set(job_id, "running", msg)
                    _set_media(media_id, "downloading", msg)
                    log(f"'{title}' {msg}")
        elif d.get("status") == "finished":
            log(f"'{title}' download finished, merging…")

    opts = {
        # prefer h264 mp4 so the prepare step is a fast remux, not a re-encode
        "format": "bv*[ext=mp4][vcodec^=avc1]+ba[ext=m4a]/b[ext=mp4]/bestvideo+bestaudio/best",
        "outtmpl": str(dest / "raw.%(ext)s"),
        "progress_hooks": [hook],
        "noplaylist": True,
        "quiet": True, "no_warnings": True,
        "merge_output_format": "mp4",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # if the user didn't give a title, use the video's own
    db = get_db()
    row = db.execute("SELECT title FROM media WHERE id=?", (media_id,)).fetchone()
    if row and row["title"].startswith("Link import") and info.get("title"):
        db.execute("UPDATE media SET title=? WHERE id=?", (info["title"], media_id))
        db.commit()

    raw = next((f for f in dest.iterdir() if f.stem == "raw"), None)
    if raw is None:
        raise RuntimeError("download produced no file")

    enqueue("prepare", media_id, {
        "src": str(raw), "keep_src": False,
        "then_transcribe": payload.get("then_transcribe", True),
    })


# -------------------------------------------------------------- prepare

def _run_prepare(job_id: int, media_id: int, payload: dict):
    src = Path(payload["src"])
    if not src.exists():
        raise RuntimeError(f"source file not found: {src}")
    title = _media_title(media_id)
    _set_media(media_id, "preparing")
    log(f"preparing '{title}' ({src.name})")

    def on_progress(pct):
        msg = f"converting {pct:.0f}%"
        _set(job_id, "running", msg)
        _set_media(media_id, "preparing", msg)
        log(f"'{title}' {msg}")

    final, mtype, duration, mode = media_ops.prepare_for_streaming(
        src, media_id, keep_src=payload.get("keep_src", False),
        on_progress=on_progress)

    db = get_db()
    db.execute("UPDATE media SET type=?, filename=?, duration=? WHERE id=?",
               (mtype, final.name, duration, media_id))
    db.commit()
    log(f"'{title}' prepared ({mode}, {mtype})")

    has_segments = db.execute(
        "SELECT 1 FROM segments WHERE media_id=? LIMIT 1", (media_id,)).fetchone()
    if has_segments:
        _set_media(media_id, "ready")
    elif payload.get("then_transcribe"):
        _set_media(media_id, "queued_transcription")
        enqueue("transcribe", media_id)
    else:
        _set_media(media_id, "ready")


# ----------------------------------------------------------- transcribe

def _run_transcription(job_id: int, media_id: int):
    source = _find_source(media_id)
    if source is None:
        raise RuntimeError("source media file not found")
    title = _media_title(media_id)

    _set(job_id, "running", "extracting audio")
    _set_media(media_id, "transcribing", "extracting audio")
    log(f"transcribing '{title}': extracting audio")
    wav = media_ops.extract_wav_for_transcription(media_id, source)

    _set(job_id, "running", "loading whisper model")
    _set_media(media_id, "transcribing", "loading model")
    log(f"transcribing '{title}': loading whisper model (first run downloads it)")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError(
            "faster-whisper is not installed. Run: pip install faster-whisper "
            "— or upload a .srt subtitle file instead.")

    # configurable via env: tiny/base/small/medium/large-v3 (bigger = better + slower)
    model_name = os.environ.get("RECOMPOSER_WHISPER_MODEL", "small")
    device = os.environ.get("RECOMPOSER_WHISPER_DEVICE", "auto")
    compute = os.environ.get("RECOMPOSER_WHISPER_COMPUTE", "auto")
    log(f"whisper model={model_name} device={device}")
    model = WhisperModel(model_name, device=device, compute_type=compute)
    segments_iter, info = model.transcribe(str(wav), vad_filter=True)
    duration = getattr(info, "duration", None)

    # transcription lives in its own track; re-running replaces only that track
    db = get_db()
    track_name = f"Whisper ({model_name})"
    row = db.execute("SELECT id FROM tracks WHERE media_id=? AND name=?",
                     (media_id, track_name)).fetchone()
    if row:
        track_id = row["id"]
        db.execute("DELETE FROM segments WHERE track_id=?", (track_id,))
    else:
        track_id = db.execute("INSERT INTO tracks (media_id, name) VALUES (?,?)",
                              (media_id, track_name)).lastrowid
    idx = 0
    last = -10.0
    for seg in segments_iter:
        text = seg.text.strip()
        if not text:
            continue
        db.execute(
            "INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text) VALUES (?,?,?,?,?,?)",
            (media_id, track_id, idx, round(seg.start, 3), round(seg.end, 3), text))
        idx += 1
        if duration:
            pct = min(99, seg.end / duration * 100)
            if pct - last >= 2:
                last = pct
                db.commit()
                msg = f"transcribing {pct:.0f}% ({idx} segments)"
                _set(job_id, "running", msg)
                _set_media(media_id, "transcribing", msg)
                log(f"'{title}' {msg}")
        elif idx % 25 == 0:
            db.commit()
            _set(job_id, "running", f"transcribing — {idx} segments")
    db.commit()
    media_ops.safe_unlink(wav)
    if idx == 0:
        raise RuntimeError("transcription produced no segments")
    _set_media(media_id, "ready")
    log(f"'{title}' transcription done: {idx} segments")


# --------------------------------------------------------------- worker

def _worker():
    while True:
        job_id = _q.get()
        db = get_db()
        job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if job is None:
            continue
        payload = json.loads(job["payload"] or "{}")
        try:
            if job["kind"] == "download":
                _run_download(job_id, job["media_id"], payload)
            elif job["kind"] == "prepare":
                _run_prepare(job_id, job["media_id"], payload)
            elif job["kind"] == "transcribe":
                _run_transcription(job_id, job["media_id"])
            else:
                raise RuntimeError(f"unknown job kind {job['kind']}")
            _set(job_id, "done")
        except Exception as e:
            traceback.print_exc()
            log(f"JOB FAILED ({job['kind']}): {e}")
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
