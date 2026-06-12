"""Shared subtitle and cut translation operations."""
from __future__ import annotations

from collections.abc import Callable

from .engines import translate


Progress = Callable[[str, float | None], None] | None


def cut_segment_rows(db, cut_id: int):
    return db.execute("""
        SELECT s.*, t.lang_code AS track_lang_code
        FROM cut_segments cs
        JOIN segments s ON s.id=cs.segment_id
        LEFT JOIN tracks t ON t.id=s.track_id
        WHERE cs.cut_id=?
        ORDER BY cs.position""", (cut_id,)).fetchall()


def _source_language_for_segments(segs, requested: str = "") -> str:
    requested = (requested or "").strip()
    if requested and requested != "auto":
        return requested
    langs = {(s["track_lang_code"] or "").strip() for s in segs
             if (s["track_lang_code"] or "").strip()}
    return langs.pop() if len(langs) == 1 else "auto"


def create_cut_translation(db, cut_id: int, lang_code: str, *,
                           source: str = "auto",
                           source_language: str = "auto",
                           created_by: int | None = None,
                           segments: dict[int, str] | None = None) -> tuple[int, str]:
    segs = cut_segment_rows(db, cut_id)
    if not segs:
        raise ValueError("cut has no segments")

    source = (source or "manual").strip().lower()
    texts: dict[int, str] = {}
    if source == "auto":
        engine = translate.get_translate_engine()
        actual_source = _source_language_for_segments(segs, source_language)
        translated = engine.translate_many([s["text"] for s in segs], lang_code,
                                           actual_source)
        texts = {int(s["id"]): translated[i].text for i, s in enumerate(segs)}
        source_label = f"auto:{engine.name}"
    elif source == "manual":
        provided = segments or {}
        texts = {int(s["id"]): provided.get(int(s["id"]), s["text"]) for s in segs}
        source_label = "user"
    else:
        raise ValueError("source must be manual or auto")

    cur = db.execute(
        "INSERT INTO cut_translations (cut_id, lang_code, source, created_by) "
        "VALUES (?,?,?,?)",
        (cut_id, lang_code, source_label, created_by))
    translation_id = cur.lastrowid
    for s in segs:
        db.execute(
            "INSERT INTO translation_segments (translation_id, segment_id, text) "
            "VALUES (?,?,?)",
            (translation_id, s["id"], texts.get(int(s["id"]), "")))
    return translation_id, source_label


def _unique_track_name(db, media_id: int, base: str) -> str:
    base = (base or "Translated subtitles").strip() or "Translated subtitles"
    names = {r["name"] for r in db.execute(
        "SELECT name FROM tracks WHERE media_id=?", (media_id,)).fetchall()}
    if base not in names:
        return base
    i = 2
    while f"{base} ({i})" in names:
        i += 1
    return f"{base} ({i})"


def translate_track_to_new_track(db, track_id: int, target_lang: str, *,
                                 source_language: str = "auto",
                                 name: str = "",
                                 report: Progress = None) -> int:
    track = db.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone()
    if not track:
        raise ValueError("track not found")
    segs = db.execute(
        "SELECT * FROM segments WHERE track_id=? ORDER BY idx", (track_id,)).fetchall()
    if not segs:
        raise ValueError("track has no segments")

    actual_source = (source_language or "").strip()
    if not actual_source or actual_source == "auto":
        actual_source = (track["lang_code"] or "").strip() or "auto"
    engine = translate.get_translate_engine()
    if report:
        report(f"translating {len(segs)} subtitle lines with {engine.name}", 10)
    translated = engine.translate_many([s["text"] for s in segs], target_lang,
                                       actual_source)

    base_name = name.strip() or f"{track['name']} -> {target_lang}"
    new_name = _unique_track_name(db, track["media_id"], base_name)
    cur = db.execute("INSERT INTO tracks (media_id, name, lang_code) VALUES (?,?,?)",
                     (track["media_id"], new_name, target_lang))
    new_track_id = cur.lastrowid
    for i, s in enumerate(segs):
        db.execute(
            "INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text) "
            "VALUES (?,?,?,?,?,?)",
            (track["media_id"], new_track_id, i, s["start_s"], s["end_s"],
             translated[i].text))
    if report:
        report(f"created subtitle track '{new_name}'", 100)
    return new_track_id


def translate_recomposition_cuts(db, recomp_id: int, lang_code: str, *,
                                 source_language: str = "auto",
                                 created_by: int | None = None,
                                 overwrite: bool = False,
                                 report: Progress = None) -> list[dict]:
    rows = db.execute("""
        SELECT rc.position, c.id AS cut_id, c.title
        FROM recomp_cuts rc
        JOIN cuts c ON c.id=rc.cut_id
        WHERE rc.recomp_id=?
        ORDER BY rc.position""", (recomp_id,)).fetchall()
    if not rows:
        raise ValueError("this recomposition has no cuts")

    out = []
    for i, row in enumerate(rows):
        if report:
            report(f"translating cut {i + 1}/{len(rows)}", 5 + i / len(rows) * 90)
        existing = None
        if not overwrite:
            existing = db.execute("""
                SELECT id FROM cut_translations
                WHERE cut_id=? AND lang_code=?
                ORDER BY id DESC LIMIT 1""", (row["cut_id"], lang_code)).fetchone()
        if existing:
            out.append({
                "cut_id": row["cut_id"],
                "translation_id": existing["id"],
                "created": False,
            })
            continue
        translation_id, _ = create_cut_translation(
            db, row["cut_id"], lang_code, source="auto",
            source_language=source_language, created_by=created_by)
        out.append({
            "cut_id": row["cut_id"],
            "translation_id": translation_id,
            "created": True,
        })
    if report:
        created = sum(1 for r in out if r["created"])
        report(f"translated {created} cut(s)", 100)
    return out
