"""Cross-source layer: one searchable understanding over EVERY title (films, series, podcasts, sermons…).

collections/<id>/collection.json   {"id", "name", "titles": [...] | ["*"], "description"}
collections/<id>/views/<lens>.json cross-title lenses (items carry composite media ids "title::media")
library.sqlite                     derived index of all titles' lines, claims/facts, points/beats (rebuildable)

Levels of detail for search: title → episode (media) → point (beat) → claim (fact) → line.
Cross-title lenses reuse each title's cached lens, then merge, de-duplicate (re-uploads, repeated sermons) and re-rank.
"""
from __future__ import annotations
import sqlite3
from pathlib import Path
from . import store, views
from .understand import load
from .util import read_json, write_json, slug, sha, now

LEVELS = ("title", "episode", "point", "claim", "line")


# ---------------------------------------------------------------- collections
def cdir(ws, cid) -> Path: return Path(ws.root) / "collections" / cid


def collections(ws):
    out = [read_json(p) for p in sorted((Path(ws.root) / "collections").glob("*/collection.json"))]
    return [{"id": "all", "name": "Everything", "titles": ["*"], "description": "all titles in the library"}] + out


def get_collection(ws, cid):
    if cid == "all": return collections(ws)[0]
    c = read_json(cdir(ws, cid) / "collection.json")
    if not c: raise KeyError(f"no collection {cid}")
    return c


def create_collection(ws, name, titles, description=""):
    cid = slug(name); write_json(cdir(ws, cid) / "collection.json", {"id": cid, "name": name, "titles": titles, "description": description, "created": now()})
    return get_collection(ws, cid)


def member_titles(ws, cid):
    c = get_collection(ws, cid)
    ids = [t["id"] for t in ws.titles()] if "*" in c["titles"] else c["titles"]
    return [t for t in ids if ws.current_version(t)]          # only titles that have an approved understanding


# ---------------------------------------------------------------- library index
def db_path(ws): return Path(ws.root) / "library.sqlite"


def build_index(ws):
    p = db_path(ws); tmp = p.with_suffix(".tmp")
    if tmp.exists(): tmp.unlink()
    db = sqlite3.connect(tmp)
    db.executescript("""
    CREATE TABLE title (id TEXT PRIMARY KEY, name TEXT, kind TEXT, version TEXT, logline TEXT);
    CREATE TABLE line (title TEXT, media TEXT, idx INT, t0 REAL, t1 REAL, speaker TEXT, text TEXT);
    CREATE TABLE beat (title TEXT, id TEXT, media TEXT, l0 INT, l1 INT, t0 REAL, t1 REAL, tier TEXT, score REAL, who TEXT, text TEXT);
    CREATE TABLE fact (title TEXT, id TEXT, media TEXT, l0 INT, l1 INT, t0 REAL, t1 REAL, kind TEXT, actor TEXT, act_type TEXT, target TEXT,
                       topics TEXT, stance TEXT, intensity INT, text TEXT, value TEXT);
    CREATE VIRTUAL TABLE fts USING fts5(level, title, ref, media, speaker, text);
    """)
    for t in ws.titles():
        tid = t["id"]
        if not t.get("understanding_version"): continue
        U = load(ws, tid)
        db.execute("INSERT INTO title VALUES (?,?,?,?,?)", (tid, t["name"], t["kind"], U["version"], U["bible"].get("logline", "")))
        if not store.db_path(ws, tid).exists(): store.build_index(ws, tid)
        tdb = store.connect(ws, tid)
        rows = [(tid, r["media"], r["idx"], r["t0"], r["t1"], r["speaker"], r["text"]) for r in tdb.execute("SELECT * FROM cue")]
        tdb.close()
        db.executemany("INSERT INTO line VALUES (?,?,?,?,?,?,?)", rows)
        db.executemany("INSERT INTO fts VALUES ('line',?,?,?,?,?)", [(r[0], f"{r[1]}:L{r[2]}", r[1], r[5] or "", r[6]) for r in rows])
        db.executemany("INSERT INTO beat VALUES (?,?,?,?,?,?,?,?,?,?,?)", [(tid, b["id"], b["media"], b["lines"][0], b["lines"][1], b["t0"], b["t1"],
                        b.get("tier", "P3"), b.get("score", 0), ", ".join(b["who"]), b["text"]) for b in U["beats"]])
        db.executemany("INSERT INTO fts VALUES ('point',?,?,?,?,?)", [(tid, b["id"], b["media"], ", ".join(b["who"]), b["text"]) for b in U["beats"]])
        db.executemany("INSERT INTO fact VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [(tid, f["id"], f["media"], f["lines"][0], f["lines"][1], f["t0"], f["t1"],
                        f["kind"], f["actor"], f["act_type"], f["target"], "; ".join(f.get("topics", [])), f.get("stance", ""), f.get("intensity", 0),
                        f["text"], f.get("value", "")) for f in U["facts"]])
        db.executemany("INSERT INTO fts VALUES ('claim',?,?,?,?,?)", [(tid, f["id"], f["media"], f["actor"],
                        f"{f['text']} [{'; '.join(f.get('topics', []))}] {f.get('value', '') if f['kind'] != 'act' else ''}") for f in U["facts"]])
    db.commit(); db.close()
    import os; os.replace(tmp, p)
    return p


