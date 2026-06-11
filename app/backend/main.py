"""Recomposer — single-process FastAPI app: API + media streaming + frontend."""
import mimetypes
import os
import re
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import jobs, media_ops
from .db import get_db, init_db, rows_to_dicts
from .srt_parser import parse_subtitles

app = FastAPI(title="Recomposer")

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@app.on_event("startup")
def _startup():
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


@app.post("/api/media")
async def upload_media(
    file: UploadFile = File(...),
    subtitle: UploadFile | None = File(None),
    title: str = Form(""),
    user_id: int = Form(...),
):
    db = get_db()
    title = title.strip() or Path(file.filename or "untitled").stem
    cur = db.execute(
        "INSERT INTO media (title, type, filename, status, added_by) VALUES (?,?,?,?,?)",
        (title, "video", "", "processing", user_id))
    media_id = cur.lastrowid
    db.commit()

    suffix = Path(file.filename or "upload.bin").suffix or ".bin"
    fd, tmp_name = tempfile.mkstemp(suffix=suffix)
    os.close(fd)  # Windows: an open handle would block every later move/delete
    tmp = Path(tmp_name)
    try:
        with tmp.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        final, mtype, duration = media_ops.prepare_for_streaming(tmp, media_id)
    except Exception as e:
        db.execute("DELETE FROM media WHERE id=?", (media_id,))
        db.commit()
        media_ops.safe_unlink(tmp)
        raise HTTPException(400, f"could not process media: {e}")

    db.execute("UPDATE media SET type=?, filename=?, duration=? WHERE id=?",
               (mtype, final.name, duration, media_id))
    db.commit()

    if subtitle is not None and subtitle.filename:
        raw = (await subtitle.read()).decode("utf-8", errors="replace")
        segs = parse_subtitles(raw)
        if not segs:
            db.execute("UPDATE media SET status=?, status_detail=? WHERE id=?",
                       ("error", "subtitle file could not be parsed", media_id))
        else:
            for i, s in enumerate(segs):
                db.execute(
                    "INSERT INTO segments (media_id, idx, start_s, end_s, text) VALUES (?,?,?,?,?)",
                    (media_id, i, s["start_s"], s["end_s"], s["text"]))
            db.execute("UPDATE media SET status='ready' WHERE id=?", (media_id,))
        db.commit()
    else:
        db.execute("UPDATE media SET status='queued_transcription' WHERE id=?", (media_id,))
        db.commit()
        jobs.enqueue("transcribe", media_id)

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


@app.post("/api/media/{media_id}/transcribe")
def retranscribe(media_id: int):
    db = get_db()
    if not db.execute("SELECT 1 FROM media WHERE id=?", (media_id,)).fetchone():
        raise HTTPException(404)
    db.execute("UPDATE media SET status='queued_transcription' WHERE id=?", (media_id,))
    db.commit()
    return {"job_id": jobs.enqueue("transcribe", media_id)}


@app.get("/api/media/{media_id}/segments")
def media_segments(media_id: int):
    rows = get_db().execute(
        "SELECT * FROM segments WHERE media_id=? ORDER BY idx", (media_id,))
    return rows_to_dicts(rows)


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
        with path.open("rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                data = f.read(min(CHUNK, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

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
    return cut


@app.post("/api/cuts")
def create_cut(c: CutIn):
    db = get_db()
    if not c.segment_ids:
        raise HTTPException(400, "a cut needs at least one segment")
    # validate segments belong to the media and are contiguous
    rows = db.execute(
        f"SELECT id, idx FROM segments WHERE media_id=? AND id IN ({','.join('?'*len(c.segment_ids))}) ORDER BY idx",
        (c.media_id, *c.segment_ids)).fetchall()
    if len(rows) != len(c.segment_ids):
        raise HTTPException(400, "segments not found in this media")
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


@app.get("/api/cuts")
def list_cuts(q: str = "", folder_id: int | None = None, tag: str = "",
              media_id: int | None = None):
    db = get_db()
    where, params = [], []
    if folder_id is not None:
        where.append("c.folder_id = ?"); params.append(folder_id)
    if media_id is not None:
        where.append("c.media_id = ?"); params.append(media_id)
    if tag:
        where.append("c.id IN (SELECT ct.cut_id FROM cut_tags ct JOIN tags t ON t.id=ct.tag_id WHERE t.name = ?)")
        params.append(tag.strip().lstrip("#").lower())
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


# ------------------------------------------------------- segment search

@app.get("/api/search/segments")
def search_segments(q: str, media_id: int | None = None, limit: int = 60):
    db = get_db()
    if not q.strip():
        return []
    safe = '"' + q.strip().replace('"', '""') + '"*'
    sql = """SELECT s.*, m.title AS media_title, m.type AS media_type
             FROM segments_fts f JOIN segments s ON s.id = f.rowid
             JOIN media m ON m.id = s.media_id
             WHERE segments_fts MATCH ?"""
    params: list = [safe]
    if media_id is not None:
        sql += " AND s.media_id = ?"
        params.append(media_id)
    sql += " ORDER BY rank LIMIT ?"
    params.append(min(limit, 200))
    return rows_to_dicts(db.execute(sql, params))


# ------------------------------------------------------ recompositions

class RecompIn(BaseModel):
    title: str
    user_id: int


class RecompCuts(BaseModel):
    cut_ids: list[int]


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
            SELECT c.*, m.title AS media_title, m.type AS media_type
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
    db.execute("DELETE FROM recomp_cuts WHERE recomp_id=?", (recomp_id,))
    for pos, cid in enumerate(body.cut_ids):
        db.execute("INSERT INTO recomp_cuts (recomp_id, cut_id, position) VALUES (?,?,?)",
                   (recomp_id, cid, pos))
    db.commit()
    return get_recomp(recomp_id)


class RecompUpdate(BaseModel):
    title: str


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
