"""The understanding pipeline (T0 -> T1 -> T2). See docs/METHODOLOGY.md.

  P0  ingest            subtitles (+ optional re-sync, shots)                      -> evidence/<media>/
  P1v vision (optional) ONE task per media: keyframes of dialogue gaps -> visual notes   -> visual.jsonl
  P1  cards + ledger    ~220-line chunks, ALL queued at once (Claude carries the story from chunk to chunk);
                        scenes, beats (+ who caused / revealed them), FACT ledger for every character
  P2  integrate         beats only (never raw facts) -> tiers, threads, turning/key points, edges -> bible.json
      (series: per-episode integrate, then series integrate over episode P0/P1)
  G1  review gate       you approve (UI) or autopilot; corrections.jsonl overrides apply on every load
Every "LLM" step is a task in <workspace>/tasks answered by Claude (see tasks.py).
"""
from __future__ import annotations
from pathlib import Path
from . import ingest, media as M, prompts as P, schemas as SC, subs as S
from .tasks import TaskQueue
from .util import write_json, write_jsonl, read_json, read_jsonl, ts, now
from .workspace import profile

TIER_FROM_LOCAL = {5: "P1", 4: "P2", 3: "P2", 2: "P3", 1: "P3", 0: "P3"}


def make_chunks(cues, max_lines=160, min_lines=60):
    chunks, i, n = [], 0, len(cues)
    while i < n:
        if n - i <= max_lines: chunks.append((i, n - 1)); break
        lo, hi = i + min_lines, min(n - 1, i + max_lines)
        cut = max(range(lo, hi), key=lambda k: (round(cues[k + 1].start - cues[k].end, 1), k))
        chunks.append((i, cut)); i = cut + 1
    return chunks


def _visual_lines(visual, t0, t1):
    out = []
    for v in visual:
        if t0 <= v["t0"] <= t1:
            txt = "; ".join(e["text"] for e in v["events"])
            if v.get("onscreen_text"): txt += f" | on-screen text: {v['onscreen_text']}"
            if v.get("is_credits"): txt += " | CREDITS"
            out.append((v["t0"], f"V@{ts(v['t0'])}-{ts(v['t1'])} {txt}"))
    return out


def chunk_text(cues, visual):
    rows = [(c.start, line) for c, line in zip(cues, S.to_prompt_lines(cues).split("\n"))]
    rows += _visual_lines(visual, cues[0].start - 1, cues[-1].end + 1)
    return "\n".join(r for _, r in sorted(rows, key=lambda x: x[0]))


# ---------------------------------------------------------------- P1v vision
def vision_pass(ws, job, llm, tid, m, cues, roster_names, max_gaps=24, min_gap=8.0):
    """One task per media: the middle keyframe of each dialogue-free stretch, labelled with its gap id."""
    if not (m.get("video") and M.have_ffmpeg() and M.has_video_stream(m["video"])): return []
    gaps = [(a.end, b.start, k) for k, (a, b) in enumerate(zip(cues, cues[1:])) if b.start - a.end >= min_gap]
    gaps = sorted(sorted(gaps, key=lambda g: -(g[1] - g[0]))[:max_gaps])
    if not gaps: return []
    kdir = ws.edir(tid, m["id"]) / "keyframes"; imgs, rows = [], []
    for n, (t0, t1, k) in enumerate(gaps):
        gid = f"g{n + 1:02d}"; t = (t0 + t1) / 2; f = kdir / f"{gid}_{int(t)}s.jpg"
        if f.exists() or M.frame(m["video"], t, f, width=512):
            imgs.append(f)
            rows.append(f"{gid} | {ts(t0)}-{ts(t1)} | image {f.name} | before: {cues[k].text[:80]} | after: {cues[k + 1].text[:80] if k + 1 < len(cues) else ''}")
    out = llm.json(f"vision-{m['id']}", P.VISION_SYSTEM,
                   f"Known characters: {', '.join(roster_names) or 'unknown'}\nGAPS (id | time | image | subtitles around it):\n" + "\n".join(rows),
                   SC.VISION_SHEET, images=imgs, hint={"gaps": [g for g in rows]}, summary=f"Describe {len(imgs)} keyframes of {m.get('label') or m['id']} (vision)")
    by_id = {f"g{n + 1:02d}": g for n, g in enumerate(gaps)}
    res = []
    for g in out["gaps"]:
        if g["id"] in by_id:
            t0, t1, k = by_id[g["id"]]
            res.append({"media": m["id"], "t0": round(t0, 2), "t1": round(t1, 2), "after_line": cues[k].idx, **{x: g[x] for x in ("events", "onscreen_text", "setting", "is_credits")}})
    return sorted(res, key=lambda v: v["t0"])


