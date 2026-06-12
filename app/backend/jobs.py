"""Background job queue: jobs persisted in SQLite, claimed by a worker loop.

Jobs are claimed with a lease (worker_id + lease_until) via an optimistic
UPDATE, so any number of workers — the in-process thread today, remote
executors later — can share one queue safely. A job whose lease expires
(crashed worker) becomes claimable again. Handlers register with @handler
and receive a JobContext for progress reporting + cooperative cancellation.

Job kinds:
  download    {"url", "then_transcribe", "whisper"?}              — yt-dlp fetch
  prepare     {"src", "keep_src", "then_transcribe", "whisper"?}  — ffmpeg remux/re-encode
  transcribe  {"model"?, "language"?, "device"?, "compute"?}      — whisperx / faster-whisper
  export      {"recomp_id"}                                       — render recomposition
Jobs chain: download → prepare → (transcribe if no subtitles were provided);
the optional "whisper" dict ({"model": ...}) rides along the chain.
"""
import json
import os
import socket
import threading
import traceback
from pathlib import Path

from . import media_ops
from .db import get_db

_wake = threading.Event()
_started = False

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
LEASE_SECONDS = 180          # a running job must report/heartbeat within this
POLL_SECONDS = 3.0           # fallback poll when the wake event is missed

HANDLERS: dict = {}


class JobCancelled(Exception):
    """Raised inside a handler when the user requested cancellation."""


def handler(kind: str):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn
    return deco


def log(msg: str):
    print(f"  [recomposer] {msg}", flush=True)


def wake():
    _wake.set()


def enqueue(kind: str, media_id: int | None = None, payload: dict | None = None, *,
            priority: int = 0, target_kind: str | None = None,
            target_id: int | None = None, max_attempts: int = 2) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO jobs (kind, media_id, payload, priority, target_kind, target_id, max_attempts) "
        "VALUES (?,?,?,?,?,?,?)",
        (kind, media_id, json.dumps(payload or {}), priority, target_kind,
         target_id, max_attempts))
    db.commit()
    wake()
    return cur.lastrowid


class JobContext:
    """Handed to every handler: progress reporting (which also keeps the
    lease alive) and cooperative cancellation."""

    def __init__(self, job):
        self.job_id = job["id"]
        self.media_id = job["media_id"]
        self.kind = job["kind"]

    def report(self, detail: str = "", progress: float | None = None):
        db = get_db()
        if progress is None:
            db.execute(
                "UPDATE jobs SET detail=?, updated_at=datetime('now'), "
                "lease_until=datetime('now', ?) WHERE id=?",
                (detail, f"+{LEASE_SECONDS} seconds", self.job_id))
        else:
            db.execute(
                "UPDATE jobs SET detail=?, progress=?, updated_at=datetime('now'), "
                "lease_until=datetime('now', ?) WHERE id=?",
                (detail, round(min(100.0, progress), 1),
                 f"+{LEASE_SECONDS} seconds", self.job_id))
        db.commit()

    def heartbeat(self):
        db = get_db()
        db.execute("UPDATE jobs SET lease_until=datetime('now', ?) WHERE id=?",
                   (f"+{LEASE_SECONDS} seconds", self.job_id))
        db.commit()

    def cancelled(self) -> bool:
        row = get_db().execute("SELECT cancel_requested FROM jobs WHERE id=?",
                               (self.job_id,)).fetchone()
        return bool(row and row["cancel_requested"])

    def check_cancel(self):
        if self.cancelled():
            raise JobCancelled()


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


def _restore_media_after_stop(media_id: int):
    """After a cancel: the media is fine if it's already playable, otherwise
    it never got a streamable file and is effectively dead."""
    db = get_db()
    row = db.execute("SELECT filename FROM media WHERE id=?", (media_id,)).fetchone()
    if row is None:
        return
    if row["filename"]:
        _set_media(media_id, "ready", "")
    else:
        _set_media(media_id, "error", "cancelled before the file was ready")


# ------------------------------------------------------------- download

@handler("download")
def _run_download(ctx: JobContext, payload: dict):
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError("yt-dlp is not installed. Run: pip install yt-dlp")

    media_id = ctx.media_id
    title = _media_title(media_id)
    url = payload["url"]
    dest = media_ops.media_dir(media_id)
    log(f"downloading '{title}': {url}")
    _set_media(media_id, "downloading")

    last = [-10.0]

    def hook(d):
        ctx.check_cancel()  # raising aborts the yt-dlp download
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                pct = d.get("downloaded_bytes", 0) / total * 100
                if pct - last[0] >= 2:
                    last[0] = pct
                    msg = f"downloading {pct:.0f}%"
                    ctx.report(msg, progress=pct)
                    _set_media(media_id, "downloading", msg)
                    log(f"'{title}' {msg}")
        elif d.get("status") == "finished":
            ctx.heartbeat()  # merging can take a while with no hook calls
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
        "whisper": payload.get("whisper") or {},
    })


