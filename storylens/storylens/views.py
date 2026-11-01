"""T3 views ("story lenses"): narrow, cached projections of the fact base.

A view = ordered items (beats or facts) with a PER-VIEW salience and tier. The same fact can be P0 in a character
lens and absent from the main lens — importance lives on the (view, item) pair, not on the fact.

  main                 beats ranked by global importance (P2)
  thread:<id>          beats of one storyline / arc
  character:<name>     facts where the character acts or is acted upon + beats they are in, caused or revealed;
                       ranked for THEIR arc by an LLM lens pass (motives, inner life, hidden influence)
  topic:<speaker>/<q>  "what did Pastor X say about women" (discourse): ledger topics + passage search -> LLM verifies
                       relevance, WHO said it and the tightest self-contained clip -> near-duplicates removed
  pattern:<speaker>      HOW a speaker builds ideas: recurring sequences of moves (asks -> reads -> illustrates -> argues ->
                       advises) mined from the ledger; one task names the pattern; items = one example clip per step
  trait:<actor>/<text> "all the times X was a good friend": interpret -> ledger filter (act types, keywords)
                       -> LLM verification of every candidate; deep=True also sweeps the scenes the actor is in
Views are cached in library/<title>/views/<id>/view.json keyed by (understanding version, corrections, params).
"""
from __future__ import annotations
import re
from . import prompts as P, schemas as SC, store
from .understand import load
from .util import read_json, write_json, slug, sha, ts, now
from .tasks import TaskQueue


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
    return slug(f"{kind}-{params.get('actor', '') or params.get('speaker', '')}-{p}") if kind != "main" else "main"


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
    if job is None:   # called outside a job (CLI/library/tests): steps still go to a job folder for auditability
        from .jobs import Job
        job = Job.create(ws, "lens", tid, {"kind": kind, **params}, autonomy="auto")
    llm = TaskQueue(ws, job)
    fn = {"main": _main, "thread": _thread, "character": _character, "trait": _trait, "topic": _topic, "pattern": _pattern}[kind]
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
                   SC.CHARACTER_VIEW, hint={"items": cl, "name": name}, summary=f"Tell {name}'s story: rank {len(cl)} facts and beats (character lens)")
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
                      SC.TRAIT_MAP, hint={"query": query, "actor": actor}, summary=f"Interpret the request \"{query}\" (trait lens)")
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
    def spec(k, b):
        txt = "\n".join(f"{c['ref']} | {c['media']} {ts(c['t0'])} | {c['text']} | {evidence(c)}" for c in b)
        return dict(task=f"lens-trait-check-{slug(query)}-{k:03d}", system=P.TRAIT_CHECK_SYSTEM,
                    prompt=P.TRAIT_CHECK_USER.format(query=query + (f" (character: {actor})" if actor else ""), interpretation=interp["description"], items=txt),
                    schema=SC.TRAIT_CHECK, hint={"items": b}, summary=f"Check candidates {k + 1}/{len(batches)} for \"{query}\" ({actor or 'anyone'})")
    checks = {}
    for r in llm.many([spec(k, b) for k, b in enumerate(batches)]):     # all batches queued at once for Claude
        for c in r["checks"]: checks[c["ref"]] = c
    items = []
    for c in cl:
        k = checks.get(c["ref"])
        if k and k["match"]:
            s = int(k["strength"])
            items.append({**c, "salience": 25 * s + 8 * (c["intensity"] or 0), "tier": {3: "P0", 2: "P1"}.get(s, "P2"), "role": "instance", "why": k["why"]})
    items = merge_overlaps(items)
    title = f"{actor + ': ' if actor else ''}{query}"
    return {"title": title, "summary": interp["description"], "interpretation": interp, "candidates": len(cl), "items": items}


# ---------------------------------------------------------------- topic lens (discourse) + de-duplication
def _norm(t): return " ".join(re.findall(r"[a-z0-9']+", (t or "").lower()))


def merge_overlaps(items):
    """One instance per moment: a beat and the facts inside its lines are the same moment for a compilation.
    Keeps the most salient item and widens it to cover the others."""
    kept = []
    for it in sorted(items, key=lambda x: (-x["salience"], x["type"] != "beat")):
        a, z = it["lines"]
        hit = next((k for k in kept if k["media"] == it["media"] and a <= k["lines"][1] and z >= k["lines"][0]), None)
        if hit: hit.setdefault("merged", []).append(it["ref"])
        else: kept.append(dict(it))
    return sorted(kept, key=lambda x: (x["media"], x["t0"]))


