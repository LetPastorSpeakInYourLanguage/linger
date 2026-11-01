"""Multi-pass understanding pipeline (P1 scene cards -> P2 integrate -> beats table).

The LLM never sees video; it sees compact subtitle lines (L### mm:ss [sdh] text). Everything it
returns cites line ids, so beats/moments map to exact [start,end] seconds in the media.
"""
from __future__ import annotations
import json, re
from . import prompts as P
from .llm import LLM, PendingLLM
from .subs import to_prompt_lines
from .select import default_forms

TIER_DEFAULT = {5: "P1", 4: "P2", 3: "P2", 2: "P3", 1: "P3"}


def make_chunks(cues, max_lines=160, min_lines=60):
    """Split at the largest time gap inside each window (scene breaks are usually long silences)."""
    chunks, i, n = [], 0, len(cues)
    while i < n:
        if n - i <= max_lines:
            chunks.append((i, n - 1)); break
        lo, hi = i + min_lines, min(n - 1, i + max_lines)
        cut = max(range(lo, hi), key=lambda k: (round(cues[k + 1].start - cues[k].end, 1), k))  # biggest silence; ties -> longest chunk
        chunks.append((i, cut)); i = cut + 1
    return chunks


def run_p1(cues, llm: LLM, title, max_lines=160, incremental=True):
    chunks = make_chunks(cues, max_lines)
    cards, roster, story = [], [], ""
    for k, (a, b) in enumerate(chunks):
        cid = f"c{k + 1:02d}"
        ctx = f"WORK: {title}\n"
        if incremental and k:
            ctx += "KNOWN CHARACTERS: " + "; ".join(f"{r['name']} ({r.get('who', '')})" for r in roster) + "\n"
            ctx += f"STORY SO FAR: {story}\n"
        prompt = P.SCENE_CARDS_USER.format(context=ctx, chunk_id=cid, first=cues[a].idx, last=cues[b].idx,
                                           lines=to_prompt_lines(cues[a:b + 1]))
        out = llm.complete_json(f"p1_{cid}", P.SCENE_CARDS_SYSTEM, prompt)
        for r in out.get("roster_updates", []):
            if not any(x["name"] == r["name"] for x in roster): roster.append(r)
        story = out.get("story_so_far", story)
        cards.append(out)
    return cards, roster, story


def compact_cards(cards):
    rows = []
    for c in cards:
        for s in c["scenes"]:
            rows.append(f"## {s['id']} L{s['lines'][0]}-L{s['lines'][1]} | {s.get('setting_guess', '')} | {', '.join(s.get('characters', []))}")
            rows.append(f"   {s['summary']}")
            for b in s.get("beats", []):
                rows.append(f"   {b['id']} [{b['kind']}/{b['local_importance']}] L{b['lines'][0]}-L{b['lines'][1]}: {b['text']}")
            for h in s.get("humor", []):
                rows.append(f"   humor L{h['lines'][0]}-L{h['lines'][1]}: {h['joke']}")
            for m in s.get("moments", []):
                rows.append(f"   moment L{m['lines'][0]}-L{m['lines'][1]} ({m['emotion']}/{m['intensity']}): {m['what']}")
    return "\n".join(rows)


def run_p2(cards, llm: LLM, title):
    return llm.complete_json("p2_integrate", P.INTEGRATE_SYSTEM, P.INTEGRATE_USER.format(title=title, cards=compact_cards(cards)))


def build_beats(cards, bible, cues, wps=2.6):
    gl = {b["id"]: b for b in bible.get("beats", [])}
    by_idx = {c.idx: c for c in cues}
    beats = []
    for c in cards:
        for s in c["scenes"]:
            for b in s.get("beats", []):
                g = gl.get(b["id"], {})
                a, z = b["lines"][0], b["lines"][-1]
                ca, cz = by_idx.get(a), by_idx.get(z)
                score = g.get("global_importance", b["local_importance"] * 15)
                words = len(b["text"].split()) * 1.6
                beats.append({"id": b["id"], "scene": s["id"], "text": b["text"], "short": g.get("short", b["text"]),
                              "kind": b["kind"], "lines": [a, z], "t": ca.start if ca else 0,
                              "t_range": [ca.start if ca else 0, cz.end if cz else 0],
                              "score": score, "tier": g.get("tier", TIER_DEFAULT.get(b["local_importance"], "P3")),
                              "requires": g.get("requires", []), "thread": g.get("thread"),
                              "emotion": b.get("emotion", {}), "forms": default_forms(int(words), wps)})
    return beats
