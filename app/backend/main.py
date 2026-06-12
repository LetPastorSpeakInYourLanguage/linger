"""Recomposer — single-process FastAPI app: API + media streaming + frontend."""
import mimetypes
import os
import re
import shutil
import sqlite3
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import jobs, media_ops, quiet_logs, search, translation_ops
from .db import get_db, init_db, rows_to_dicts
from .srt_parser import parse_subtitles

app = FastAPI(title="Recomposer")

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@app.on_event("startup")
def _startup():
    quiet_logs.install()
    init_db()
    jobs.start_worker()


# ---------------------------------------------------------------- users

class UserIn(BaseModel):
    name: str
    color: str = "#6366f1"


@app.get("/api/users")
def list_users():
    return rows_to_dicts(get_db().execute("SELECT * FROM users ORDER BY name"))


@app.post("/api/users")
def create_user(u: UserIn):
    db = get_db()
    name = u.name.strip()
    if not name:
        raise HTTPException(400, "name required")
    row = db.execute("SELECT * FROM users WHERE name=?", (name,)).fetchone()
    if row:
        return dict(row)
    cur = db.execute("INSERT INTO users (name, color) VALUES (?,?)", (name, u.color))
    db.commit()
    return {"id": cur.lastrowid, "name": name, "color": u.color}


# ---------------------------------------------------------------- media

@app.get("/api/media")
def list_media():
    db = get_db()
    rows = db.execute("""
        SELECT m.*, u.name AS added_by_name,
               (SELECT COUNT(*) FROM segments s WHERE s.media_id = m.id) AS segment_count,
               (SELECT COUNT(*) FROM cuts c WHERE c.media_id = m.id) AS cut_count
        FROM media m LEFT JOIN users u ON u.id = m.added_by
        ORDER BY m.id DESC""").fetchall()
    return rows_to_dicts(rows)


def _insert_subtitles(db, media_id: int, raw: str, track_name: str = "Subtitles",
                      lang_code: str = "") -> bool:
    """Parse subtitle text into a NEW track. Returns True if segments were created."""
    segs = parse_subtitles(raw)
    if not segs:
        return False
    cur = db.execute("INSERT INTO tracks (media_id, name, lang_code) VALUES (?,?,?)",
                     (media_id, track_name, lang_code))
    track_id = cur.lastrowid
    for i, s in enumerate(segs):
        db.execute(
            "INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text) "
            "VALUES (?,?,?,?,?,?)",
            (media_id, track_id, i, s["start_s"], s["end_s"], s["text"]))
    return True


def _reindex_track(db, track_id: int):
    """Renumber idx by start time after inserts/deletes/timing edits."""
    rows = db.execute(
        "SELECT id FROM segments WHERE track_id=? ORDER BY start_s, id",
        (track_id,)).fetchall()
    for i, r in enumerate(rows):
        db.execute("UPDATE segments SET idx=? WHERE id=? AND idx<>?", (i, r["id"], i))


def _drop_empty_cuts(db) -> int:
    """Delete cuts whose segments were all removed. Returns how many."""
    rows = db.execute("""SELECT id FROM cuts WHERE id NOT IN
                         (SELECT DISTINCT cut_id FROM cut_segments)""").fetchall()
    for r in rows:
        db.execute("DELETE FROM cuts WHERE id=?", (r["id"],))
    return len(rows)


def _cuts_using_segments(db, seg_ids: list[int]) -> int:
    if not seg_ids:
        return 0
    return db.execute(
        f"SELECT COUNT(DISTINCT cut_id) AS n FROM cut_segments "
        f"WHERE segment_id IN ({','.join('?' * len(seg_ids))})",
        seg_ids).fetchone()["n"]


@app.post("/api/media")
async def upload_media(
    file: UploadFile = File(...),
    subtitle: UploadFile | None = File(None),
    title: str = Form(""),
    user_id: int = Form(...),
    whisper_model: str = Form(""),
    subtitle_language: str = Form(""),
):
    """Browser upload: save the raw bytes, return immediately; ffmpeg runs in background."""
    db = get_db()
    title = title.strip() or Path(file.filename or "untitled").stem
    cur = db.execute(
        "INSERT INTO media (title, type, filename, status, added_by) VALUES (?,?,?,?,?)",
        (title, "video", "", "preparing", user_id))
    media_id = cur.lastrowid
    db.commit()

    suffix = Path(file.filename or "upload.bin").suffix or ".bin"
    raw_path = media_ops.media_dir(media_id) / ("raw" + suffix.lower())
    try:
        with raw_path.open("wb") as out:
            shutil.copyfileobj(file.file, out, length=1024 * 1024)
    except Exception as e:
        db.execute("DELETE FROM media WHERE id=?", (media_id,))
        db.commit()
        media_ops.safe_unlink(raw_path)
        raise HTTPException(400, f"could not save upload: {e}")

    has_subs = False
    if subtitle is not None and subtitle.filename:
        text = (await subtitle.read()).decode("utf-8", errors="replace")
        has_subs = _insert_subtitles(db, media_id, text,
                                     Path(subtitle.filename).stem or "Subtitles",
                                     _norm_lang_code_or_empty(subtitle_language))
        if not has_subs:
            db.execute("UPDATE media SET status_detail=? WHERE id=?",
                       ("subtitle file could not be parsed — will auto-transcribe", media_id))
        db.commit()

    jobs.enqueue("prepare", media_id,
                 {"src": str(raw_path), "keep_src": False,
                  "then_transcribe": not has_subs,
                  "whisper": _whisper_payload(whisper_model)})
    row = db.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
    return dict(row)


def _whisper_payload(model: str) -> dict:
    model = (model or "").strip()
    return {"model": model} if model else {}


class PathImport(BaseModel):
    path: str
    subtitle_path: str | None = None
    title: str = ""
    user_id: int
    whisper_model: str = ""
    subtitle_language: str = ""


@app.post("/api/media/import-path")
def import_path(body: PathImport):
    """Import a file already on the host machine — no HTTP copy, ffmpeg reads it directly."""
    src = Path(body.path.strip().strip('"'))
    if not src.is_file():
        raise HTTPException(400, f"file not found on the host: {src}")
    db = get_db()
    title = body.title.strip() or src.stem
    cur = db.execute(
        "INSERT INTO media (title, type, filename, status, added_by) VALUES (?,?,?,?,?)",
        (title, "video", "", "preparing", body.user_id))
    media_id = cur.lastrowid

    has_subs = False
    if body.subtitle_path:
        sub = Path(body.subtitle_path.strip().strip('"'))
        if not sub.is_file():
            db.execute("DELETE FROM media WHERE id=?", (media_id,))
            db.commit()
            raise HTTPException(400, f"subtitle file not found: {sub}")
        has_subs = _insert_subtitles(db, media_id,
                                     sub.read_text(encoding="utf-8", errors="replace"),
                                     sub.stem or "Subtitles",
                                     _norm_lang_code_or_empty(body.subtitle_language))
    db.commit()

    jobs.enqueue("prepare", media_id,
                 {"src": str(src), "keep_src": True,  # never touch the user's original
                  "then_transcribe": not has_subs,
                  "whisper": _whisper_payload(body.whisper_model)})
    row = db.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
    return dict(row)