# -------------------------------------------------------------- prepare

@handler("prepare")
def _run_prepare(ctx: JobContext, payload: dict):
    media_id = ctx.media_id
    src = Path(payload["src"])
    if not src.exists():
        raise RuntimeError(f"source file not found: {src}")
    title = _media_title(media_id)
    _set_media(media_id, "preparing")
    log(f"preparing '{title}' ({src.name})")

    def on_progress(pct):
        msg = f"converting {pct:.0f}%"
        ctx.report(msg, progress=pct)
        _set_media(media_id, "preparing", msg)
        log(f"'{title}' {msg}")

    final, mtype, duration, mode = media_ops.prepare_for_streaming(
        src, media_id, keep_src=payload.get("keep_src", False),
        on_progress=on_progress, check_cancel=ctx.check_cancel)

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
        enqueue("transcribe", media_id, payload.get("whisper") or {})
    else:
        _set_media(media_id, "ready")


# ----------------------------------------------------------- transcribe

def _replace_track(db, media_id: int, track_name: str) -> int:
    """Transcriptions live in their own track; re-running replaces only it."""
    row = db.execute("SELECT id FROM tracks WHERE media_id=? AND name=?",
                     (media_id, track_name)).fetchone()
    if row:
        db.execute("DELETE FROM segments WHERE track_id=?", (row["id"],))
        return row["id"]
    return db.execute("INSERT INTO tracks (media_id, name) VALUES (?,?)",
                      (media_id, track_name)).lastrowid


def _whisper_settings():
    """Env config: RECOMPOSER_WHISPER_MODEL / _DEVICE / _COMPUTE."""
    return (os.environ.get("RECOMPOSER_WHISPER_MODEL", "small"),
            os.environ.get("RECOMPOSER_WHISPER_DEVICE", "auto"),
            os.environ.get("RECOMPOSER_WHISPER_COMPUTE", "auto"))


@handler("transcribe")
def _run_transcription(ctx: JobContext, payload: dict):
    media_id = ctx.media_id
    source = _find_source(media_id)
    if source is None:
        raise RuntimeError("source media file not found")
    title = _media_title(media_id)

    def stage(msg, pct=None):
        ctx.report(msg, progress=pct)
        _set_media(media_id, "transcribing", msg)
        log(f"transcribing '{title}': {msg}")

    # per-job settings win over env defaults
    model_name, device, compute = _whisper_settings()
    model_name = (payload.get("model") or "").strip() or model_name
    device = (payload.get("device") or "").strip() or device
    compute = (payload.get("compute") or "").strip() or compute
    language = (payload.get("language") or "").strip() or None

    stage("extracting audio", 2)
    wav = media_ops.extract_wav_for_transcription(media_id, source,
                                                  check_cancel=ctx.check_cancel)

    engine = None
    try:
        import whisperx  # noqa: F401
        engine = "whisperx"
    except ImportError:
        try:
            from faster_whisper import WhisperModel  # noqa: F401
            engine = "faster-whisper"
        except ImportError:
            raise RuntimeError(
                "no transcription engine installed. Run: pip install whisperx "
                "(recommended, accurate timestamps) or pip install faster-whisper "
                "— or upload a .srt subtitle file instead.")

    try:
        ctx.check_cancel()
        if engine == "whisperx":
            idx = _transcribe_whisperx(ctx, media_id, wav, model_name, device,
                                       compute, language, stage)
        else:
            idx = _transcribe_faster(ctx, media_id, wav, model_name, device,
                                     compute, language, stage)
    finally:
        media_ops.safe_unlink(wav)
    if idx == 0:
        raise RuntimeError("transcription produced no segments")
    _set_media(media_id, "ready")
    log(f"'{title}' transcription done ({engine}): {idx} segments")


def _transcribe_whisperx(ctx, media_id, wav, model_name, device, compute,
                         language, stage):
    """WhisperX: batched whisper + wav2vec2 forced alignment → precise timestamps."""
    import whisperx
    import torch

    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if compute == "auto":
        compute = "float16" if device == "cuda" else "int8"

    stage(f"loading whisperx model '{model_name}' ({device}) — first run downloads it", 5)
    model = whisperx.load_model(model_name, device, compute_type=compute,
                                language=language)
    audio = whisperx.load_audio(str(wav))

    ctx.check_cancel()
    stage("transcribing (whisperx)…", 25)
    result = model.transcribe(audio, batch_size=16 if device == "cuda" else 8)
    segs = result["segments"]

    ctx.check_cancel()
    stage("aligning timestamps (wav2vec2)…", 70)
    try:
        align_model, meta = whisperx.load_align_model(
            language_code=result["language"], device=device)
        segs = whisperx.align(segs, align_model, meta, audio, device,
                              return_char_alignments=False)["segments"]
    except Exception as e:  # no align model for this language etc.
        log(f"alignment unavailable ({e}); keeping whisper timestamps")

    stage("saving segments", 95)
    db = get_db()
    track_id = _replace_track(db, media_id, f"WhisperX ({model_name})")
    idx = 0
    for s in segs:
        text = (s.get("text") or "").strip()
        if not text or s.get("start") is None or s.get("end") is None:
            continue
        db.execute(
            "INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text) VALUES (?,?,?,?,?,?)",
            (media_id, track_id, idx, round(float(s["start"]), 3),
             round(float(s["end"]), 3), text))
        idx += 1
    db.commit()
    return idx