def dedupe(items, text_key="claim", threshold=0.8):
    """Drop near-duplicate statements (same thing said twice, re-uploads, repeated sermons). Keeps the most salient."""
    from difflib import SequenceMatcher
    kept, dropped = [], 0
    for it in sorted(items, key=lambda x: -x["salience"]):
        a = _norm(it.get(text_key) or it["text"])
        if any(SequenceMatcher(None, a, _norm(k.get(text_key) or k["text"])).ratio() >= threshold for k in kept
               if (k.get("speaker") or "").lower() == (it.get("speaker") or "").lower() or not it.get("speaker")):
            dropped += 1; continue
        kept.append(it)
    return kept, dropped


def topic_candidates(ws, tid, U, interp, al, limit=150):
    terms = {t.lower() for t in interp["topics"]} | {k.lower() for k in interp["keywords"]}
    def speaker_ok(name): return not al or not name or name in ("?", "") or name.lower() in al or any(a in name.lower() for a in al if len(a) > 3)
    cands = {}
    for f in U["facts"]:
        hay = " ".join(f.get("topics", [])).lower() + " " + f["text"].lower()
        if any(t in hay for t in terms) and speaker_ok(f["actor"]):
            it = _item_from_fact(f); it["topics"] = f.get("topics", []); cands[f["id"]] = it
    hits = store.search(ws, tid, " ".join(sorted(terms)), kinds=("line", "fact", "beat"), limit=limit)
    for h in hits:
        if h["kind"] != "line": continue
        media, l = h["ref"].split(":L"); l = int(l)
        if any(c["media"] == media and c["lines"][0] - 2 <= l <= c["lines"][1] + 2 for c in cands.values()): continue
        ls = store.lines(ws, tid, media, l, l, pad=3)
        if not ls: continue
        ref = f"{media}:P{ls[0]['idx']}"
        cands[ref] = {"ref": ref, "type": "passage", "media": media, "lines": [ls[0]["idx"], ls[-1]["idx"]], "t0": ls[0]["t0"], "t1": ls[-1]["t1"],
                      "text": " ".join(x["text"] for x in ls)[:300], "short": "", "salience": 0, "tier": "P3", "role": "", "why": "",
                      "requires": [], "intensity": 0, "actor": ""}
    return sorted(cands.values(), key=lambda x: (x["media"], x["t0"]))[: limit * 2]


def _topic(ws, job, llm, tid, U, params):
    query, speaker = params["query"], params.get("speaker", "")
    interp = llm.json(f"lens-topic-map-{slug(speaker + '-' + query)}", P.TOPIC_MAP_SYSTEM,
                      f"REQUEST: {query}\nSPEAKER (may be empty): {speaker}\nKNOWN SPEAKERS: {', '.join(c['name'] for c in U['characters'][:40])}",
                      SC.TOPIC_MAP, hint={"query": query, "speaker": speaker}, summary=f"Interpret the request: what {speaker or 'anyone'} said about \"{query}\" (topic lens)")
    al = _alias_set(U, speaker) | {x.lower() for x in interp.get("speakers", []) if x} if speaker else set()
    cl = topic_candidates(ws, tid, U, interp, al)
    items = verify_topic(ws, llm, query, speaker, interp, cl, al, lambda c: (tid, c["media"]))
    items, dropped = dedupe(items)
    title = f"{speaker + ' on ' if speaker else ''}{query}"
    return {"title": title, "summary": interp["description"], "interpretation": interp, "candidates": len(cl), "duplicates_removed": dropped, "items": items}


def verify_topic(ws, llm, query, speaker, interp, cl, al, where):
    def evidence(c):
        t, media = where(c)
        ls = store.lines(ws, t, media, c["lines"][0], c["lines"][1], pad=2)
        return " ".join(f"[L{l['idx']}{(' ' + l['speaker']) if l['speaker'] and l['speaker'] != '?' else ''}] {l['text']}" for l in ls)[:1400]
    batches = [cl[i:i + 20] for i in range(0, len(cl), 20)]
    def spec(k, b):
        txt = "\n".join(f"{c['ref']} | {c.get('title', '')}{c['media']} | {ts(c['t0'])} | {evidence(c)}" for c in b)
        return dict(task=f"lens-topic-check-{slug(speaker + '-' + query)}-{k:03d}", system=P.TOPIC_CHECK_SYSTEM,
                    prompt=P.TOPIC_CHECK_USER.format(query=query, speaker=speaker or "(anyone)", interpretation=interp["description"], items=txt),
                    schema=SC.TOPIC_CHECK, hint={"items": b, "query": query, "speaker": speaker},
                    summary=f"Check passages {k + 1}/{len(batches)}: what {speaker or 'anyone'} said about \"{query}\"")
    checks = {}
    for r in llm.many([spec(k, b) for k, b in enumerate(batches)]):     # all batches queued at once for Claude
        for c in r["checks"]: checks[c["ref"]] = c
    items = []
    for c in cl:
        k = checks.get(c["ref"])
        if not k or not k["relevant"]: continue
        who = (k["speaker"] or "").strip()
        match = not al or who.lower() in al or any(a in who.lower() for a in al if len(a) > 3)
        if al and not match and k["speaker_confident"]: continue          # confidently someone else
        s_ = int(k["strength"])
        l0, l1 = k["first_line"], k["last_line"]
        if not (c["lines"][0] - 6 <= l0 <= l1 <= c["lines"][1] + 6): l0, l1 = c["lines"]
        items.append({**c, "lines": [l0, l1], "claim": k["claim"], "text": k["claim"] or c["text"], "stance": k["stance"],
                      "speaker": who or c.get("actor", ""), "speaker_uncertain": not (match and k["speaker_confident"]),
                      "salience": 25 * s_ + (10 if k["speaker_confident"] else 0) + 5 * (c.get("intensity") or 0),
                      "tier": {3: "P0", 2: "P1"}.get(s_, "P2"), "role": "statement", "why": k["stance"]})
    return items


