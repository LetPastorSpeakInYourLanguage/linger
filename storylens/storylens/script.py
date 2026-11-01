"""Zoom-in detail harvest, script writing (style cards), and independent verification (research exp12)."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from . import prompts as P, schemas as SC, store
from .util import slug

HERO_SECONDS = {"recap_channel": 20, "dramatic_comedic": 25, "short_direct": 0, "fan_silent": 9999, "detailed_full": 30,
                "character": 25, "compilation": 9999}


def item_lines(ws, tid, it, pad=0):
    ls = store.lines(ws, tid, it["media"], it["lines"][0], it["lines"][1], pad)
    return "\n".join(f"L{l['idx']} {(l['speaker'] + ': ') if l['speaker'] and l['speaker'] != '?' else ''}{l['text']}" for l in ls)


def zoom(ws, llm, tid, items, tag):
    batches = [items[i:i + 15] for i in range(0, len(items), 15)]
    def run(kb):
        k, b = kb
        txt = "\n\n".join(f"ITEM {it['ref']} ({it['media']}): {it['text']}\n{item_lines(ws, tid, it)}" for it in b)
        return llm.json(f"zoom-{tag}-{k:03d}", P.ZOOM_SYSTEM, txt, SC.ZOOM, role="bulk", effort_key="zoom", hint={"items": b})
    details, corrections = [], []
    with ThreadPoolExecutor(ws.s.max_parallel) as ex:
        for r in ex.map(run, enumerate(batches)):
            details += r["details"]; corrections += r["corrections"]
    return details, corrections


def write(ws, llm, tid, U, view, sel, style, target_s, details, instructions, tag, hero_seconds=None):
    hero = HERO_SECONDS.get(style, 20) if hero_seconds is None else hero_seconds
    if target_s: hero = min(hero, int(target_s * 0.45))
    max_words = int(((target_s or 0) - (hero if target_s else 0)) * ws.s.wps) if target_s else 4000
    items = "\n".join(f"{it['ref']} | {it['media']} | L{it['lines'][0]}-L{it['lines'][1]} | {it['tier']} | "
                      f"{it['text'] if it.get('form') != 'micro' else it.get('short', it['text'])}" + (f" (why: {it['why']})" if it.get("why") else "")
                      for it in sel)
    det = "\n".join(f"{d['ref']} | L{d['line']} | {d['detail']}" for d in details) or "-"
    moments = "\n".join(f"{f['media']} | L{f['lines'][0]}-L{f['lines'][1]} | {f['text']}" for f in U["facts"]
                        if f["kind"] == "moment" and f.get("intensity", 0) >= 2 and any(f["media"] == s["media"] and s["t0"] - 120 <= f["t0"] <= s["t1"] + 120 for s in sel))[:6000] or "-"
    lens = f"{view['title']} — {view.get('summary', '')}"
    prompt = P.SCRIPT_USER.format(style=style, style_card=P.STYLE_CARDS.get(style, style), target=f"{target_s} seconds total" if target_s else "no time limit — cover every item",
                                  wps=ws.s.wps, max_words=max_words, hero_seconds=hero, logline=U["bible"].get("logline", ""), lens=lens,
                                  instructions=instructions or "-", items=items, details=det, moments=moments)
    out = llm.json(f"script-{tag}", P.SCRIPT_SYSTEM, prompt, SC.SCRIPT, role="main", effort_key="script",
                   hint={"items": sel, "style": style})
    valid_media = {m["id"] for m in ws.title(tid)["media"]}
    by = {it["ref"]: it for it in sel}
    for s in out["segments"]:
        ref = next((by[r] for r in s.get("refs", []) if r in by), sel[0] if sel else None)
        if s.get("media") not in valid_media and ref: s["media"] = ref["media"]
        if (not s.get("lines") or len(s["lines"]) < 2) and ref: s["lines"] = list(ref["lines"])
        if s["type"] not in ("narration", "hero_clip", "title_card"): s["type"] = "narration"
    out["meta"] = {"style": style, "target_s": target_s, "hero_seconds": hero, "max_words": max_words,
                   "narration_words": sum(len(s["text"].split()) for s in out["segments"] if s["type"] == "narration")}
    return out


def verify(ws, llm, tid, script, tag):
    blocks = []
    for i, s in enumerate(script["segments"]):
        if s["type"] == "hero_clip": continue
        ls = store.lines(ws, tid, s["media"], s["lines"][0], s["lines"][1], pad=1)
        ev = " / ".join(f"L{l['idx']} {l['text']}" for l in ls)[:1500]
        blocks.append(f"SEGMENT {i} ({s['type']}): {s['text']}\nCITED LINES: {ev}")
    if not blocks: return {"checks": [], "leakage": []}
    return llm.json(f"verify-{tag}", P.VERIFY_SYSTEM, "\n\n".join(blocks), SC.VERIFY, role="main", effort_key="verify",
                    hint={"segments": script["segments"]})


def metrics(script, checks, wps):
    v = [c["verdict"] for c in checks.get("checks", [])]
    est = sum(len(s["text"].split()) / wps + 0.7 for s in script["segments"] if s["type"] == "narration") \
        + sum(min(12, 2.5 * (s["lines"][1] - s["lines"][0] + 1)) for s in script["segments"] if s["type"] == "hero_clip") \
        + 2.8 * sum(1 for s in script["segments"] if s["type"] == "title_card")
    return {"segments": len(script["segments"]), "supported": v.count("supported"), "partly": v.count("partly"),
            "unsupported": v.count("unsupported"), "leakage": len(checks.get("leakage", [])), "est_seconds": round(est),
            "target_seconds": script["meta"]["target_s"], "narration_words": script["meta"]["narration_words"]}