def _transcribe_faster(ctx, media_id, wav, model_name, device, compute,
                       language, stage):
    """Fallback engine: faster-whisper with streaming progress."""
    from faster_whisper import WhisperModel

    stage(f"loading whisper model '{model_name}' — first run downloads it", 5)
    model = WhisperModel(model_name, device=device, compute_type=compute)
    segments_iter, info = model.transcribe(str(wav), vad_filter=True,
                                           language=language)
    duration = getattr(info, "duration", None)

    db = get_db()
    track_id = _replace_track(db, media_id, f"Whisper ({model_name})")
    idx = 0
    last = -10.0
    for seg in segments_iter:
        ctx.check_cancel()
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
                stage(f"transcribing {pct:.0f}% ({idx} segments)", pct)
        elif idx % 25 == 0:
            db.commit()
            ctx.report(f"transcribing — {idx} segments")
    db.commit()
    return idx


# --------------------------------------------------------------- export

@handler("export")
def _run_export(ctx: JobContext, payload: dict):
    recomp_id = payload["recomp_id"]
    db = get_db()
    recomp = db.execute("SELECT * FROM recompositions WHERE id=?", (recomp_id,)).fetchone()
    if not recomp:
        raise RuntimeError("recomposition not found")
    rows = db.execute("""
        SELECT c.id AS cut_id, m.id AS media_id, m.filename, m.type,
               MIN(s.start_s) AS start_s, MAX(s.end_s) AS end_s
        FROM recomp_cuts rc
        JOIN cuts c ON c.id = rc.cut_id
        JOIN media m ON m.id = c.media_id
        JOIN cut_segments cs ON cs.cut_id = c.id
        JOIN segments s ON s.id = cs.segment_id
        WHERE rc.recomp_id=?
        GROUP BY rc.position, c.id, m.id, m.filename, m.type
        ORDER BY rc.position""", (recomp_id,)).fetchall()
    if not rows:
        raise RuntimeError("this recomposition has no cuts")

    cuts = []
    for r in rows:
        src = media_ops.media_dir(r["media_id"]) / r["filename"]
        if not src.exists():
            raise RuntimeError(f"source file missing for media {r['media_id']}")
        cuts.append({"src": str(src), "start_s": r["start_s"], "end_s": r["end_s"],
                     "is_video": r["type"] == "video"})

    title = recomp["title"]
    log(f"export '{title}': {len(cuts)} cuts")

    def prog(msg, pct=None):
        ctx.report(msg, progress=pct)
        log(f"export '{title}': {msg}")

    final = media_ops.export_recomposition(recomp_id, title, cuts, on_progress=prog,
                                           check_cancel=ctx.check_cancel)
    log(f"export '{title}' done → {final}")
    ctx.report(f"done: {final.name}", progress=100)


# ----------------------------------------------------- cancel & retry API

def request_cancel(job_id: int) -> dict:
    """Queued jobs are cancelled instantly; running jobs get cancel_requested
    and stop at their next check_cancel()."""
    db = get_db()
    row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        return {"error": "job not found"}
    if row["status"] in ("done", "failed", "cancelled"):
        return {"error": f"job is already {row['status']}"}
    # atomic, so we can't race the claim loop: only one of us gets the row
    cur = db.execute(
        "UPDATE jobs SET status='cancelled', detail='cancelled by user', "
        "finished_at=datetime('now'), updated_at=datetime('now') "
        "WHERE id=? AND status='queued'", (job_id,))
    db.commit()
    if cur.rowcount:
        if row["media_id"]:
            _restore_media_after_stop(row["media_id"])
        return {"status": "cancelled"}
    db.execute("UPDATE jobs SET cancel_requested=1, updated_at=datetime('now') WHERE id=?",
               (job_id,))
    db.commit()
    return {"status": "cancelling"}


_RETRY_MEDIA_STATUS = {"download": "downloading", "prepare": "preparing",
                       "transcribe": "queued_transcription"}