# ---------------------------------------------------------------- pattern lens (rhetoric / homiletics)
MOVE = {"asks": "question", "answers": "answer", "reads": "reading", "cites": "citation", "quotes": "citation", "illustrates": "story",
        "argues": "argument", "asserts": "claim", "advises": "application", "prays": "prayer", "confesses": "confession", "jokes": "humor",
        "agrees": "response", "disagrees": "response", "predicts": "claim"}


def _pattern(ws, job, llm, tid, U, params, top=6):
    """Mine recurring move sequences in a speaker's points, let Claude name the pattern, return one clip per step."""
    speaker = params.get("speaker", ""); al = _alias_set(U, speaker) if speaker else set()
    def mine(f): return not al or f["actor"].lower() in al or any(a in f["actor"].lower() for a in al if len(a) > 3)
    by_beat = {}
    for f in sorted(U["facts"], key=lambda f: (f["media"], f["t0"])):
        mv = MOVE.get(f["act_type"]) or ("story" if f["kind"] == "story" else None)
        if mv and f.get("beat_id") and mine(f): by_beat.setdefault(f["beat_id"], []).append((mv, f))
    seqs = {}
    for bid, moves in by_beat.items():
        seq = [m for i, (m, _) in enumerate(moves) if i == 0 or m != moves[i - 1][0]]
        for n in (5, 4, 3):
            for i in range(len(seq) - n + 1):
                seqs.setdefault(tuple(seq[i:i + n]), set()).add(bid)
    ranked = sorted(((k, v) for k, v in seqs.items() if len(v) >= 2), key=lambda kv: (-len(kv[1]) * len(kv[0]), -len(kv[0])))[:top]
    if not ranked: raise ValueError("not enough structured moves found — the pattern lens needs a discourse title (podcast/sermon/lecture) with claims")
    beats = {b["id"]: b for b in U["beats"]}
    rows = []
    for k, ids in ranked:
        ex = sorted(ids, key=lambda i: -beats.get(i, {}).get("score", 0))[:3]
        rows.append(f"PATTERN {' -> '.join(k)} (in {len(ids)} points); examples: " + "; ".join(f"{i}: {beats[i]['text'][:120]}" for i in ex if i in beats))
    out = llm.json(f"lens-pattern-{slug(speaker or 'all')}", P.PATTERN_SYSTEM, f"SPEAKER: {speaker or '(main speaker)'}\n" + "\n".join(rows),
                   SC.PATTERN, hint={"ranked": [list(k) for k, _ in ranked], "examples": [sorted(v)[:3] for _, v in ranked]},
                   summary=f"Name {speaker or 'the speaker'}'s way of building ideas (pattern lens)")
    best = [b for b in out["best_examples"] if b in by_beat] or sorted(ranked[0][1], key=lambda i: -beats.get(i, {}).get("score", 0))[:2]
    pattern = list(ranked[0][0]); labels = {s_["move"]: s_["label"] for s_ in out["steps"]}
    items = []
    for bid in best[:3]:
        moves = by_beat[bid]; step = 0
        for mv in pattern:
            hit = next(((m, f) for m, f in moves[step:] if m == mv), None)
            if not hit: continue
            step = moves.index(hit) + 1; f = hit[1]
            it = _item_from_fact(f, salience=70, tier="P1", role=mv, why=labels.get(mv, mv))
            it["label"] = labels.get(mv, mv); it["speaker"] = f["actor"]; it["example"] = bid
            items.append(it)
    return {"title": f"How {speaker or 'the speaker'} builds ideas: {out['name']}", "summary": out["description"], "pattern": pattern,
            "steps": out["steps"], "patterns_found": [{"moves": list(k), "points": len(v)} for k, v in ranked], "items": items}