# ---------------------------------------------------------------- P1 cards + ledger
def cards_specs(ws, job, t, m, cues, visual, base_roster):
    """One task per part of a media. Every part of every media is queued at once (see run), so Claude can work
    through a whole season in one sitting."""
    chunks = make_chunks(cues, ws.s.chunk_lines)
    roster_txt = "; ".join(f"{r['name']} ({r.get('who', '')})" for r in base_roster)
    ins = ws.instructions(t["id"], job.dir)
    system = P.DISCOURSE_CARDS_SYSTEM if profile(t) == "discourse" else P.CARDS_SYSTEM
    specs = []
    for k, (a, b) in enumerate(chunks):
        cid = f"{m['id']}-c{k + 1:02d}"
        ctx = f"WORK: {t['name']} — {m.get('label') or m['id']}  (part {k + 1} of {len(chunks)})\n"
        if roster_txt: ctx += f"KNOWN CHARACTERS/SPEAKERS: {roster_txt}\n"
        if k: ctx += (f"CONTINUITY: this continues part {k} ({m['id']}-c{k:02d}). Do the parts in order and carry the story, the names "
                      f"and the roster forward from your previous answers (their answer.json has story_so_far if you need it).\n")
        if ins: ctx += f"NOTES FROM THE USER:\n{ins}\n"
        prompt = P.CARDS_USER.format(context=ctx, chunk_id=cid, first=cues[a].idx, last=cues[b].idx, lines=chunk_text(cues[a:b + 1], visual))
        specs.append(dict(task=f"cards-{t['id']}-{cid}", system=system, prompt=prompt, schema=SC.CARDS,
                          hint={"cues": [c.dict() for c in cues[a:b + 1]], "chunk_id": cid},
                          summary=f"Understand {t['name']} — {m.get('label') or m['id']} part {k + 1}/{len(chunks)} (lines L{cues[a].idx}-L{cues[b].idx})"))
    return chunks, specs


def cards_collect(job, m, chunks, outs, base_roster):
    cards, roster = [], list(base_roster)
    for (k, _), out in zip(enumerate(chunks), outs):
        for r in out.get("roster_updates", []):
            if not any(x["name"].lower() == r["name"].lower() for x in roster): roster.append(r)
        out["chunk_id"], out["media"] = f"{m['id']}-c{k + 1:02d}", m["id"]
        cards.append(out)
    job.log(f"{m['id']}: {len(chunks)} parts understood — {sum(len(s['beats']) for c in cards for s in c['scenes'])} beats, "
            f"{sum(len(s['facts']) for c in cards for s in c['scenes'])} facts")
    return cards, roster, cards[-1].get("story_so_far", "") if cards else ""


def flatten(cards, cues_by_media):
    """Cards -> flat tables. Ids in answers are not trusted: every id is made globally unique (<chunk>-<local id>), and
    references inside the same part (beat_id, caused_by, revealed_by) are remapped; references to earlier parts that
    already use a global id are kept."""
    scenes, beats, facts, speakers = [], [], [], []
    used = set()
    def uid(cid, raw, kind, n):
        base = raw if raw and raw.startswith(cid) else f"{cid}-{raw or kind + str(n)}"
        x, k = base, 1
        while x in used: k += 1; x = f"{base}-{k}"
        used.add(x); return x
    for c in cards:
        mid, cid = c["media"], c["chunk_id"]; by = cues_by_media[mid]
        def span(lines):
            a, z = (list(lines) + list(lines))[:2] if lines else (0, 0)
            ca, cz = by.get(a), by.get(z)
            return a, z, (ca.start if ca else 0.0), (cz.end if cz else (ca.end if ca else 0.0))
        local = {}
        for si, s in enumerate(c["scenes"]):
            s["_id"] = uid(cid, s.get("id"), "s", si + 1)
            for bi, b in enumerate(s["beats"]): local[b.get("id")] = b["_id"] = uid(cid, b.get("id"), "b", bi + 1)
        remap = lambda xs: [local.get(x, x) for x in xs or []]
        for s in c["scenes"]:
            a, z, t0, t1 = span(s["lines"]); sid = s["_id"]
            scenes.append({"id": sid, "media": mid, "lines": [a, z], "t0": t0, "t1": t1, "setting": s["setting"],
                           "characters": s["characters"], "summary": s["summary"]})
            for sp in s.get("speakers", []): speakers.append({"media": mid, "line": sp["line"], "name": sp["name"]})
            for b in s["beats"]:
                a2, z2, u0, u1 = span(b["lines"])
                beats.append({"id": b["_id"], "scene": sid, "media": mid, "lines": [a2, z2], "t0": u0, "t1": u1, "text": b["text"],
                              "kind": b["kind"], "local_importance": b["local_importance"], "emotion": b["emotion"],
                              "intensity": b["intensity"], "who": b["who"], "caused_by": remap(b.get("caused_by")), "revealed_by": remap(b.get("revealed_by"))})
            for fi, f in enumerate(s["facts"]):
                a3, z3, v0, v1 = span(f["lines"])
                facts.append({**f, "id": uid(cid, f.get("id"), "f", fi + 1), "beat_id": local.get(f.get("beat_id"), f.get("beat_id", "")),
                              "scene": sid, "media": mid, "lines": [a3, z3], "t0": v0, "t1": v1, "source": "P1"})
    return scenes, beats, facts, speakers