class UrlImport(BaseModel):
    url: str
    title: str = ""
    user_id: int
    whisper_model: str = ""


@app.post("/api/media/from-url")
def import_url(body: UrlImport):
    """Import from YouTube & co. via yt-dlp (pip install yt-dlp)."""
    url = body.url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "that doesn't look like a link")
    db = get_db()
    title = body.title.strip() or f"Link import {url[:60]}"
    cur = db.execute(
        "INSERT INTO media (title, type, filename, status, added_by) VALUES (?,?,?,?,?)",
        (title, "video", "", "downloading", body.user_id))
    media_id = cur.lastrowid
    db.commit()
    jobs.enqueue("download", media_id, {"url": url, "then_transcribe": True,
                                        "whisper": _whisper_payload(body.whisper_model)})
    row = db.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
    return dict(row)


@app.get("/api/media/{media_id}")
def get_media(media_id: int):
    row = get_db().execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
    if not row:
        raise HTTPException(404)
    return dict(row)


@app.delete("/api/media/{media_id}")
def delete_media(media_id: int, user_id: int):
    db = get_db()
    row = db.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
    if not row:
        raise HTTPException(404)
    if row["added_by"] is not None and row["added_by"] != user_id:
        raise HTTPException(403, "only the person who added this media can delete it")
    db.execute("DELETE FROM media WHERE id=?", (media_id,))
    db.commit()
    shutil.rmtree(media_ops.media_dir(media_id), ignore_errors=True)
    return {"ok": True}


class TranscribeIn(BaseModel):
    model: str = ""
    language: str = ""
    device: str = ""
    compute: str = ""


@app.post("/api/media/{media_id}/transcribe")
def retranscribe(media_id: int, body: TranscribeIn | None = None):
    """Queue a (re-)transcription; body fields override the env defaults."""
    db = get_db()
    if not db.execute("SELECT 1 FROM media WHERE id=?", (media_id,)).fetchone():
        raise HTTPException(404)
    db.execute("UPDATE media SET status='queued_transcription' WHERE id=?", (media_id,))
    db.commit()
    payload = {k: v.strip() for k, v in (body.model_dump() if body else {}).items()
               if v and v.strip()}
    return {"job_id": jobs.enqueue("transcribe", media_id, payload)}


WHISPER_MODELS = ["tiny", "tiny.en", "base", "base.en", "small", "small.en",
                  "medium", "medium.en", "large-v2", "large-v3", "distil-large-v3"]


@lru_cache(maxsize=1)
def _whisper_env() -> tuple[str, str | None]:
    """(device, engine) — importing torch is slow, so detect once per process."""
    cuda = False
    try:
        import torch
        cuda = torch.cuda.is_available()
    except ImportError:
        pass
    engine = None
    try:
        import whisperx  # noqa: F401
        engine = "whisperx"
    except ImportError:
        try:
            import faster_whisper  # noqa: F401
            engine = "faster-whisper"
        except ImportError:
            pass
    return ("cuda" if cuda else "cpu"), engine


@app.get("/api/transcribe/options")
def transcribe_options():
    """What the transcription UI can offer: models, default, detected device."""
    device, engine = _whisper_env()
    return {"models": WHISPER_MODELS,
            "default_model": os.environ.get("RECOMPOSER_WHISPER_MODEL", "small"),
            "device": device,
            "engine": engine}


# --------------------------------------------------------------- languages

LANG_CODE_RE = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")


def _norm_lang_code(code: str) -> str:
    raw = (code or "").strip().replace("_", "-")
    parts = [p for p in raw.split("-") if p]
    if not parts:
        raise HTTPException(400, "language code required")
    base = parts[0].lower()
    if len(parts) > 1:
        norm = f"{base}-{parts[1].upper()}"
    else:
        norm = base
    if not LANG_CODE_RE.match(norm):
        raise HTTPException(400, "use a language code like en, es, am, or pt-BR")
    return norm


def _norm_lang_code_or_empty(code: str | None) -> str:
    return _norm_lang_code(code) if (code or "").strip() else ""


def _language_payload(row) -> dict:
    d = dict(row)
    d["dub_capable"] = bool((d.get("tts_voice") or "").strip())
    return d


class LanguageIn(BaseModel):
    code: str
    name: str = ""
    tts_engine: str = "edge"
    tts_voice: str = ""


class LanguageUpdate(BaseModel):
    name: str | None = None
    tts_engine: str | None = None
    tts_voice: str | None = None


@app.get("/api/languages")
def list_languages():
    rows = get_db().execute("SELECT * FROM languages ORDER BY name, code").fetchall()
    return [_language_payload(r) for r in rows]


@app.post("/api/languages")
def create_language(lang: LanguageIn):
    db = get_db()
    code = _norm_lang_code(lang.code)
    name = lang.name.strip() or code
    engine = (lang.tts_engine or "").strip() or "edge"
    voice = (lang.tts_voice or "").strip()
    try:
        db.execute(
            "INSERT INTO languages (code, name, tts_engine, tts_voice) VALUES (?,?,?,?)",
            (code, name, engine, voice))
        db.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"language {code} already exists")
    return _language_payload(db.execute(
        "SELECT * FROM languages WHERE code=?", (code,)).fetchone())


@app.patch("/api/languages/{code}")
def update_language(code: str, lang: LanguageUpdate):
    db = get_db()
    code = _norm_lang_code(code)
    row = db.execute("SELECT * FROM languages WHERE code=?", (code,)).fetchone()
    if not row:
        raise HTTPException(404)
    if lang.name is not None:
        db.execute("UPDATE languages SET name=?, updated_at=datetime('now') WHERE code=?",
                   (lang.name.strip() or code, code))
    if lang.tts_engine is not None:
        db.execute("UPDATE languages SET tts_engine=?, updated_at=datetime('now') WHERE code=?",
                   ((lang.tts_engine or "").strip() or "edge", code))
    if lang.tts_voice is not None:
        db.execute("UPDATE languages SET tts_voice=?, updated_at=datetime('now') WHERE code=?",
                   ((lang.tts_voice or "").strip(), code))
    db.commit()
    return _language_payload(db.execute(
        "SELECT * FROM languages WHERE code=?", (code,)).fetchone())


