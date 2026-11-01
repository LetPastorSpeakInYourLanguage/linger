"""Persist pipeline output (cues + cards + bible + beats) into the SQLite Story Understanding Layer."""
from __future__ import annotations
import json, os, sqlite3
import numpy as np

SCHEMA = os.path.join(os.path.dirname(__file__), "schema.sql")


def connect(path):
    db = sqlite3.connect(path)
    db.executescript(open(SCHEMA).read())
    return db


def put_vec(db, kind, oid, vec, model="minilm-l6"):
    v = np.asarray(vec, np.float32)
    db.execute("INSERT OR REPLACE INTO embedding VALUES (?,?,?,?,?)", (kind, oid, model, len(v), v.tobytes()))


def load_vecs(db, kind, model="minilm-l6"):
    rows = db.execute("SELECT owner_id, vec FROM embedding WHERE owner_kind=? AND model=?", (kind, model)).fetchall()
    return [r[0] for r in rows], (np.vstack([np.frombuffer(r[1], np.float32) for r in rows]) if rows else np.zeros((0, 384), np.float32))


def ingest_understanding(db, title_id, media_id, cues, U, kind="film", name=None, embed=True):
    b = U["bible"]
    db.execute("INSERT OR REPLACE INTO title VALUES (?,?,?,?,?,?)", (title_id, kind, name or title_id, b.get("logline"), b.get("genre_tone"), json.dumps(b)))
    db.execute("INSERT OR REPLACE INTO media (id,title_id,duration) VALUES (?,?,?)", (media_id, title_id, cues[-1].end if cues else 0))
    spk = {}
    for c in U["cards"]:
        for s in c["scenes"]:
            for k, v in (s.get("speakers") or {}).items(): spk[int(k[1:])] = v
    db.executemany("INSERT OR REPLACE INTO cue VALUES (?,?,?,?,?,?,?,?,?)",
                   [(media_id, c.idx, c.start, c.end, c.text, json.dumps(c.sdh), spk.get(c.idx), None, None) for c in cues])
    for ch in b.get("characters", []):
        db.execute("INSERT OR REPLACE INTO character VALUES (?,?,?,?,?,?,?,?,?)", (f"{title_id}:{ch['name']}", title_id, ch["name"], json.dumps(ch.get("aliases", [])),
                                                                                  ch.get("role"), ch.get("arc"), ch.get("importance"), None, None))
    for t in b.get("threads", []):
        db.execute("INSERT OR REPLACE INTO thread VALUES (?,?,?,?,?)", (f"{title_id}:{t['id']}", title_id, t["title"], t["summary"], t["importance"]))
    by = {c.idx: c for c in cues}
    gb = {x["id"]: x for x in b.get("beats", [])}
    texts = []
    for c in U["cards"]:
        for s in c["scenes"]:
            a, z = s["lines"]
            db.execute("INSERT OR REPLACE INTO scene VALUES (?,?,?,?,?,?,?,?,?,?,?)", (f"{media_id}:{s['id']}", media_id, a, z, by[a].start, by[z].end,
                                                                                     s.get("setting_guess"), json.dumps(s.get("characters", [])), s["summary"], None, None))
            texts.append(("scene", f"{media_id}:{s['id']}", s["summary"]))
            for bt in s.get("beats", []):
                g = gb.get(bt["id"], {}); a2, z2 = bt["lines"]
                bid = f"{media_id}:{bt['id']}"
                db.execute("INSERT OR REPLACE INTO beat VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (bid, f"{media_id}:{s['id']}", media_id, a2, z2, by[a2].start, by[z2].end, bt["text"], g.get("short"), bt["kind"],
                            bt["local_importance"], g.get("global_importance"), g.get("tier"), g.get("thread") and f"{title_id}:{g['thread']}",
                            bt.get("emotion", {}).get("label"), bt.get("emotion", {}).get("intensity"), g.get("spoiler_level"), json.dumps(bt.get("who", []))))
                for r in g.get("requires", []): db.execute("INSERT OR IGNORE INTO beat_edge VALUES (?,?,?)", (bid, f"{media_id}:{r}", "requires"))
                for r in g.get("pays_off", []): db.execute("INSERT OR IGNORE INTO beat_edge VALUES (?,?,?)", (bid, f"{media_id}:{r}", "pays_off"))
                texts.append(("beat", bid, bt["text"]))
            for m in s.get("moments", []):
                a3, z3 = m["lines"]
                db.execute("INSERT INTO moment (media_id,cue0,cue1,t0,t1,kind,what,emotion,intensity) VALUES (?,?,?,?,?,?,?,?,?)",
                           (media_id, a3, z3, by[a3].start, by[z3].end, "moment", m["what"], m["emotion"], m["intensity"]))
    for tp, bid in b.get("turning_points", {}).items():
        db.execute("INSERT INTO turning_point VALUES (?,?,?,?)", (title_id, media_id, tp, f"{media_id}:{bid}"))
    for k, i, t in texts: db.execute("INSERT INTO fts VALUES (?,?,?)", (k, i, t))
    if embed:
        from .embed import encode
        E = encode([t for _, _, t in texts])
        for (k, i, _), v in zip(texts, E): put_vec(db, k, i, v)
    db.commit()
