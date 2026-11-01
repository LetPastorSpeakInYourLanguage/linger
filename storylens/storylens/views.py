"""T3 views ("story lenses"): narrow, cached projections of the fact base.

A view = ordered items (beats or facts) with a PER-VIEW salience and tier. The same fact can be P0 in a character
lens and absent from the main lens — importance lives on the (view, item) pair, not on the fact.

  main                 beats ranked by global importance (P2)
  thread:<id>          beats of one storyline / arc
  character:<name>     facts where the character acts or is acted upon + beats they are in, caused or revealed;
                       ranked for THEIR arc by an LLM lens pass (motives, inner life, hidden influence)
  trait:<actor>/<text> "all the times X was a good friend": interpret -> ledger filter (act types, keywords)
                       -> LLM verification of every candidate; deep=True also sweeps the scenes the actor is in
Views are cached in library/<title>/views/<id>/view.json keyed by (understanding version, corrections, params).
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from . import prompts as P, schemas as SC, store
from .understand import load
from .util import read_json, write_json, slug, sha, ts, now
from .llm import LLMRunner


def _alias_set(U, name):
    n = name.lower(); al = {n}
    for c in U["characters"]:
        names = {c["name"].lower(), *[a.lower() for a in c.get("aliases", [])]}
        if n in names: al |= names
    return al


def _item_from_beat(b, salience=None, tier=None, role="", why=""):
    return {"ref": b["id"], "type": "beat", "media": b["media"], "lines": b["lines"], "t0": b["t0"], "t1": b["t1"], "text": b["text"],
            "short": b.get("short", b["text"]), "salience": b.get("score", 0) if salience is None else salience,
            "tier": tier or b.get("tier", "P3"), "role": role, "why": why, "requires": [], "intensity": b.get("intensity", 0)}


def _item_from_fact(f, salience=50, tier="P2", role="", why=""):
    return {"ref": f["id"], "type": "fact", "media": f["media"], "lines": f["lines"], "t0": f["t0"], "t1": f["t1"], "text": f["text"],
            "short": f["text"], "salience": salience, "tier": tier, "role": role, "why": why, "requires": [], "intensity": f.get("intensity", 0),
            "actor": f["actor"], "act_type": f["act_type"]}


def view_id(kind, params):
    p = params.get("name") or params.get("thread") or params.get("query") or ""
    return slug(f"{kind}-{params.get('actor', '')}-{p}") if kind != "main" else "main"


def get_view(ws, tid, vid):
    return read_json(ws.tdir(tid) / "views" / vid / "view.json")


def list_views(ws, tid):
    out = []
    for p in sorted((ws.tdir(tid) / "views").glob("*/view.json")):
        v = read_json(p); out.append({k: v[k] for k in ("id", "kind", "title", "params", "version", "created")} | {"items": len(v["items"])})
    return out


def build(ws, job, tid, kind, params=None, force=False):
    params = params or {}
    U = load(ws, tid)
    key = sha(U["version"], ws.corrections(tid), kind, params)
    vid = view_id(kind, params)
    p = ws.tdir(tid) / "views" / vid / "view.json"
    old = read_json(p)
    if old and old.get("key") == key and not force:
        return old
    llm = LLMRunner(ws, job.dir, cancelled=job.cancelled, log=job.log) if job else None
    fn = {"main": _main, "thread": _thread, "character": _character, "trait": _trait}[kind]
    v = fn(ws, job, llm, tid, U, params)
    v.update({"id": vid, "kind": kind, "params": params, "version": U["version"], "key": key, "created": now()})
    v["items"].sort(key=lambda x: (x["media"], x["t0"]))
    write_json(p, v)
    return v


# ---------------------------------------------------------------- builders
def _main(ws, job, llm, tid, U, params):
    edges = {}
    for e in U["edges"]:
        if e["kind"] == "requires": edges.setdefault(e["src"], []).append(e["dst"])
    items = []
    for b in U["beats"]:
        it = _item_from_beat(b, role="spine" if b.get("tier") == "P0" else "")
        it["requires"] = edges.get(b["id"], []); items.append(it)
    return {"title": "Main story", "summary": U["bible"].get("logline", ""), "items": items}


def _thread(ws, job, llm, tid, U, params):
    th = next((t for t in U["bible"].get("threads", []) if t["id"] == params["thread"]), None)
    if not th: raise KeyError(f"no thread {params['thread']}")
    ids = set(th["beats"])
    return {"title": th["title"], "summary": th["summary"], "items": [_item_from_beat(b) for b in U["beats"] if b["id"] in ids]}


def _character(ws, job, llm, tid, U, params):
    name = params["name"]; al = _alias_set(U, name)
    facts = [f for f in U["facts"] if f["actor"].lower() in al or f["target"].lower() in al
             or any(a in f["actor"].lower() for a in al if len(a) > 3)]
    causal = {e["src"]: e["kind"] for e in U["edges"] if e["kind"] in ("caused_by", "revealed_by", "witnessed_by") and e["dst"].lower() in al}
    beats = [b for b in U["beats"] if any(w.lower() in al for w in b["who"]) or b["id"] in causal]
    cands = {f"{f['id']}": _item_from_fact(f) for f in facts}
    for b in beats: cands[b["id"]] = _item_from_beat(b, role=causal.get(b["id"], ""))
    cl = sorted(cands.values(), key=lambda x: (-(x["intensity"] or 0), x["t0"]))[:260]
    cl.sort(key=lambda x: (x["media"], x["t0"]))
    if not cl: raise ValueError(f"no facts or beats involve '{name}' — check the character name/aliases")
    txt = "\n".join(f"{c['ref']} | {c['media']} {ts(c['t0'])} | {c['type']}{'/' + c['role'] if c['role'] else ''} | {c['text']}" for c in cl)
    char = next((c for c in U["characters"] if c["name"].lower() in al), {"aliases": []})
    out = llm.json(f"lens-character-{slug(name)}", P.CHARACTER_SYSTEM,
                   P.CHARACTER_USER.format(name=name, aliases=", ".join(char.get("aliases", [])) or "-", logline=U["bible"].get("logline", ""), items=txt),
                   SC.CHARACTER_VIEW, role="main", effort_key="view", hint={"items": cl, "name": name})
    items = []
    for r in out["items"]:
        c = cands.get(r["ref"])
        if c: items.append({**c, "salience": r["salience"], "tier": r["tier"], "role": r["role"] or c["role"], "why": r["why"]})
    return {"title": f"{name}'s story", "summary": out["summary"], "arc": out["arc"], "hidden_gems": out["hidden_gems"],
            "candidates": len(cl), "items": items}


def _trait(ws, job, llm, tid, U, params):
    query, actor, deep = params["query"], params.get("actor", ""), params.get("deep", False)
    interp = llm.json(f"lens-trait-map-{slug(query)}", P.TRAIT_MAP_SYSTEM,
                      f"REQUEST: {query}\nCHARACTER (may be empty): {actor}\nReturn description, act_types (from the list), keywords (5-15), actor_required.",
                      SC.TRAIT_MAP, role="main", effort_key="view", hint={"query": query, "actor": actor})
    al = _alias_set(U, actor) if actor else set()
    acts = set(interp["act_types"])
    def actor_ok(f): return not al or f["actor"].lower() in al or any(a in f["actor"].lower() for a in al if len(a) > 3)
    cands = {f["id"]: _item_from_fact(f) for f in U["facts"] if actor_ok(f) and (f["act_type"] in acts or f["kind"] in ("act", "moment") and not acts)}
    kw = " ".join(interp["keywords"])
    if kw:
        hits = store.search(ws, tid, kw, kinds=("fact", "beat"), limit=150)
        fid = {f["id"]: f for f in U["facts"]}; bid = {b["id"]: b for b in U["beats"]}
        for h in hits:
            if h["kind"] == "fact" and h["ref"] in fid and actor_ok(fid[h["ref"]]): cands.setdefault(h["ref"], _item_from_fact(fid[h["ref"]]))
            if h["kind"] == "beat" and h["ref"] in bid and (not al or any(w.lower() in al for w in bid[h["ref"]]["who"])):
                cands.setdefault(h["ref"], _item_from_beat(bid[h["ref"]]))
    if deep and al:   # sweep: every scene the actor appears in, judged directly from its lines
        spk = {(s["media"], s["line"]) for s in U["speakers"] if s["name"].lower() in al}
        for s in U["scenes"]:
            if any(c.lower() in al for c in s["characters"]) or any((s["media"], l) in spk for l in range(s["lines"][0], s["lines"][1] + 1)):
                cands.setdefault(s["id"], {"ref": s["id"], "type": "scene", "media": s["media"], "lines": s["lines"], "t0": s["t0"], "t1": s["t1"],
                                           "text": s["summary"], "short": s["summary"], "salience": 0, "tier": "P3", "role": "", "why": "",
                                           "requires": [], "intensity": 0})
    cl = sorted(cands.values(), key=lambda x: (x["media"], x["t0"]))
    def evidence(c):
        ls = store.lines(ws, tid, c["media"], c["lines"][0], c["lines"][1])
        return " / ".join(f"{(l['speaker'] + ': ') if l['speaker'] and l['speaker'] != '?' else ''}{l['text']}" for l in ls)[:700]
    batches = [cl[i:i + 25] for i in range(0, len(cl), 25)]
    def check(kb):
        k, b = kb
        txt = "\n".join(f"{c['ref']} | {c['media']} {ts(c['t0'])} | {c['text']} | {evidence(c)}" for c in b)
        return llm.json(f"lens-trait-check-{slug(query)}-{k:03d}", P.TRAIT_CHECK_SYSTEM,
                        P.TRAIT_CHECK_USER.format(query=query + (f" (character: {actor})" if actor else ""), interpretation=interp["description"], items=txt),
                        SC.TRAIT_CHECK, role="bulk", effort_key="view", hint={"items": b})
    checks = {}
    with ThreadPoolExecutor(ws.s.max_parallel) as ex:
        for r in ex.map(check, enumerate(batches)):
            for c in r["checks"]: checks[c["ref"]] = c
    items = []
    for c in cl:
        k = checks.get(c["ref"])
        if k and k["match"]:
            s = int(k["strength"])
            items.append({**c, "salience": 25 * s + 8 * (c["intensity"] or 0), "tier": {3: "P0", 2: "P1"}.get(s, "P2"), "role": "instance", "why": k["why"]})
    title = f"{actor + ': ' if actor else ''}{query}"
    return {"title": title, "summary": interp["description"], "interpretation": interp, "candidates": len(cl), "items": items}