@app.delete("/api/languages/{code}")
def delete_language(code: str):
    db = get_db()
    code = _norm_lang_code(code)
    cur = db.execute("DELETE FROM languages WHERE code=?", (code,))
    db.commit()
    if not cur.rowcount:
        raise HTTPException(404)
    return {"ok": True}


@app.get("/api/media/{media_id}/segments")
def media_segments(media_id: int, track_id: int | None = None):
    db = get_db()
    if track_id is None:
        row = db.execute(
            "SELECT id FROM tracks WHERE media_id=? ORDER BY id LIMIT 1",
            (media_id,)).fetchone()
        if not row:
            return []
        track_id = row["id"]
    rows = db.execute(
        "SELECT * FROM segments WHERE media_id=? AND track_id=? ORDER BY idx",
        (media_id, track_id))
    return rows_to_dicts(rows)


# ------------------------------------------------------ subtitle tracks

@app.get("/api/media/{media_id}/tracks")
def media_tracks(media_id: int):
    return rows_to_dicts(get_db().execute("""
        SELECT t.*, (SELECT COUNT(*) FROM segments s WHERE s.track_id=t.id) AS segment_count
        FROM tracks t WHERE t.media_id=? ORDER BY t.id""", (media_id,)))


@app.post("/api/media/{media_id}/subtitles")
async def add_subtitle_track(media_id: int,
                             file: UploadFile | None = File(None),
                             path: str = Form(""),
                             name: str = Form(""),
                             lang_code: str = Form("")):
    """Attach another subtitle file (upload or host path) as a NEW track."""
    db = get_db()
    if not db.execute("SELECT 1 FROM media WHERE id=?", (media_id,)).fetchone():
        raise HTTPException(404)
    if file is not None and file.filename:
        raw = (await file.read()).decode("utf-8", errors="replace")
        default_name = Path(file.filename).stem
    elif path.strip():
        p = Path(path.strip().strip('"'))
        if not p.is_file():
            raise HTTPException(400, f"subtitle file not found on the host: {p}")
        raw = p.read_text(encoding="utf-8", errors="replace")
        default_name = p.stem
    else:
        raise HTTPException(400, "provide a subtitle file or a path")
    if not _insert_subtitles(db, media_id, raw, name.strip() or default_name or "Subtitles",
                             _norm_lang_code_or_empty(lang_code)):
        raise HTTPException(400, "subtitle file could not be parsed")
    db.commit()
    return media_tracks(media_id)


class TrackUpdate(BaseModel):
    name: str | None = None
    lang_code: str | None = None


class TrackTranslateIn(BaseModel):
    target_lang: str
    source_language: str = ""
    name: str = ""


@app.patch("/api/tracks/{track_id}")
def rename_track(track_id: int, u: TrackUpdate):
    db = get_db()
    if u.name is not None:
        db.execute("UPDATE tracks SET name=? WHERE id=?",
                   (u.name.strip() or "Subtitles", track_id))
    if u.lang_code is not None:
        db.execute("UPDATE tracks SET lang_code=? WHERE id=?",
                   (_norm_lang_code_or_empty(u.lang_code), track_id))
    db.commit()
    return {"ok": True}


@app.post("/api/tracks/{track_id}/translate")
def translate_track(track_id: int, body: TrackTranslateIn):
    db = get_db()
    track = db.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone()
    if not track:
        raise HTTPException(404)
    target_lang = _norm_lang_code(body.target_lang)
    source_language = (body.source_language or "").strip()
    if source_language and source_language != "auto":
        source_language = _norm_lang_code(source_language)
    running = db.execute("""SELECT 1 FROM jobs WHERE kind='translate_track'
        AND status IN ('queued','running')
        AND target_kind='track' AND target_id=?""", (track_id,)).fetchone()
    if running:
        raise HTTPException(409, "this track is already being translated")
    job_id = jobs.enqueue("translate_track", track["media_id"], {
        "track_id": track_id,
        "target_lang": target_lang,
        "source_language": source_language or track["lang_code"] or "auto",
        "name": body.name.strip(),
    }, target_kind="track", target_id=track_id, max_attempts=1)
    return {"job_id": job_id, "status": "queued"}


@app.delete("/api/tracks/{track_id}")
def delete_track(track_id: int):
    """Deletion is BLOCKED if this is the media's only track, or if any cut
    was made from it — delete those cuts (or add another track) first."""
    db = get_db()
    row = db.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone()
    if not row:
        raise HTTPException(404)
    n_tracks = db.execute("SELECT COUNT(*) AS n FROM tracks WHERE media_id=?",
                          (row["media_id"],)).fetchone()["n"]
    if n_tracks <= 1:
        raise HTTPException(409,
            "this is the only subtitle track of this media — add another track before deleting it")
    seg_ids = [r["id"] for r in db.execute(
        "SELECT id FROM segments WHERE track_id=?", (track_id,))]
    n_cuts = _cuts_using_segments(db, seg_ids)
    if n_cuts:
        raise HTTPException(409,
            f"{n_cuts} cut(s) were made from this track — delete those cuts first")
    db.execute("DELETE FROM segments WHERE track_id=?", (track_id,))
    db.execute("DELETE FROM tracks WHERE id=?", (track_id,))
    db.commit()
    return {"ok": True}


# ------------------------------------------------------- media streaming

CHUNK = 1024 * 512
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


@app.get("/stream/{media_id}")
def stream(media_id: int, request: Request):
    row = get_db().execute("SELECT filename FROM media WHERE id=?", (media_id,)).fetchone()
    if not row or not row["filename"]:
        raise HTTPException(404)
    path = media_ops.media_dir(media_id) / row["filename"]
    if not path.exists():
        raise HTTPException(404)
    file_size = path.stat().st_size
    content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"

    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(path, media_type=content_type,
                            headers={"Accept-Ranges": "bytes"})

    m = RANGE_RE.match(range_header)
    if not m:
        raise HTTPException(416)
    start = int(m.group(1)) if m.group(1) else 0
    end = int(m.group(2)) if m.group(2) else file_size - 1
    end = min(end, file_size - 1)
    if start > end:
        raise HTTPException(416)
    length = end - start + 1

    def iter_range():
        try:
            with path.open("rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    data = f.read(min(CHUNK, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data
        except (ConnectionResetError, BrokenPipeError):
            return  # client aborted mid-stream (seek, cut switch) — normal

    return StreamingResponse(
        iter_range(), status_code=206, media_type=content_type,
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
        })


