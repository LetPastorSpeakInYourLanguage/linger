"""Bulk ingest from a watched local folder.

`scan()` walks a registered folder and ingests anything new:
  • media folder  — each video/audio file becomes a media row; sibling subtitle
    files (``movie.srt`` / ``movie.en.srt`` …) are attached as tracks; if a movie
    has no subtitles it's queued for transcription with the default settings.
  • audio folder  — each audio file becomes a background-audio bed, filed into a
    folder mirroring its sub-directory under the watched root.

A ``scanned_files`` ledger keeps re-scans idempotent (already-seen paths skip).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from . import media_ops
from .srt_parser import parse_subtitles

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv", ".flv", ".mpg", ".mpeg"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}
SUB_EXTS = {".srt", ".vtt", ".ass", ".ssa"}


def _read(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, OSError):
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _insert_subtitles(db, media_id: int, raw: str, name: str, lang: str) -> bool:
    segs = parse_subtitles(raw)
    if not segs:
        return False
    tid = db.execute("INSERT INTO tracks (media_id, name, lang_code) VALUES (?,?,?)",
                     (media_id, name or "Subtitles", lang or "")).lastrowid
    for i, s in enumerate(segs):
        db.execute("INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text) "
                   "VALUES (?,?,?,?,?,?)", (media_id, tid, i, s["start_s"], s["end_s"], s["text"]))
    return True


def _subs_for(video: Path) -> list[tuple[Path, str]]:
    """Sibling subtitle files sharing the video's stem. ``movie.en.srt`` →
    lang 'en'; ``movie.srt`` → lang ''."""
    out = []
    stem = video.stem
    for f in video.parent.iterdir():
        if f.suffix.lower() not in SUB_EXTS or not f.is_file():
            continue
        if f.stem == stem:
            out.append((f, ""))
        elif f.stem.startswith(stem + "."):
            lang = f.stem[len(stem) + 1:].split(".")[-1].lower()
            out.append((f, lang if 1 <= len(lang) <= 5 else ""))
    return out


def _seen(db, path: str) -> bool:
    return db.execute("SELECT 1 FROM scanned_files WHERE path=?", (path,)).fetchone() is not None


def _mark(db, path: str, kind: str, ref_id: int):
    db.execute("INSERT OR REPLACE INTO scanned_files (path, kind, ref_id) VALUES (?,?,?)",
               (path, kind, ref_id))


def scan(db, folder_row, ctx, enqueue) -> dict:
    root = Path(folder_row["path"])
    kind = folder_row["kind"]
    if not root.is_dir():
        ctx.report(f"folder not found: {root}", progress=100)
        return {"ingested": 0}
    exts = (VIDEO_EXTS | AUDIO_EXTS) if kind == "media" else AUDIO_EXTS
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in exts)
    ingested = 0
    for i, f in enumerate(files):
        ctx.check_cancel()
        ctx.report(f"scanning {f.name}", progress=5 + (i / max(1, len(files))) * 90)
        key = str(f.resolve())
        if _seen(db, key):
            continue
        if kind == "media":
            mid = db.execute(
                "INSERT INTO media (title, type, filename, status, added_by) VALUES (?,?,?,?,?)",
                (f.stem, "video", "", "preparing", None)).lastrowid
            has_subs = False
            for sp, lang in _subs_for(f):
                try:
                    if _insert_subtitles(db, mid, _read(sp), sp.stem, lang):
                        has_subs = True
                except Exception:
                    pass
            db.execute("INSERT INTO media_sources (media_id, kind, locator, status) "
                       "VALUES (?,?,?,?)", (mid, "local", key, "ok"))
            _mark(db, key, "media", mid)
            db.commit()
            enqueue("prepare", mid, {"src": key, "keep_src": True,
                                     "then_transcribe": not has_subs, "whisper": {}})
            ingested += 1
        else:  # audio bed
            rel = f.parent.relative_to(root).as_posix()
            folder = "" if rel == "." else rel
            asset_id = db.execute(
                "INSERT INTO audio_assets (name, filename, added_by, folder) VALUES (?,?,?,?)",
                (f.stem, "", None, folder)).lastrowid
            stored = f"{asset_id}{f.suffix.lower()}"
            media_ops.BG_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(f, media_ops.bg_audio_path(stored))
                dur = media_ops.duration(media_ops.bg_audio_path(stored))
                db.execute("UPDATE audio_assets SET filename=?, duration_s=? WHERE id=?",
                           (stored, dur, asset_id))
            except Exception:
                db.execute("DELETE FROM audio_assets WHERE id=?", (asset_id,))
                db.commit()
                continue
            _mark(db, key, "audio", asset_id)
            db.commit()
            ingested += 1
    ctx.report(f"scan complete — {ingested} new item(s)", progress=100)
    return {"ingested": ingested}
