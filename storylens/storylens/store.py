"""Derived SQLite index of the current understanding (rebuildable at any time from the files).

Files are the source of truth; this index makes the UI and lenses fast: FTS5 search over speaker-attributed
lines, facts, beats and scene summaries, plus fact-by-actor/act lookups for trait lenses."""
from __future__ import annotations
import json, sqlite3
from . import ingest
from .understand import load

SCHEMA = """
DROP TABLE IF EXISTS cue; DROP TABLE IF EXISTS fact; DROP TABLE IF EXISTS beat; DROP TABLE IF EXISTS scene; DROP TABLE IF EXISTS edge;
DROP TABLE IF EXISTS fts;
CREATE TABLE cue (media TEXT, idx INT, t0 REAL, t1 REAL, speaker TEXT, text TEXT, PRIMARY KEY(media, idx));
CREATE TABLE scene (id TEXT PRIMARY KEY, media TEXT, l0 INT, l1 INT, t0 REAL, t1 REAL, setting TEXT, characters TEXT, summary TEXT);
CREATE TABLE beat (id TEXT PRIMARY KEY, scene TEXT, media TEXT, l0 INT, l1 INT, t0 REAL, t1 REAL, text TEXT, short TEXT, kind TEXT,
                   tier TEXT, score REAL, thread TEXT, who TEXT, emotion TEXT, intensity INT);
CREATE TABLE fact (id TEXT PRIMARY KEY, scene TEXT, media TEXT, l0 INT, l1 INT, t0 REAL, t1 REAL, kind TEXT, actor TEXT, act_type TEXT,
                   target TEXT, cost INT, field TEXT, value TEXT, text TEXT, intensity INT, beat_id TEXT, source TEXT);
CREATE TABLE edge (src TEXT, dst TEXT, kind TEXT);
CREATE INDEX fact_actor ON fact(actor, act_type);
CREATE VIRTUAL TABLE fts USING fts5(kind, ref, media, text);
"""


def db_path(ws, tid): return ws.tdir(tid) / "index.sqlite"


def connect(ws, tid):
    db = sqlite3.connect(db_path(ws, tid), check_same_thread=False); db.row_factory = sqlite3.Row
    return db


def build_index(ws, tid):
    U = load(ws, tid); t = ws.title(tid)
    db = connect(ws, tid); db.executescript(SCHEMA)
    spk = {(s["media"], s["line"]): s["name"] for s in U["speakers"]}
    for m in t["media"]:
        try: cs = ingest.cues(ws, tid, m["id"])
        except Exception: continue
        rows = [(m["id"], c.idx, c.start, c.end, spk.get((m["id"], c.idx), ""), c.text) for c in cs]
        db.executemany("INSERT INTO cue VALUES (?,?,?,?,?,?)", rows)
        db.executemany("INSERT INTO fts VALUES ('line', ?, ?, ?)", [(f"{r[0]}:L{r[1]}", r[0], (f"{r[4]}: " if r[4] and r[4] != "?" else "") + r[5]) for r in rows])
    db.executemany("INSERT INTO scene VALUES (?,?,?,?,?,?,?,?,?)", [(s["id"], s["media"], s["lines"][0], s["lines"][1], s["t0"], s["t1"], s["setting"],
                                                                     json.dumps(s["characters"]), s["summary"]) for s in U["scenes"]])
    db.executemany("INSERT INTO beat VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   [(b["id"], b["scene"], b["media"], b["lines"][0], b["lines"][1], b["t0"], b["t1"], b["text"], b.get("short", ""), b["kind"],
                     b.get("tier", "P3"), b.get("score", 0), b.get("thread", ""), json.dumps(b["who"]), b["emotion"], b["intensity"]) for b in U["beats"]])
    db.executemany("INSERT INTO fact VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   [(f["id"], f["scene"], f["media"], f["lines"][0], f["lines"][1], f["t0"], f["t1"], f["kind"], f["actor"], f["act_type"],
                     f["target"], f["cost"], f["field"], f["value"], f["text"], f["intensity"], f["beat_id"], f.get("source", "")) for f in U["facts"]])
    db.executemany("INSERT INTO edge VALUES (?,?,?)", [(e["src"], e["dst"], e["kind"]) for e in U["edges"]])
    db.executemany("INSERT INTO fts VALUES ('scene', ?, ?, ?)", [(s["id"], s["media"], s["summary"]) for s in U["scenes"]])
    db.executemany("INSERT INTO fts VALUES ('beat', ?, ?, ?)", [(b["id"], b["media"], b["text"]) for b in U["beats"]])
    db.executemany("INSERT INTO fts VALUES ('fact', ?, ?, ?)", [(f["id"], f["media"], f"{f['actor']} {f['act_type']} {f['target']}: {f['text']}") for f in U["facts"]])
    db.commit(); db.close()


def search(ws, tid, q, kinds=("beat", "fact", "scene", "line"), limit=40):
    if not db_path(ws, tid).exists(): build_index(ws, tid)
    db = connect(ws, tid)
    terms = " OR ".join(f'"{w}"' for w in q.replace('"', " ").split() if len(w) > 1)
    if not terms: return []
    ph = ",".join("?" * len(kinds))
    rows = db.execute(f"SELECT kind, ref, media, text, bm25(fts) AS score FROM fts WHERE fts MATCH ? AND kind IN ({ph}) ORDER BY score LIMIT ?",
                      (terms, *kinds, limit)).fetchall()
    db.close()
    return [dict(r) for r in rows]


def lines(ws, tid, media, l0, l1, pad=0):
    if not db_path(ws, tid).exists(): build_index(ws, tid)
    db = connect(ws, tid)
    rows = db.execute("SELECT idx, t0, t1, speaker, text FROM cue WHERE media=? AND idx BETWEEN ? AND ? ORDER BY idx",
                      (media, l0 - pad, l1 + pad)).fetchall()
    db.close()
    return [dict(r) for r in rows]