# ---------------------------------------------------------------- jobs

@app.get("/api/jobs")
def list_jobs():
    rows = get_db().execute("""
        SELECT j.*, m.title AS media_title FROM jobs j
        LEFT JOIN media m ON m.id = j.media_id
        ORDER BY j.id DESC LIMIT 50""")
    return rows_to_dicts(rows)


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: int):
    res = jobs.request_cancel(job_id)
    if "error" in res:
        raise HTTPException(409, res["error"])
    return res


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: int):
    res = jobs.retry(job_id)
    if "error" in res:
        raise HTTPException(409, res["error"])
    return res


# ------------------------------------------------------- folders & tags

class FolderIn(BaseModel):
    name: str
    parent_id: int | None = None


@app.get("/api/folders")
def list_folders():
    return rows_to_dicts(get_db().execute("SELECT * FROM folders ORDER BY name"))


@app.post("/api/folders")
def create_folder(f: FolderIn):
    db = get_db()
    cur = db.execute("INSERT INTO folders (name, parent_id) VALUES (?,?)",
                     (f.name.strip(), f.parent_id))
    db.commit()
    return {"id": cur.lastrowid, "name": f.name.strip(), "parent_id": f.parent_id}


@app.delete("/api/folders/{folder_id}")
def delete_folder(folder_id: int):
    db = get_db()
    db.execute("DELETE FROM folders WHERE id=?", (folder_id,))
    db.commit()
    return {"ok": True}


@app.get("/api/tags")
def list_tags():
    return rows_to_dicts(get_db().execute("""
        SELECT t.*, COUNT(ct.cut_id) AS usage FROM tags t
        LEFT JOIN cut_tags ct ON ct.tag_id = t.id
        GROUP BY t.id ORDER BY t.name"""))


# ---------------------------------------------------------------- cuts

class CutIn(BaseModel):
    media_id: int
    title: str
    note: str = ""
    folder_id: int | None = None
    segment_ids: list[int]
    tags: list[str] = []
    user_id: int


class CutUpdate(BaseModel):
    title: str | None = None
    note: str | None = None
    folder_id: int | None = None
    clear_folder: bool = False
    tags: list[str] | None = None


def _tag_ids(db, names: list[str]) -> list[int]:
    ids = []
    for raw in names:
        name = raw.strip().lstrip("#").lower()
        if not name:
            continue
        row = db.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
        ids.append(row["id"] if row else
                   db.execute("INSERT INTO tags (name) VALUES (?)", (name,)).lastrowid)
    return ids


def _cut_dubs(db, cut_id: int, done_only: bool = False) -> list[dict]:
    where = "WHERE ct.cut_id=?"
    if done_only:
        where += " AND d.status='done'"
    rows = db.execute(f"""
        SELECT d.*, ct.cut_id, ct.lang_code, ct.source, l.name AS language_name
        FROM dubs d
        JOIN cut_translations ct ON ct.id=d.translation_id
        LEFT JOIN languages l ON l.code=ct.lang_code
        {where}
        ORDER BY d.id DESC""", (cut_id,)).fetchall()
    out = rows_to_dicts(rows)
    for d in out:
        d["audio_url"] = f"/api/dubs/{d['id']}/audio" if d["status"] == "done" else None
    return out


def _cut_payload(db, cut_row) -> dict:
    cut = dict(cut_row)
    segs = db.execute("""
        SELECT s.* FROM cut_segments cs JOIN segments s ON s.id = cs.segment_id
        WHERE cs.cut_id=? ORDER BY cs.position""", (cut["id"],)).fetchall()
    cut["segments"] = rows_to_dicts(segs)
    cut["start_s"] = segs[0]["start_s"] if segs else None
    cut["end_s"] = segs[-1]["end_s"] if segs else None
    cut["text"] = " ".join(s["text"] for s in segs)
    cut["tags"] = [r["name"] for r in db.execute("""
        SELECT t.name FROM cut_tags ct JOIN tags t ON t.id = ct.tag_id
        WHERE ct.cut_id=? ORDER BY t.name""", (cut["id"],))]
    cut["dubs"] = _cut_dubs(db, cut["id"], done_only=True)
    return cut


@app.post("/api/cuts")
def create_cut(c: CutIn):
    db = get_db()
    if not c.segment_ids:
        raise HTTPException(400, "a cut needs at least one segment")
    # validate segments belong to the media, to ONE track, and are contiguous
    rows = db.execute(
        f"SELECT id, idx, track_id FROM segments WHERE media_id=? AND id IN ({','.join('?'*len(c.segment_ids))}) ORDER BY idx",
        (c.media_id, *c.segment_ids)).fetchall()
    if len(rows) != len(c.segment_ids):
        raise HTTPException(400, "segments not found in this media")
    if len({r["track_id"] for r in rows}) > 1:
        raise HTTPException(400, "cut segments must come from one subtitle track")
    idxs = [r["idx"] for r in rows]
    if idxs != list(range(idxs[0], idxs[0] + len(idxs))):
        raise HTTPException(400, "cut segments must be consecutive")

    cur = db.execute(
        "INSERT INTO cuts (media_id, title, note, folder_id, created_by) VALUES (?,?,?,?,?)",
        (c.media_id, c.title.strip() or "Untitled cut", c.note, c.folder_id, c.user_id))
    cut_id = cur.lastrowid
    for pos, row in enumerate(rows):
        db.execute("INSERT INTO cut_segments (cut_id, segment_id, position) VALUES (?,?,?)",
                   (cut_id, row["id"], pos))
    for tid in _tag_ids(db, c.tags):
        db.execute("INSERT OR IGNORE INTO cut_tags (cut_id, tag_id) VALUES (?,?)", (cut_id, tid))
    db.commit()
    return _cut_payload(db, db.execute("SELECT * FROM cuts WHERE id=?", (cut_id,)).fetchone())


def _csv_ints(s: str) -> list[int]:
    out = []
    for part in s.split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