# ---------------------------------------------------------------- P2 integrate
def _beat_lines(beats, media_label):
    return "\n".join(f"{b['id']} | {media_label.get(b['media'], b['media'])} | L{b['lines'][0]}-L{b['lines'][1]} | "
                     f"{b['kind']}/{b['local_importance']} | {', '.join(b['who'][:4])} | {b['text']}" for b in beats)


def integrate_pass(ws, job, llm, t, beats, roster, media_label):
    disc = profile(t) == "discourse"
    I_SYS = P.DISCOURSE_INTEGRATE_SYSTEM if disc else P.INTEGRATE_SYSTEM
    S_SYS = P.DISCOURSE_INTEGRATE_SYSTEM.replace("from a conversation or talk", "from a whole SERIES of episodes (already ranked per episode)") if disc else P.SERIES_SYSTEM
    roster_txt = "; ".join(f"{r['name']}" + (f" ({', '.join(r.get('aliases', []))})" if r.get("aliases") else "") for r in roster[:120])
    if len({b["media"] for b in beats}) == 1:
        return llm.json("integrate", I_SYS,
                        P.INTEGRATE_USER.format(title=t["name"], scope=t["kind"] if t["kind"] != "series" else "single episode", roster=roster_txt,
                                                beats=_beat_lines(beats, media_label)),
                        SC.INTEGRATE, hint={"beats": beats, "roster": roster}, summary=f"Integrate the whole story of {t['name']} ({len(beats)} beats)")
    # series: per-episode first, then the series pass over each episode's P0/P1 beats
    mids = sorted({b["media"] for b in beats}, key=lambda x: x)
    def ep(mid):
        bs = [b for b in beats if b["media"] == mid]
        return dict(task=f"integrate-{mid}", system=I_SYS,
                    prompt=P.INTEGRATE_USER.format(title=f"{t['name']} — {media_label.get(mid, mid)}", scope="single episode", roster=roster_txt,
                                                   beats=_beat_lines(bs, media_label)),
                    schema=SC.INTEGRATE, hint={"beats": bs, "roster": roster}, summary=f"Integrate {t['name']} {media_label.get(mid, mid)} ({len(bs)} beats)")
    eps = dict(zip(mids, llm.many([ep(mid) for mid in mids])))
    job.log(f"integrated {len(eps)} episodes; running the series pass")
    ep_rank = {x["id"]: x for r in eps.values() for x in r["beats"]}
    top = [b for b in beats if ep_rank.get(b["id"], {}).get("tier") in ("P0", "P1")]
    series = llm.json("integrate-series", S_SYS,
                      P.INTEGRATE_USER.format(title=t["name"], scope=f"series, {len(mids)} episodes", roster=roster_txt, beats=_beat_lines(top, media_label)),
                      SC.INTEGRATE, hint={"beats": top, "roster": roster}, summary=f"Integrate the whole series {t['name']} ({len(top)} key beats)")
    # merge: series ranking wins for the beats it saw; other beats keep episode rank, shifted down one tier
    srank = {x["id"]: x for x in series["beats"]}
    shift = {"P0": "P1", "P1": "P2", "P2": "P3", "P3": "P3"}
    merged = []
    for b in beats:
        if b["id"] in srank: merged.append(srank[b["id"]])
        elif b["id"] in ep_rank:
            e = dict(ep_rank[b["id"]]); e["tier"] = shift.get(e["tier"], "P3"); e["global_importance"] = int(e["global_importance"] * 0.6); merged.append(e)
    series["beats"] = merged
    series["episodes"] = {mid: {"logline": r["logline"], "turning_points": r["turning_points"]} for mid, r in eps.items()}
    series["threads"] = series["threads"] + [dict(th, id=f"{mid}:{th['id']}") for mid, r in eps.items() for th in r["threads"]]
    return series