def search(ws, q, level="claim", speaker="", collection="all", limit=60):
    """Cross-source search at a level of detail. title/episode levels aggregate claim+point+line hits."""
    if not db_path(ws).exists(): build_index(ws)
    titles = member_titles(ws, collection)
    if not titles: return []
    db = sqlite3.connect(db_path(ws)); db.row_factory = sqlite3.Row
    terms = " OR ".join(f'"{w}"' for w in q.replace('"', " ").split() if len(w) > 1)
    if not terms: return []
    ph = ",".join("?" * len(titles))
    base = f"SELECT level, title, ref, media, speaker, text, bm25(fts) AS score FROM fts WHERE fts MATCH ? AND title IN ({ph})"
    args = [terms, *titles]
    if speaker:
        base += " AND speaker LIKE ?"; args.append(f"%{speaker}%")
    names = {r["id"]: r["name"] for r in db.execute("SELECT id, name FROM title")}
    if level in ("point", "claim", "line"):
        rows = db.execute(base + " AND level = ? ORDER BY score LIMIT ?", (*args, level, limit)).fetchall()
        out = [dict(r, title_name=names.get(r["title"], r["title"])) for r in rows]
    else:
        rows = db.execute(base + " ORDER BY score LIMIT 2000", args).fetchall()
        groups = {}
        for r in rows:
            key = r["title"] if level == "title" else f"{r['title']}::{r['media']}"
            g = groups.setdefault(key, {"level": level, "title": r["title"], "title_name": names.get(r["title"], r["title"]),
                                        "media": None if level == "title" else r["media"], "hits": 0, "claims": 0, "score": 0.0, "examples": []})
            g["hits"] += 1; g["score"] += -r["score"]; g["claims"] += r["level"] == "claim"
            if len(g["examples"]) < 3 and r["level"] in ("claim", "point"): g["examples"].append(r["text"][:160])
        out = sorted(groups.values(), key=lambda g: -g["score"])[:limit]
    db.close()
    return out


# ---------------------------------------------------------------- cross-title lenses
def build_lens(ws, job, cid, kind, params, force=False):
    """kinds: topic (speaker/query), trait (actor/query), character (name), overview (P0/P1 spine of every title)."""
    titles = member_titles(ws, cid)
    if not titles: raise RuntimeError("no titles with an approved understanding in this collection")
    key = sha([ws.current_version(t) for t in titles], [ws.corrections(t) for t in titles], kind, params, titles)
    vid = slug(f"{kind}-{params.get('speaker') or params.get('actor') or params.get('name') or ''}-{params.get('query', '')}")
    p = cdir(ws, cid) / "views" / f"{vid}.json"
    old = read_json(p)
    if old and old.get("key") == key and not force: return old
    items, notes = [], []
    for tid in titles:
        if job: job.log(f"lens {kind} on {tid}")
        tname = ws.title(tid)["name"]
        try:
            if kind == "overview":
                v = views.build(ws, job, tid, "main", {})
                its = [i for i in v["items"] if i["tier"] in ("P0", "P1")]
            else:
                v = views.build(ws, job, tid, kind, params, force=force); its = v["items"]
        except (ValueError, KeyError) as e:
            notes.append(f"{tid}: {e}"); continue
        for i in its:
            items.append({**i, "ref": f"{tid}::{i['ref']}", "media": f"{tid}::{i['media']}", "title": tname, "title_id": tid})
    dropped = 0
    if kind in ("topic", "trait"):
        items, dropped = views.dedupe(items, "claim" if kind == "topic" else "text")
    label = {"topic": f"{params.get('speaker', '') + ' on ' if params.get('speaker') else ''}{params.get('query', '')}",
             "trait": f"{params.get('actor', '')}: {params.get('query', '')}", "character": f"{params.get('name', '')} across titles",
             "overview": "Overview"}[kind]
    v = {"id": vid, "kind": kind, "params": params, "collection": cid, "titles": titles, "key": key, "created": now(),
         "title": f"{label} — {get_collection(ws, cid)['name']}", "summary": f"{len(items)} items from {len({i['title_id'] for i in items})} titles",
         "duplicates_removed": dropped, "notes": notes, "items": sorted(items, key=lambda i: (i["title_id"], i["media"], i["t0"]))}
    write_json(p, v)
    return v


def list_lenses(ws, cid):
    out = []
    for p in sorted((cdir(ws, cid) / "views").glob("*.json")):
        v = read_json(p); out.append({k: v.get(k) for k in ("id", "kind", "title", "params", "created", "summary")} | {"items": len(v["items"])})
    return out


def get_lens(ws, cid, vid): return read_json(cdir(ws, cid) / "views" / f"{vid}.json")