@app.get("/api/cuts")
def list_cuts(q: str = "", folder_id: int | None = None, tag: str = "",
              media_id: int | None = None,
              tags: str = "", folder_ids: str = "", media_ids: str = ""):
    """Filters: multi-value CSV params (tags/folder_ids/media_ids) are OR within
    a category, AND across categories. Single-value params kept for compat."""
    db = get_db()
    where, params = [], []

    fids = _csv_ints(folder_ids)
    if folder_id is not None:
        fids.append(folder_id)
    if fids:
        where.append(f"c.folder_id IN ({','.join('?' * len(fids))})")
        params.extend(fids)

    mids = _csv_ints(media_ids)
    if media_id is not None:
        mids.append(media_id)
    if mids:
        where.append(f"c.media_id IN ({','.join('?' * len(mids))})")
        params.extend(mids)

    tag_names = [t.strip().lstrip("#").lower() for t in (tags.split(",") if tags else [])]
    if tag:
        tag_names.append(tag.strip().lstrip("#").lower())
    tag_names = [t for t in tag_names if t]
    if tag_names:
        where.append(f"""c.id IN (SELECT ct.cut_id FROM cut_tags ct
            JOIN tags t ON t.id=ct.tag_id
            WHERE t.name IN ({','.join('?' * len(tag_names))}))""")
        params.extend(tag_names)

    if q.strip():
        safe = '"' + q.strip().replace('"', '""') + '"*'
        where.append("""(c.title LIKE '%' || ? || '%' OR c.id IN (
            SELECT cs.cut_id FROM cut_segments cs
            WHERE cs.segment_id IN (SELECT rowid FROM segments_fts WHERE segments_fts MATCH ?)))""")
        params.extend([q.strip(), safe])
    sql = """SELECT c.*, m.title AS media_title, m.type AS media_type, u.name AS created_by_name
             FROM cuts c JOIN media m ON m.id = c.media_id
             LEFT JOIN users u ON u.id = c.created_by"""
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY c.id DESC LIMIT 200"
    out = []
    for row in db.execute(sql, params):
        cut = _cut_payload(db, row)
        cut["media_title"] = row["media_title"]
        cut["media_type"] = row["media_type"]
        cut["created_by_name"] = row["created_by_name"]
        out.append(cut)
    return out


@app.patch("/api/cuts/{cut_id}")
def update_cut(cut_id: int, u: CutUpdate):
    db = get_db()
    row = db.execute("SELECT * FROM cuts WHERE id=?", (cut_id,)).fetchone()
    if not row:
        raise HTTPException(404)
    if u.title is not None:
        db.execute("UPDATE cuts SET title=? WHERE id=?", (u.title.strip(), cut_id))
    if u.note is not None:
        db.execute("UPDATE cuts SET note=? WHERE id=?", (u.note, cut_id))
    if u.clear_folder:
        db.execute("UPDATE cuts SET folder_id=NULL WHERE id=?", (cut_id,))
    elif u.folder_id is not None:
        db.execute("UPDATE cuts SET folder_id=? WHERE id=?", (u.folder_id, cut_id))
    if u.tags is not None:
        db.execute("DELETE FROM cut_tags WHERE cut_id=?", (cut_id,))
        for tid in _tag_ids(db, u.tags):
            db.execute("INSERT OR IGNORE INTO cut_tags (cut_id, tag_id) VALUES (?,?)", (cut_id, tid))
    db.commit()
    return _cut_payload(db, db.execute("SELECT * FROM cuts WHERE id=?", (cut_id,)).fetchone())


@app.delete("/api/cuts/{cut_id}")
def delete_cut(cut_id: int):
    db = get_db()
    db.execute("DELETE FROM cuts WHERE id=?", (cut_id,))
    db.commit()
    return {"ok": True}


def _stem_status_payload(cache: dict) -> dict:
    return {
        "cut_id": cache["cut_id"],
        "media_id": cache["media_id"],
        "start_s": cache["start_s"],
        "end_s": cache["end_s"],
        "segment_start_s": cache["segment_start_s"],
        "segment_end_s": cache["segment_end_s"],
        "padding_s": cache["padding_s"],
        "cache_dir": str(cache["dir"]),
        "exists": cache["exists"],
        "vocals": str(cache["vocals"]) if cache["vocals"].exists() else None,
        "accompaniment": (
            str(cache["accompaniment"]) if cache["accompaniment"].exists() else None
        ),
    }


@app.get("/api/cuts/{cut_id}/stems")
def cut_stems(cut_id: int, padding_s: float = 3.0):
    try:
        return _stem_status_payload(jobs.cut_stem_cache(cut_id, padding_s))
    except RuntimeError as e:
        raise HTTPException(404, str(e))


@app.post("/api/cuts/{cut_id}/separate")
def separate_cut(cut_id: int, padding_s: float = 3.0):
    db = get_db()
    try:
        cache = jobs.cut_stem_cache(cut_id, padding_s)
    except RuntimeError as e:
        raise HTTPException(404, str(e))
    if cache["exists"]:
        return {"status": "ready", "cached": True,
                "stems": _stem_status_payload(cache)}
    running = db.execute("""
        SELECT id, status FROM jobs
        WHERE kind='separate' AND target_kind='cut' AND target_id=?
          AND status IN ('queued','running')
        ORDER BY id DESC LIMIT 1""", (cut_id,)).fetchone()
    if running:
        return {"job_id": running["id"], "status": running["status"], "cached": False}
    return {"job_id": jobs.enqueue(
        "separate", cache["media_id"],
        {"cut_id": cut_id, "padding_s": padding_s},
        target_kind="cut", target_id=cut_id),
        "status": "queued", "cached": False}


# ------------------------------------------------ translations & dubs

class TranslationCreate(BaseModel):
    lang_code: str
    source: str = "manual"  # manual | auto
    source_language: str = "auto"
    user_id: int | None = None
    segments: dict[int, str] = {}


class TranslationSegmentUpdate(BaseModel):
    text: str


def _cut_segment_rows(db, cut_id: int):
    return db.execute("""
        SELECT s.*
        FROM cut_segments cs JOIN segments s ON s.id=cs.segment_id
        WHERE cs.cut_id=?
        ORDER BY cs.position""", (cut_id,)).fetchall()


def _translation_payload(db, translation_id: int) -> dict:
    row = db.execute("""
        SELECT ct.*, l.name AS language_name, l.tts_engine, l.tts_voice
        FROM cut_translations ct
        LEFT JOIN languages l ON l.code=ct.lang_code
        WHERE ct.id=?""", (translation_id,)).fetchone()
    if not row:
        raise HTTPException(404)
    out = dict(row)
    segs = db.execute("""
        SELECT s.id AS segment_id, s.idx, s.start_s, s.end_s,
               s.text AS source_text, ts.text
        FROM cut_segments cs
        JOIN segments s ON s.id=cs.segment_id
        LEFT JOIN translation_segments ts
          ON ts.segment_id=s.id AND ts.translation_id=?
        WHERE cs.cut_id=?
        ORDER BY cs.position""", (translation_id, row["cut_id"])).fetchall()
    out["segments"] = rows_to_dicts(segs)
    out["dubs"] = rows_to_dicts(db.execute("""
        SELECT * FROM dubs WHERE translation_id=? ORDER BY id DESC""",
        (translation_id,)).fetchall())
    for d in out["dubs"]:
        d["audio_url"] = f"/api/dubs/{d['id']}/audio" if d["status"] == "done" else None
    out["dub_capable"] = bool((row["tts_voice"] or "").strip())
    return out


