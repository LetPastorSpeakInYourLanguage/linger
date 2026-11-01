"""The understanding pipeline (T0 -> T1 -> T2). See docs/METHODOLOGY.md.

  P0  ingest            subtitles (+ optional re-sync, shots)                      -> evidence/<media>/
  P1v vision (optional) keyframes of dialogue gaps -> visual notes                 -> visual.jsonl
  P1  cards + ledger    per ~160-line chunk, incremental (story-so-far, roster)    -> cards/, scenes, beats, FACTS
  P2  integrate         beats only (never raw facts) -> tiers, threads, TPs, edges -> bible.json
      (series: per-episode integrate, then series integrate over episode P0/P1)
  P2c causal links      P0/P1 beats + facts of their scene ±1 -> caused_by / revealed_by / witnessed_by
  G1  review gate       human (or autopilot) approves; corrections.jsonl overrides apply on every load
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from . import ingest, media as M, prompts as P, schemas as SC, subs as S
from .llm import LLMRunner
from .util import write_json, write_jsonl, read_json, read_jsonl, ts, now

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
def vision_pass(ws, job, llm, tid, m, cues, roster_names, max_gaps=40, min_gap=8.0):
    if not (m.get("video") and M.have_ffmpeg()): return []
    gaps = [(a.end, b.start, k) for k, (a, b) in enumerate(zip(cues, cues[1:])) if b.start - a.end >= min_gap]
    info = ingest.media_info(ws, tid, m["id"])
    dur = info.get("duration") or 0
    if dur and dur - cues[-1].end >= min_gap: gaps.append((cues[-1].end, dur, len(cues) - 1))
    gaps = sorted(gaps, key=lambda g: -(g[1] - g[0]))[:max_gaps]
    kdir = ws.edir(tid, m["id"]) / "keyframes"
    out = []
    def one(g):
        t0, t1, k = g
        imgs = []
        for q in (0.2, 0.5, 0.8):
            t = t0 + (t1 - t0) * q; f = kdir / f"k{t:09.1f}.jpg"
            if f.exists() or M.frame(m["video"], t, f): imgs.append(f)
        if not imgs: return None
        before = " / ".join(c.text for c in cues[max(0, k - 2):k + 1]); after = " / ".join(c.text for c in cues[k + 1:k + 3])
        r = llm.json(f"vision-{m['id']}-{int(t0)}", P.VISION_SYSTEM,
                     P.VISION_USER.format(before=before, after=after, roster=", ".join(roster_names) or "unknown", n=len(imgs), t0=ts(t0), t1=ts(t1)),
                     SC.VISION, role="bulk", effort_key="cards", images=imgs, hint={"t0": t0, "t1": t1})
        return {"media": m["id"], "t0": round(t0, 2), "t1": round(t1, 2), "after_line": k, **r}
    with ThreadPoolExecutor(ws.s.max_parallel) as ex:
        for r in ex.map(one, gaps):
            job.check_cancel()
            if r: out.append(r)
    return sorted(out, key=lambda v: v["t0"])


# ---------------------------------------------------------------- P1 cards + ledger
def cards_pass(ws, job, llm, t, m, cues, visual, base_roster):
    by = {c.idx: c for c in cues}
    roster, story, cards = list(base_roster), "", []
    chunks = make_chunks(cues, ws.s.chunk_lines)
    for k, (a, b) in enumerate(chunks):
        job.check_cancel()
        cid = f"{m['id']}-c{k + 1:02d}"
        ctx = f"WORK: {t['name']} — {m.get('label') or m['id']}\n"
        if roster: ctx += "KNOWN CHARACTERS: " + "; ".join(f"{r['name']} ({r.get('who', '')})" for r in roster[:60]) + "\n"
        if story: ctx += f"STORY SO FAR: {story}\n"
        ins = ws.instructions(t["id"], job.dir)
        if ins: ctx += f"NOTES FROM THE USER:\n{ins}\n"
        prompt = P.CARDS_USER.format(context=ctx, chunk_id=cid, first=cues[a].idx, last=cues[b].idx, lines=chunk_text(cues[a:b + 1], visual))
        out = llm.json(f"cards-{cid}", P.CARDS_SYSTEM, prompt, SC.CARDS, role="bulk", effort_key="cards",
                       hint={"cues": [c.dict() for c in cues[a:b + 1]], "chunk_id": cid})
        for r in out.get("roster_updates", []):
            if not any(x["name"].lower() == r["name"].lower() for x in roster): roster.append(r)
        story = out.get("story_so_far") or story
        out["chunk_id"], out["media"] = cid, m["id"]
        cards.append(out)
        job.log(f"{m['id']}: chunk {k + 1}/{len(chunks)} — {sum(len(s['beats']) for s in out['scenes'])} beats, "
                f"{sum(len(s['facts']) for s in out['scenes'])} facts")
    return cards, roster, story


def flatten(cards, cues_by_media):
    scenes, beats, facts, speakers = [], [], [], []
    for c in cards:
        mid = c["media"]; by = cues_by_media[mid]
        def span(lines):
            a, z = (lines + lines)[:2] if lines else (0, 0)
            ca, cz = by.get(a), by.get(z)
            return a, z, (ca.start if ca else 0.0), (cz.end if cz else (ca.end if ca else 0.0))
        for s in c["scenes"]:
            a, z, t0, t1 = span(s["lines"])
            sid = f"{s['id']}" if s["id"].startswith(mid) else f"{c['chunk_id']}-{s['id']}"
            scenes.append({"id": sid, "media": mid, "lines": [a, z], "t0": t0, "t1": t1, "setting": s["setting"],
                           "characters": s["characters"], "summary": s["summary"]})
            for sp in s.get("speakers", []): speakers.append({"media": mid, "line": sp["line"], "name": sp["name"]})
            for b in s["beats"]:
                a2, z2, u0, u1 = span(b["lines"])
                beats.append({"id": b["id"], "scene": sid, "media": mid, "lines": [a2, z2], "t0": u0, "t1": u1, "text": b["text"],
                              "kind": b["kind"], "local_importance": b["local_importance"], "emotion": b["emotion"],
                              "intensity": b["intensity"], "who": b["who"]})
            for f in s["facts"]:
                a3, z3, v0, v1 = span(f["lines"])
                facts.append({**f, "scene": sid, "media": mid, "lines": [a3, z3], "t0": v0, "t1": v1, "source": "P1"})
    return scenes, beats, facts, speakers


# ---------------------------------------------------------------- P2 integrate
def _beat_lines(beats, media_label):
    return "\n".join(f"{b['id']} | {media_label.get(b['media'], b['media'])} | L{b['lines'][0]}-L{b['lines'][1]} | "
                     f"{b['kind']}/{b['local_importance']} | {', '.join(b['who'][:4])} | {b['text']}" for b in beats)


def integrate_pass(ws, job, llm, t, beats, roster, media_label):
    roster_txt = "; ".join(f"{r['name']}" + (f" ({', '.join(r.get('aliases', []))})" if r.get("aliases") else "") for r in roster[:120])
    if t["kind"] != "series" or len({b["media"] for b in beats}) == 1:
        return llm.json("integrate", P.INTEGRATE_SYSTEM,
                        P.INTEGRATE_USER.format(title=t["name"], scope="film" if t["kind"] == "film" else "single episode", roster=roster_txt,
                                                beats=_beat_lines(beats, media_label)),
                        SC.INTEGRATE, role="main", effort_key="integrate", hint={"beats": beats, "roster": roster})
    # series: per-episode first, then the series pass over each episode's P0/P1 beats
    mids = sorted({b["media"] for b in beats}, key=lambda x: x)
    def ep(mid):
        bs = [b for b in beats if b["media"] == mid]
        return mid, llm.json(f"integrate-{mid}", P.INTEGRATE_SYSTEM,
                             P.INTEGRATE_USER.format(title=f"{t['name']} — {media_label.get(mid, mid)}", scope="single episode", roster=roster_txt,
                                                     beats=_beat_lines(bs, media_label)),
                             SC.INTEGRATE, role="main", effort_key="integrate", hint={"beats": bs, "roster": roster})
    with ThreadPoolExecutor(ws.s.max_parallel) as ex:
        eps = dict(ex.map(ep, mids))
    job.log(f"integrated {len(eps)} episodes; running the series pass")
    ep_rank = {x["id"]: x for r in eps.values() for x in r["beats"]}
    top = [b for b in beats if ep_rank.get(b["id"], {}).get("tier") in ("P0", "P1")]
    series = llm.json("integrate-series", P.SERIES_SYSTEM,
                      P.INTEGRATE_USER.format(title=t["name"], scope=f"series, {len(mids)} episodes", roster=roster_txt, beats=_beat_lines(top, media_label)),
                      SC.INTEGRATE, role="main", effort_key="integrate", hint={"beats": top, "roster": roster})
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


# ---------------------------------------------------------------- P2c causal links
def causal_pass(ws, job, llm, beats, facts, scenes, ranks):
    order = {s["id"]: i for i, s in enumerate(scenes)}
    facts_by_scene = {}
    for f in facts: facts_by_scene.setdefault(f["scene"], []).append(f)
    major = [b for b in beats if ranks.get(b["id"], {}).get("tier") in ("P0", "P1")]
    def block(b):
        i = order.get(b["scene"], 0)
        near = [s["id"] for s in scenes[max(0, i - 1):i + 2] if s["media"] == b["media"]]
        fs = [f for sid in near for f in facts_by_scene.get(sid, [])][:60]
        lines = "\n".join(f"  {f['id']} | {f['kind']}:{f['act_type'] or f['field']} | {f['actor']} -> {f['target']} | {f['text']}" for f in fs)
        return f"BEAT {b['id']}: {b['text']}\nFACTS:\n{lines}"
    links = []
    batches = [major[i:i + 8] for i in range(0, len(major), 8)]
    def run(k_batch):
        k, batch = k_batch
        return llm.json(f"causal-{k:03d}", P.CAUSAL_SYSTEM, P.CAUSAL_USER.format(blocks="\n\n".join(block(b) for b in batch)),
                        SC.CAUSAL, role="main", effort_key="causal", hint={"beats": batch, "facts": facts})
    with ThreadPoolExecutor(ws.s.max_parallel) as ex:
        for r in ex.map(run, enumerate(batches)):
            job.check_cancel(); links += r["links"]
    return links


# ---------------------------------------------------------------- orchestration
def run(ws, job, tid, reingest=False, vision="auto"):
    t = ws.title(tid)
    if not t["media"]: raise RuntimeError("add media (video + subtitles) to the title first")
    llm = LLMRunner(ws, job.dir, cancelled=job.cancelled, log=job.log)
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
    use_vision = vision == "on" or (vision == "auto" and llm.backend.name in ("anthropic", "mock"))
    if use_vision:
        job.stage("vision: keyframes of dialogue gaps", 0.06)
        for m in t["media"]:
            visual += vision_pass(ws, job, llm, tid, m, cue_lists[m["id"]], [r["name"] for r in base_roster])
        write_jsonl(vd / "visual.jsonl", visual)
    # P1
    job.stage("P1: scene cards + fact ledger", 0.1)
    all_cards, rosters = [], []
    def per_media(m):
        vis = [v for v in visual if v["media"] == m["id"]]
        return cards_pass(ws, job, llm, t, m, cue_lists[m["id"]], vis, base_roster)
    with ThreadPoolExecutor(ws.s.max_parallel if t["kind"] == "series" else 1) as ex:
        for cards, roster, _ in ex.map(per_media, t["media"]):
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
            facts.append({"id": f"{v['media']}-v{int(v['t0'])}-{k}", "kind": "moment", "actor": ", ".join(e.get("who", [])), "act_type": "",
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
    # P2c
    job.stage("P2c: causal links", 0.75)
    links = causal_pass(ws, job, llm, beats, facts, scenes, ranks)
    for l in links:
        for kind in ("caused_by", "revealed_by", "witnessed_by"):
            for who in l[kind]: edges.append({"src": l["beat_id"], "dst": who, "kind": kind, "evidence": l["evidence_facts"]})
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
    manifest = {"version": version, "created": now(), "job": job.id, "backend": llm.backend.name, "model": ws.s.model, "bulk_model": ws.s.bulk_model,
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
    from . import store
    store.build_index(ws, tid)
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