# ---------------------------------------------------------------- orchestration
def run(ws, job, tid, reingest=False, vision="auto"):
    t = ws.title(tid)
    if not t["media"]: raise RuntimeError("add media (video + subtitles) to the title first")
    llm = TaskQueue(ws, job)
    job.stage("ingest", 0.02)
    cues_by_media, cue_lists = {}, {}
    for m in t["media"]:
        job.check_cancel()
        if reingest or not (ws.edir(tid, m["id"]) / "cues.jsonl").exists():
            ingest.ingest_media(ws, tid, m, log=job.log)
        cs = ingest.cues(ws, tid, m["id"]); cue_lists[m["id"]] = cs; cues_by_media[m["id"]] = {c.idx: c for c in cs}
    version = ws.new_version(tid); vd = ws.vdir(tid, version)
    job.event("version", version=version)
    base_roster = [{"name": c, "aliases": [], "who": "cast"} for c in t.get("cast", [])]
    media_label = {m["id"]: (f"S{m['season']:02d}E{m['episode']:02d}" if m.get("season") else m.get("label") or m["id"]) for m in t["media"]}
    # P1v
    visual = []
    use_vision = vision == "on" or (vision in ("auto", None) and ws.s.vision == "gaps")
    if use_vision:
        job.stage("vision: keyframes of dialogue gaps", 0.06)
        for m in t["media"]:
            visual += vision_pass(ws, job, llm, tid, m, cue_lists[m["id"]], [r["name"] for r in base_roster])
        write_jsonl(vd / "visual.jsonl", visual)
    # P1
    job.stage("P1: scene cards + fact ledger", 0.1)
    all_cards, rosters = [], []
    plan = [(m, *cards_specs(ws, job, t, m, cue_lists[m["id"]], [v for v in visual if v["media"] == m["id"]], base_roster)) for m in t["media"]]
    outs = llm.many([sp for _, _, specs in plan for sp in specs])
    k = 0
    for m, chunks, specs in plan:
        cards, roster, _ = cards_collect(job, m, chunks, outs[k:k + len(specs)], base_roster); k += len(specs)
        all_cards += cards; rosters.append(roster)
    write_json(vd / "cards.json", all_cards)
    roster = []
    for r in [x for rs in rosters for x in rs]:
        hit = next((x for x in roster if x["name"].lower() == r["name"].lower() or r["name"] in x.get("aliases", [])), None)
        if hit: hit["aliases"] = sorted(set(hit.get("aliases", [])) | set(r.get("aliases", [])))
        else: roster.append(dict(r))
    scenes, beats, facts, speakers = flatten(all_cards, cues_by_media)
    for v in visual:
        for k, e in enumerate(v["events"]):
            facts.append({"id": f"{v['media']}-v{int(v['t0'])}-{k}", "kind": "moment", "topics": [], "stance": "", "actor": ", ".join(e.get("who", [])), "act_type": "",
                          "target": "", "cost": 0, "field": "visual", "value": v.get("onscreen_text", ""), "text": e["text"],
                          "lines": [v["after_line"], v["after_line"]], "intensity": 1, "beat_id": "", "scene": "", "media": v["media"],
                          "t0": v["t0"], "t1": v["t1"], "source": "P1v"})
    # P2
    job.stage("P2: global integration (beats only)", 0.55)
    bible = integrate_pass(ws, job, llm, t, beats, roster, media_label)
    ranks = {b["id"]: b for b in bible["beats"]}
    for b in beats:
        r = ranks.get(b["id"])
        b["score"] = r["global_importance"] if r else b["local_importance"] * 15
        b["tier"] = r["tier"] if r else TIER_FROM_LOCAL.get(b["local_importance"], "P3")
        b["thread"] = r["thread"] if r else ""; b["short"] = r["short"] if r else b["text"]
        b["spoiler_level"] = r["spoiler_level"] if r else 1
    edges = [{"src": b["id"], "dst": d, "kind": "requires"} for b in bible["beats"] for d in b["requires"]]
    edges += [{"src": b["id"], "dst": d, "kind": "pays_off"} for b in bible["beats"] for d in b["pays_off"]]
    for b in beats:   # causes were recorded during P1 (no separate pass)
        for kind in ("caused_by", "revealed_by"):
            for who in b.get(kind, []): edges.append({"src": b["id"], "dst": who, "kind": kind})
    # write T1/T2
    write_jsonl(vd / "scenes.jsonl", scenes); write_jsonl(vd / "beats.jsonl", beats); write_jsonl(vd / "facts.jsonl", facts)
    write_jsonl(vd / "edges.jsonl", edges); write_jsonl(vd / "speakers.jsonl", speakers)
    chars = bible.get("characters", [])
    for r in roster:
        if not any(c["name"].lower() == r["name"].lower() for c in chars):
            chars.append({"name": r["name"], "aliases": r.get("aliases", []), "role": "minor", "arc": r.get("who", ""), "importance": 10})
    for c in chars:
        n = c["name"].lower(); al = {a.lower() for a in c.get("aliases", [])} | {n}
        c["facts"] = sum(1 for f in facts if f["actor"].lower() in al or f["target"].lower() in al)
        c["lines"] = sum(1 for s in speakers if s["name"].lower() in al)
    write_json(vd / "characters.json", chars)
    write_json(vd / "bible.json", {k: v for k, v in bible.items() if k != "beats"})
    total_lines = sum(len(v) for v in cue_lists.values())
    covered = sum(len(range(s["lines"][0], s["lines"][1] + 1)) for s in scenes)
    unknown = sum(1 for s in speakers if s["name"] in ("?", "")) / max(1, len(speakers))
    manifest = {"version": version, "created": now(), "job": job.id, "answered_by": ws.s.answerer,
                "media": len(t["media"]), "cues": total_lines, "scenes": len(scenes), "beats": len(beats), "facts": len(facts),
                "visual_notes": len(visual), "edges": len(edges), "coverage": round(min(1.0, covered / max(1, total_lines)), 3),
                "unknown_speaker_rate": round(unknown, 3), "usage": llm.usage}
    write_json(vd / "MANIFEST.json", manifest)
    # G1 review
    job.stage("G1: review understanding", 0.9)
    tps = {x["tp"]: x["beat_id"] for x in bible.get("turning_points", [])}
    by_id = {b["id"]: b for b in beats}
    md = [f"# G1 — understanding review: {t['name']} ({version})", "", f"**Logline:** {bible.get('logline', '')}", "",
          f"beats {len(beats)} · facts {len(facts)} · scenes {len(scenes)} · coverage {manifest['coverage']:.0%} · unknown speakers {unknown:.0%}", "",
          "## Characters", *[f"- **{c['name']}** ({c.get('role', '')}) — {c.get('arc', '')}" for c in chars[:25]], "",
          "## Turning points", *[f"- {k}: {by_id.get(v, {}).get('text', v)}" for k, v in tps.items()], "",
          "## Spine (P0)", *[f"- [{b['media']} L{b['lines'][0]}] {b['text']}" for b in beats if b["tier"] == "P0"], "",
          "Fix anything wrong in the UI (beats/characters → corrections) before approving."]
    job.gate("G1_understanding", "\n".join(md), manifest, rules=[lambda m: m["coverage"] >= 0.7])
    ws.set_current(tid, version)
    from . import store, library
    store.build_index(ws, tid)
    try: library.build_index(ws)
    except Exception as e: job.log(f"library index not rebuilt: {e}")
    job.log(f"understanding {version} ready: {len(beats)} beats, {len(facts)} facts")
    return version


# ---------------------------------------------------------------- loading (with corrections)
def load(ws, tid, version=None):
    vd = ws.vdir(tid, version)
    U = {"version": vd.name, "bible": read_json(vd / "bible.json", {}), "beats": read_jsonl(vd / "beats.jsonl"),
         "facts": read_jsonl(vd / "facts.jsonl"), "edges": read_jsonl(vd / "edges.jsonl"), "scenes": read_jsonl(vd / "scenes.jsonl"),
         "speakers": read_jsonl(vd / "speakers.jsonl"), "characters": read_json(vd / "characters.json", []),
         "visual": read_jsonl(vd / "visual.jsonl"), "manifest": read_json(vd / "MANIFEST.json", {})}
    idx = {**{b["id"]: b for b in U["beats"]}, **{f["id"]: f for f in U["facts"]}, **{f"char:{c['name']}": c for c in U["characters"]}}
    for c in ws.corrections(tid):
        obj = idx.get(c["target"])
        if obj is None: continue
        if c["field"] == "delete": obj["deleted"] = True
        else: obj[c["field"]] = c["value"]
    U["beats"] = [b for b in U["beats"] if not b.get("deleted")]
    U["facts"] = [f for f in U["facts"] if not f.get("deleted")]
    return U