@app.get("/api/cuts/{cut_id}/translations")
def list_cut_translations(cut_id: int):
    db = get_db()
    cut = db.execute("SELECT * FROM cuts WHERE id=?", (cut_id,)).fetchone()
    if not cut:
        raise HTTPException(404)
    source_segments = rows_to_dicts(_cut_segment_rows(db, cut_id))
    ids = [r["id"] for r in db.execute(
        "SELECT id FROM cut_translations WHERE cut_id=? ORDER BY id DESC",
        (cut_id,)).fetchall()]
    return {
        "cut": _cut_payload(db, cut),
        "source_segments": source_segments,
        "translations": [_translation_payload(db, tid) for tid in ids],
    }


@app.post("/api/cuts/{cut_id}/translations")
def create_translation(cut_id: int, body: TranslationCreate):
    db = get_db()
    if not db.execute("SELECT 1 FROM cuts WHERE id=?", (cut_id,)).fetchone():
        raise HTTPException(404)
    lang_code = _norm_lang_code(body.lang_code)
    if not db.execute("SELECT 1 FROM languages WHERE code=?", (lang_code,)).fetchone():
        raise HTTPException(404, f"language {lang_code} is not configured")
    segs = _cut_segment_rows(db, cut_id)
    if not segs:
        raise HTTPException(400, "cut has no segments")

    try:
        tid, _ = translation_ops.create_cut_translation(
            db, cut_id, lang_code, source=body.source,
            source_language=body.source_language or "auto",
            created_by=body.user_id, segments=body.segments)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    db.commit()
    return _translation_payload(db, tid)


@app.patch("/api/translations/{translation_id}/segments/{segment_id}")
def update_translation_segment(translation_id: int, segment_id: int,
                               body: TranslationSegmentUpdate):
    db = get_db()
    row = db.execute("SELECT * FROM cut_translations WHERE id=?",
                     (translation_id,)).fetchone()
    if not row:
        raise HTTPException(404)
    if not db.execute("""
        SELECT 1 FROM cut_segments
        WHERE cut_id=? AND segment_id=?""", (row["cut_id"], segment_id)).fetchone():
        raise HTTPException(400, "segment is not part of this cut")
    db.execute("""
        INSERT INTO translation_segments (translation_id, segment_id, text)
        VALUES (?,?,?)
        ON CONFLICT(translation_id, segment_id) DO UPDATE SET text=excluded.text""",
        (translation_id, segment_id, body.text.strip()))
    db.commit()
    return _translation_payload(db, translation_id)


@app.delete("/api/translations/{translation_id}")
def delete_translation(translation_id: int):
    db = get_db()
    cur = db.execute("DELETE FROM cut_translations WHERE id=?", (translation_id,))
    db.commit()
    if not cur.rowcount:
        raise HTTPException(404)
    return {"ok": True}


@app.post("/api/translations/{translation_id}/dub")
def create_dub(translation_id: int):
    db = get_db()
    row = db.execute("""
        SELECT ct.*, l.tts_engine, l.tts_voice
        FROM cut_translations ct JOIN languages l ON l.code=ct.lang_code
        WHERE ct.id=?""", (translation_id,)).fetchone()
    if not row:
        raise HTTPException(404)
    if not (row["tts_voice"] or "").strip():
        raise HTTPException(400, f"language {row['lang_code']} has no TTS voice configured")
    running = db.execute("""
        SELECT * FROM dubs WHERE translation_id=? AND status IN ('queued','running')
        ORDER BY id DESC LIMIT 1""", (translation_id,)).fetchone()
    if running:
        return {"dub": dict(running), "job_id": None, "status": running["status"]}
    cur = db.execute(
        "INSERT INTO dubs (translation_id, engine, voice, status, detail) "
        "VALUES (?,?,?,?,?)",
        (translation_id, row["tts_engine"] or "edge", row["tts_voice"], "queued", "queued"))
    dub_id = cur.lastrowid
    db.commit()
    job_id = jobs.enqueue("dub", None, {"dub_id": dub_id},
                          target_kind="dub", target_id=dub_id, max_attempts=1)
    dub = dict(db.execute("SELECT * FROM dubs WHERE id=?", (dub_id,)).fetchone())
    return {"dub": dub, "job_id": job_id, "status": "queued"}


@app.get("/api/dubs/{dub_id}/audio")
def dub_audio(dub_id: int):
    db = get_db()
    row = db.execute("SELECT * FROM dubs WHERE id=?", (dub_id,)).fetchone()
    if not row:
        raise HTTPException(404)
    if row["status"] != "done" or not row["filename"]:
        raise HTTPException(409, "dub audio is not ready")
    path = media_ops.MEDIA_ROOT / row["filename"]
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="audio/mp4", filename=path.name)


# ----------------------------------------------------- segment editing

class SegmentUpdate(BaseModel):
    text: str | None = None
    start_s: float | None = None
    end_s: float | None = None


class SegmentIn(BaseModel):
    track_id: int
    start_s: float
    end_s: float
    text: str = ""


@app.patch("/api/segments/{seg_id}")
def update_segment(seg_id: int, u: SegmentUpdate):
    db = get_db()
    row = db.execute("SELECT * FROM segments WHERE id=?", (seg_id,)).fetchone()
    if not row:
        raise HTTPException(404)
    text = u.text if u.text is not None else row["text"]
    start = u.start_s if u.start_s is not None else row["start_s"]
    end = u.end_s if u.end_s is not None else row["end_s"]
    if end <= start:
        raise HTTPException(400, "end time must be after start time")
    db.execute("UPDATE segments SET text=?, start_s=?, end_s=? WHERE id=?",
               (text.strip(), round(start, 3), round(end, 3), seg_id))
    if u.start_s is not None:  # order may have changed
        _reindex_track(db, row["track_id"])
    db.commit()
    return dict(db.execute("SELECT * FROM segments WHERE id=?", (seg_id,)).fetchone())