def retry(job_id: int) -> dict:
    db = get_db()
    row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        return {"error": "job not found"}
    if row["status"] not in ("failed", "cancelled"):
        return {"error": "only failed or cancelled jobs can be retried"}
    db.execute(
        "UPDATE jobs SET status='queued', attempts=0, cancel_requested=0, "
        "worker_id=NULL, lease_until=NULL, finished_at=NULL, progress=NULL, "
        "detail='requeued', updated_at=datetime('now') WHERE id=?", (job_id,))
    db.commit()
    if row["media_id"] and row["kind"] in _RETRY_MEDIA_STATUS:
        _set_media(row["media_id"], _RETRY_MEDIA_STATUS[row["kind"]], "requeued")
    wake()
    return {"status": "queued"}


# --------------------------------------------------------------- worker

def _claim_next():
    """Claim the next runnable job with an optimistic UPDATE. Also adopts
    running jobs whose lease expired (their worker died)."""
    db = get_db()
    for _ in range(10):
        row = db.execute("""
            SELECT id FROM jobs
            WHERE (status='queued' AND cancel_requested=0)
               OR (status='running' AND lease_until IS NOT NULL
                   AND lease_until < datetime('now'))
            ORDER BY priority DESC, id LIMIT 1""").fetchone()
        if row is None:
            return None
        cur = db.execute("""
            UPDATE jobs SET status='running', worker_id=?,
                   lease_until=datetime('now', ?),
                   started_at=COALESCE(started_at, datetime('now')),
                   attempts=attempts+1, updated_at=datetime('now')
            WHERE id=? AND ((status='queued' AND cancel_requested=0)
                OR (status='running' AND lease_until < datetime('now')))""",
            (WORKER_ID, f"+{LEASE_SECONDS} seconds", row["id"]))
        db.commit()
        if cur.rowcount:
            return db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()
    return None


def _finish(job_id: int, status: str, detail: str | None = None):
    db = get_db()
    if detail is None:  # keep the handler's last detail (e.g. "done: file.mp4")
        db.execute("UPDATE jobs SET status=?, finished_at=datetime('now'), "
                   "updated_at=datetime('now') WHERE id=?", (status, job_id))
    else:
        db.execute("UPDATE jobs SET status=?, detail=?, finished_at=datetime('now'), "
                   "updated_at=datetime('now') WHERE id=?", (status, detail, job_id))
    db.commit()


def _execute(job):
    job_id = job["id"]
    payload = json.loads(job["payload"] or "{}")
    ctx = JobContext(job)
    try:
        fn = HANDLERS.get(job["kind"])
        if fn is None:
            raise RuntimeError(f"unknown job kind {job['kind']}")
        ctx.check_cancel()
        fn(ctx, payload)
        db = get_db()
        db.execute("UPDATE jobs SET status='done', progress=100, "
                   "finished_at=datetime('now'), updated_at=datetime('now') WHERE id=?",
                   (job_id,))
        db.commit()
    except JobCancelled:
        log(f"job {job_id} ({job['kind']}) cancelled")
        _finish(job_id, "cancelled", "cancelled by user")
        if job["media_id"]:
            _restore_media_after_stop(job["media_id"])
    except Exception as e:
        traceback.print_exc()
        row = get_db().execute("SELECT attempts, max_attempts FROM jobs WHERE id=?",
                               (job_id,)).fetchone()
        if row and row["attempts"] < row["max_attempts"]:
            log(f"JOB ERROR ({job['kind']}), will retry: {e}")
            db = get_db()
            db.execute(
                "UPDATE jobs SET status='queued', worker_id=NULL, lease_until=NULL, "
                "detail=?, updated_at=datetime('now') WHERE id=?",
                (f"retrying after error: {str(e)[:400]}", job_id))
            db.commit()
            wake()
        else:
            log(f"JOB FAILED ({job['kind']}): {e}")
            _finish(job_id, "failed", str(e)[:500])
            if job["media_id"]:
                _set_media(job["media_id"], "error", str(e)[:500])


def _worker():
    while True:
        job = _claim_next()
        if job is None:
            _wake.wait(timeout=POLL_SECONDS)
            _wake.clear()
            continue
        _execute(job)


def start_worker():
    global _started
    if _started:
        return
    _started = True
    db = get_db()
    # jobs that kept getting interrupted are dead; everything else re-runs
    db.execute("UPDATE jobs SET status='failed', detail='interrupted too many times', "
               "finished_at=datetime('now') WHERE status IN ('queued','running') "
               "AND attempts >= max_attempts + 2")
    db.execute("UPDATE jobs SET status='queued', worker_id=NULL, lease_until=NULL "
               "WHERE status='running'")
    db.commit()
    t = threading.Thread(target=_worker, daemon=True, name="recomposer-worker")
    t.start()
    wake()
