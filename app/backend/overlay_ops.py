"""Derive overlay caption events from a recomposition's cuts, on the shared
export timeline (so reordering cuts never desyncs the captions)."""
from __future__ import annotations

import json

from . import compose


def _cut_durations_and_starts(db, recomp_id: int):
    rows = db.execute("""
        SELECT rc.position, c.id AS cut_id,
               MIN(s.start_s) AS cut_start, MAX(s.end_s) AS cut_end
        FROM recomp_cuts rc
        JOIN cuts c ON c.id = rc.cut_id
        JOIN cut_segments cs ON cs.cut_id = c.id
        JOIN segments s ON s.id = cs.segment_id
        WHERE rc.recomp_id=?
        GROUP BY rc.position, c.id
        ORDER BY rc.position""", (recomp_id,)).fetchall()
    durations = [max(0.05, float(r["cut_end"]) - float(r["cut_start"])) for r in rows]
    return rows, durations


def gather_events(db, recomp_id: int, source: str, lang_code: str) -> list[dict]:
    """[{start_s, end_s, text}] in recomposition time. source 'subtitles' uses
    each cut's segment text; 'translation' uses its translation for lang_code."""
    rows, durations = _cut_durations_and_starts(db, recomp_id)
    segs_tl = compose.timeline(durations)
    events = []
    for idx, r in enumerate(rows):
        offset = segs_tl[idx].offset_s
        cut_start = float(r["cut_start"])
        seg_rows = db.execute("""
            SELECT s.id, s.start_s, s.end_s, s.text
            FROM cut_segments cs JOIN segments s ON s.id = cs.segment_id
            WHERE cs.cut_id=? ORDER BY cs.position""", (r["cut_id"],)).fetchall()
        for sg in seg_rows:
            text = sg["text"]
            if source == "translation":
                tr = db.execute("""
                    SELECT ts.text FROM cut_translations ct
                    JOIN translation_segments ts ON ts.translation_id = ct.id
                    WHERE ct.cut_id=? AND ct.lang_code=? AND ts.segment_id=?
                    ORDER BY ct.id DESC LIMIT 1""",
                    (r["cut_id"], lang_code, sg["id"])).fetchone()
                text = tr["text"] if tr else ""
            events.append({
                "start_s": offset + (float(sg["start_s"]) - cut_start),
                "end_s": offset + (float(sg["end_s"]) - cut_start),
                "text": text,
            })
    return events


def enabled_overlay_specs(db, recomp_id: int) -> list[dict]:
    """Build [{name, style, events}] for every enabled overlay track — what the
    .ass writer needs to render/burn."""
    specs = []
    for ov in db.execute("""
            SELECT * FROM overlay_tracks WHERE recomp_id=? AND enabled=1
            ORDER BY ord, id""", (recomp_id,)):
        try:
            style = json.loads(ov["style_json"] or "{}")
        except (ValueError, TypeError):
            style = {}
        specs.append({
            "name": ov["name"],
            "style": style,
            "events": gather_events(db, recomp_id, ov["source"], ov["lang_code"]),
        })
    return specs