@app.post("/api/segments")
def create_segment(s: SegmentIn):
    db = get_db()
    track = db.execute("SELECT * FROM tracks WHERE id=?", (s.track_id,)).fetchone()
    if not track:
        raise HTTPException(404, "track not found")
    if s.end_s <= s.start_s:
        raise HTTPException(400, "end time must be after start time")
    cur = db.execute(
        "INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text) "
        "VALUES (?,?,?,?,?,?)",
        (track["media_id"], s.track_id, -1, round(s.start_s, 3), round(s.end_s, 3),
         s.text.strip() or "…"))
    _reindex_track(db, s.track_id)
    db.commit()
    return dict(db.execute("SELECT * FROM segments WHERE id=?", (cur.lastrowid,)).fetchone())


@app.delete("/api/segments/{seg_id}")
def delete_segment(seg_id: int, force: int = 0):
    db = get_db()
    row = db.execute("SELECT * FROM segments WHERE id=?", (seg_id,)).fetchone()
    if not row:
        raise HTTPException(404)
    n_cuts = _cuts_using_segments(db, [seg_id])
    if n_cuts and not force:
        raise HTTPException(409, f"this line is part of {n_cuts} cut(s)")
    db.execute("DELETE FROM segments WHERE id=?", (seg_id,))
    dropped = _drop_empty_cuts(db)
    _reindex_track(db, row["track_id"])
    db.commit()
    return {"ok": True, "cuts_deleted": dropped}


class BatchOp(BaseModel):
    pattern: str
    action: str = "preview"   # preview | replace | delete
    replacement: str = ""
    case_sensitive: bool = False


@app.post("/api/tracks/{track_id}/batch")
def batch_segments(track_id: int, b: BatchOp):
    """Regex batch operations over one track: preview matches, regex-replace
    text (empty result deletes the line), or delete every matching line."""
    db = get_db()
    if not db.execute("SELECT 1 FROM tracks WHERE id=?", (track_id,)).fetchone():
        raise HTTPException(404)
    try:
        rx = re.compile(b.pattern, 0 if b.case_sensitive else re.IGNORECASE)
    except re.error as e:
        raise HTTPException(400, f"bad regex: {e}")

    rows = db.execute("SELECT * FROM segments WHERE track_id=? ORDER BY idx",
                      (track_id,)).fetchall()
    matched = [r for r in rows if rx.search(r["text"])]
    seg_ids = [r["id"] for r in matched]
    n_cuts = _cuts_using_segments(db, seg_ids)

    if b.action == "preview":
        return {"count": len(matched), "cuts_affected": n_cuts,
                "matches": rows_to_dicts(matched[:300])}

    deleted = changed = 0
    if b.action == "delete":
        for r in matched:
            db.execute("DELETE FROM segments WHERE id=?", (r["id"],))
            deleted += 1
    elif b.action == "replace":
        for r in matched:
            new = rx.sub(b.replacement, r["text"]).strip()
            if new == r["text"]:
                continue
            if new:
                db.execute("UPDATE segments SET text=? WHERE id=?", (new, r["id"]))
                changed += 1
            else:  # replacement emptied the line: remove it
                db.execute("DELETE FROM segments WHERE id=?", (r["id"],))
                deleted += 1
    else:
        raise HTTPException(400, "action must be preview, replace or delete")

    dropped = _drop_empty_cuts(db)
    if deleted:
        _reindex_track(db, track_id)
    db.commit()
    return {"count": len(matched), "changed": changed, "deleted": deleted,
            "cuts_deleted": dropped}


# ------------------------------------------------------- segment search

@app.get("/api/search/segments")
def search_segments(q: str, media_id: int | None = None, track_id: int | None = None,
                    limit: int = 60, fuzzy: int = 1):
    """Exact (FTS5) + fuzzy (trigram-index + word-similarity re-rank) search.
    Results carry match='exact'|'fuzzy' and a 0–1 score."""
    return search.search_segments(q, media_id=media_id, track_id=track_id,
                                  limit=limit, fuzzy=bool(fuzzy))


# ------------------------------------------------------ recompositions

class RecompIn(BaseModel):
    title: str
    user_id: int


class RecompCutItem(BaseModel):
    cut_id: int
    audio_mode: str = "original"
    dub_id: int | None = None


class RecompCuts(BaseModel):
    cut_ids: list[int] | None = None
    items: list[RecompCutItem] | None = None


@app.get("/api/recompositions")
def list_recomps():
    db = get_db()
    rows = db.execute("""
        SELECT r.*, u.name AS created_by_name,
               (SELECT COUNT(*) FROM recomp_cuts rc WHERE rc.recomp_id = r.id) AS cut_count
        FROM recompositions r LEFT JOIN users u ON u.id = r.created_by
        ORDER BY r.id DESC""")
    return rows_to_dicts(rows)


@app.post("/api/recompositions")
def create_recomp(r: RecompIn):
    db = get_db()
    cur = db.execute("INSERT INTO recompositions (title, created_by) VALUES (?,?)",
                     (r.title.strip() or "Untitled", r.user_id))
    db.commit()
    return {"id": cur.lastrowid, "title": r.title.strip(), "cut_count": 0}


@app.get("/api/recompositions/{recomp_id}")
def get_recomp(recomp_id: int):
    db = get_db()
    row = db.execute("SELECT * FROM recompositions WHERE id=?", (recomp_id,)).fetchone()
    if not row:
        raise HTTPException(404)
    recomp = dict(row)
    cuts = []
    for rc in db.execute("""
            SELECT c.*, rc.audio_mode, rc.dub_id,
                   m.title AS media_title, m.type AS media_type
            FROM recomp_cuts rc JOIN cuts c ON c.id = rc.cut_id
            JOIN media m ON m.id = c.media_id
            WHERE rc.recomp_id=? ORDER BY rc.position""", (recomp_id,)):
        cut = _cut_payload(db, rc)
        cut["media_title"] = rc["media_title"]
        cut["media_type"] = rc["media_type"]
        cuts.append(cut)
    recomp["cuts"] = cuts
    return recomp


@app.put("/api/recompositions/{recomp_id}/cuts")
def set_recomp_cuts(recomp_id: int, body: RecompCuts):
    db = get_db()
    if not db.execute("SELECT 1 FROM recompositions WHERE id=?", (recomp_id,)).fetchone():
        raise HTTPException(404)
    existing = rows_to_dicts(db.execute("""
        SELECT position, cut_id, audio_mode, dub_id FROM recomp_cuts
        WHERE recomp_id=? ORDER BY position""", (recomp_id,)).fetchall())

    if body.items is not None:
        items = [i.model_dump() for i in body.items]
    elif body.cut_ids is not None:
        buckets: dict[int, list[dict]] = {}
        for r in existing:
            buckets.setdefault(r["cut_id"], []).append(r)
        items = []
        for cid in body.cut_ids:
            prev = buckets.get(cid, [])
            kept = prev.pop(0) if prev else {}
            items.append({
                "cut_id": cid,
                "audio_mode": kept.get("audio_mode") or "original",
                "dub_id": kept.get("dub_id"),
            })
    else:
        raise HTTPException(400, "provide cut_ids or items")

    for item in items:
        mode = item.get("audio_mode") or "original"
        dub_id = item.get("dub_id")
        if mode not in ("original", "dub"):
            raise HTTPException(400, "audio_mode must be original or dub")
        if mode == "dub":
            if not dub_id:
                raise HTTPException(400, "dub_id is required for audio_mode=dub")
            ok = db.execute("""
                SELECT 1 FROM dubs d
                JOIN cut_translations ct ON ct.id=d.translation_id
                WHERE d.id=? AND d.status='done' AND ct.cut_id=?""",
                (dub_id, item["cut_id"])).fetchone()
            if not ok:
                raise HTTPException(400, "dub must be ready and belong to this cut")
        else:
            item["dub_id"] = None

    db.execute("DELETE FROM recomp_cuts WHERE recomp_id=?", (recomp_id,))
    for pos, item in enumerate(items):
        db.execute("""
            INSERT INTO recomp_cuts (recomp_id, cut_id, position, audio_mode, dub_id)
            VALUES (?,?,?,?,?)""",
            (recomp_id, item["cut_id"], pos,
             item.get("audio_mode") or "original", item.get("dub_id")))
    db.commit()
    return get_recomp(recomp_id)


class RecompUpdate(BaseModel):
    title: str


class RecompTranslateIn(BaseModel):
    lang_code: str
    source_language: str = "auto"
    user_id: int | None = None
    overwrite: bool = False


@app.patch("/api/recompositions/{recomp_id}")
def rename_recomp(recomp_id: int, u: RecompUpdate):
    db = get_db()
    db.execute("UPDATE recompositions SET title=? WHERE id=?", (u.title.strip(), recomp_id))
    db.commit()
    return {"ok": True}


@app.delete("/api/recompositions/{recomp_id}")
def delete_recomp(recomp_id: int):
    db = get_db()
    db.execute("DELETE FROM recompositions WHERE id=?", (recomp_id,))
    db.commit()
    return {"ok": True}


@app.post("/api/recompositions/{recomp_id}/translations")
def translate_recomp(recomp_id: int, body: RecompTranslateIn):
    db = get_db()
    if not db.execute("SELECT 1 FROM recompositions WHERE id=?", (recomp_id,)).fetchone():
        raise HTTPException(404)
    lang_code = _norm_lang_code(body.lang_code)
    if not db.execute("SELECT 1 FROM languages WHERE code=?", (lang_code,)).fetchone():
        raise HTTPException(404, f"language {lang_code} is not configured")
    source_language = (body.source_language or "").strip()
    if source_language and source_language != "auto":
        source_language = _norm_lang_code(source_language)
    running = db.execute("""SELECT 1 FROM jobs WHERE kind='translate_recomposition'
        AND status IN ('queued','running')
        AND target_kind='recomposition' AND target_id=?""",
        (recomp_id,)).fetchone()
    if running:
        raise HTTPException(409, "this recomposition is already being translated")
    job_id = jobs.enqueue("translate_recomposition", None, {
        "recomp_id": recomp_id,
        "lang_code": lang_code,
        "source_language": source_language or "auto",
        "user_id": body.user_id,
        "overwrite": body.overwrite,
    }, target_kind="recomposition", target_id=recomp_id, max_attempts=1)
    return {"job_id": job_id, "status": "queued"}


# ------------------------------------------------------------- export

class ExportIn(BaseModel):
    audio_mode: str = "sequence"  # sequence | original | target_dub
    target_lang: str = ""
    quality: str = "720p"


@app.post("/api/recompositions/{recomp_id}/export")
def export_recomp(recomp_id: int, body: ExportIn | None = None):
    """Render the recomposition into one real .mp4 (or .wav if audio-only)."""
    db = get_db()
    if not db.execute("SELECT 1 FROM recompositions WHERE id=?", (recomp_id,)).fetchone():
        raise HTTPException(404)
    n = db.execute("SELECT COUNT(*) AS n FROM recomp_cuts WHERE recomp_id=?",
                   (recomp_id,)).fetchone()["n"]
    if not n:
        raise HTTPException(400, "add some cuts before exporting")
    running = db.execute("""SELECT 1 FROM jobs WHERE kind='export'
        AND status IN ('queued','running')
        AND target_kind='recomposition' AND target_id=?""",
        (recomp_id,)).fetchone()
    if running:
        raise HTTPException(409, "an export of this recomposition is already running")
    body = body or ExportIn()
    audio_mode = (body.audio_mode or "sequence").strip()
    if audio_mode not in ("sequence", "original", "target_dub"):
        raise HTTPException(400, "audio_mode must be sequence, original, or target_dub")
    quality = (body.quality or "720p").strip()
    if quality not in media_ops.EXPORT_PRESETS:
        raise HTTPException(400, "quality must be 480p, 720p, or 1080p")
    target_lang = _norm_lang_code_or_empty(body.target_lang)
    if audio_mode == "target_dub" and not target_lang:
        raise HTTPException(400, "target_lang is required for translated dub export")
    return {"job_id": jobs.enqueue("export", None, {
        "recomp_id": recomp_id,
        "audio_mode": audio_mode,
        "target_lang": target_lang,
        "quality": quality,
    },
                                   target_kind="recomposition", target_id=recomp_id)}


@app.get("/api/recompositions/{recomp_id}/exports")
def list_exports(recomp_id: int):
    d = media_ops.EXPORT_DIR
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob(f"recomp{recomp_id}_*"), reverse=True):
        if f.is_file():
            st = f.stat()
            out.append({"filename": f.name, "size": st.st_size, "mtime": st.st_mtime})
    return out


@app.get("/api/exports/{filename}")
def download_export(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400)
    path = media_ops.EXPORT_DIR / filename
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, filename=filename,
                        media_type=mimetypes.guess_type(filename)[0] or "application/octet-stream")


@app.delete("/api/exports/{filename}")
def delete_export(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400)
    path = media_ops.EXPORT_DIR / filename
    if not path.is_file():
        raise HTTPException(404)
    media_ops.safe_unlink(path)
    return {"ok": True}


# ------------------------------------------------------------ frontend

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        target = FRONTEND_DIST / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/")
    def no_frontend():
        return Response("Frontend not built. Run: cd frontend && npm install && npm run build",
                        media_type="text/plain")
