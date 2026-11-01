"""Script writing from the exact lines (style cards), deterministic checks, and the optional Claude review (research exp12)."""
from __future__ import annotations
import re
from . import prompts as P, schemas as SC, store
from .util import slug, split_media

HERO_SECONDS = {"recap_channel": 20, "dramatic_comedic": 25, "short_direct": 0, "fan_silent": 9999, "detailed_full": 30,
                "character": 25, "compilation": 9999, "clips": 9999}


def item_lines(ws, tid, it, pad=0):
    t, m = split_media(tid, it["media"])
    ls = store.lines(ws, t, m, it["lines"][0], it["lines"][1], pad)
    return "\n".join(f"L{l['idx']} {(l['speaker'] + ': ') if l['speaker'] and l['speaker'] != '?' else ''}{l['text']}" for l in ls)


def source_label(ws, tid, it):
    t, m = split_media(tid, it["media"])
    try:
        title = ws.title(t); med = next((x for x in title["media"] if x["id"] == m), {})
        ep = f" S{med['season']:02d}E{med['episode']:02d}" if med.get("season") else (f" · {med.get('label')}" if len(title["media"]) > 1 else "")
        src = f"{title['name']}{ep}"
    except Exception:
        src = it.get("title", "")
    who = it.get("speaker") if it.get("speaker") and it.get("speaker") != "?" else ""
    return " · ".join(x for x in (who + ("?" if who and it.get("speaker_uncertain") else ""), src) if x)


def quotes_ok(text, evidence):
    """Every quoted phrase in the narration must appear (fuzzily) in the cited lines."""
    from difflib import SequenceMatcher
    ev = " ".join(re.findall(r"[a-z0-9']+", evidence.lower()))
    bad = []
    for q in re.findall(r"[\"“]([^\"”]{8,})[\"”]", text):
        qn = " ".join(re.findall(r"[a-z0-9']+", q.lower()))
        if qn and qn not in ev and SequenceMatcher(None, qn, ev).find_longest_match(0, len(qn), 0, len(ev)).size < 0.8 * len(qn):
            bad.append(q)
    return bad


def write(ws, llm, tid, U, view, sel, style, target_s, instructions, tag, hero_seconds=None):
    hero = HERO_SECONDS.get(style, 20) if hero_seconds is None else hero_seconds
    if target_s: hero = min(hero, int(target_s * 0.45))
    max_words = int(((target_s or 0) - (hero if target_s else 0)) * ws.s.wps) if target_s else 4000
    def item_row(it):
        who = f"[{it['speaker']}{'?' if it.get('speaker_uncertain') else ''}] " if it.get("speaker") else ""
        src = f"{it['title']} · " if it.get("title") else ""
        body = it["text"] if it.get("form") != "micro" else it.get("short", it["text"])
        lab = f" (on-screen label: {it['label']})" if it.get("label") else ""
        lines = item_lines(ws, tid, it)
        return (f"{it['ref']} | {src}{it['media']} | L{it['lines'][0]}-L{it['lines'][1]} | {it['tier']} | {who}{body}"
                + (f" (why: {it['why']})" if it.get("why") else "") + lab + ("\n    " + lines.replace("\n", "\n    ") if lines else ""))
    items = "\n".join(item_row(it) for it in sel)
    moments = "\n".join(f"{f['media']} | L{f['lines'][0]}-L{f['lines'][1]} | {f['text']}" for f in U.get("facts", [])
                        if f["kind"] == "moment" and f.get("intensity", 0) >= 2 and any(f["media"] == s["media"] and s["t0"] - 120 <= f["t0"] <= s["t1"] + 120 for s in sel))[:6000] or "-"
    lens = f"{view['title']} — {view.get('summary', '')}"
    prompt = P.SCRIPT_USER.format(style=style, style_card=P.STYLE_CARDS.get(style, style), target=f"{target_s} seconds total" if target_s else "no time limit — cover every item",
                                  wps=ws.s.wps, max_words=max_words, hero_seconds=hero, logline=U["bible"].get("logline", ""), lens=lens,
                                  instructions=instructions or "-", items=items, moments=moments)
    out = llm.json(f"script-{tag}", P.SCRIPT_SYSTEM, prompt, SC.SCRIPT, hint={"items": sel, "style": style},
                   summary=f"Write the {style} script: {view['title']} ({target_s or 'unlimited'} s)")
    valid_media = {m["id"] for m in ws.title(tid)["media"]} if tid else {it["media"] for it in sel}
    by = {it["ref"]: it for it in sel}
    for s in out["segments"]:
        ref = next((by[r] for r in s.get("refs", []) if r in by), sel[0] if sel else None)
        if s.get("media") not in valid_media and ref: s["media"] = ref["media"]
        if (not s.get("lines") or len(s["lines"]) < 2) and ref: s["lines"] = list(ref["lines"])
        if s["type"] not in ("narration", "hero_clip", "title_card"): s["type"] = "narration"
    # talks / cross-source cuts: every clip must say whose words these are: auto lower-third "Speaker · Source S01E02"
    # when the writer left it empty (films and series don't need it)
    from .workspace import profile
    discourse = not tid or profile(ws.title(tid)) == "discourse" or style == "clips"
    for sgm in out["segments"]:
        ref = next((by[r] for r in sgm.get("refs", []) if r in by), None) if sgm["type"] == "hero_clip" and not sgm.get("text") else None
        if ref and (discourse or ref.get("label")):
            if ref: sgm["text"] = (f"{ref['label']} — " if ref.get("label") else "") + source_label(ws, tid, ref)
    out["meta"] = {"style": style, "target_s": target_s, "hero_seconds": hero, "max_words": max_words,
                   "narration_words": sum(len(s["text"].split()) for s in out["segments"] if s["type"] == "narration")}
    return out


def check(ws, tid, script, valid_refs):
    """Deterministic checks (always): citations exist, quotes appear in the cited lines, clips are clips."""
    checks = []
    for i, sgm in enumerate(script["segments"]):
        t, m = split_media(tid, sgm["media"])
        ls = store.lines(ws, t, m, sgm["lines"][0], sgm["lines"][1], pad=1) if sgm.get("lines") else []
        issue = []
        if not ls: issue.append("cited lines not found")
        if sgm.get("refs") and not any(r in valid_refs for r in sgm["refs"]): issue.append("cites no selected item")
        if sgm["type"] == "narration":
            bad = quotes_ok(sgm["text"], " ".join(l["text"] for l in ls))
            if bad: issue.append("quote not in cited lines: " + "; ".join(bad[:2]))
        checks.append({"index": i, "verdict": "unsupported" if "cited lines not found" in issue else "partly" if issue else "supported",
                       "issue": "; ".join(issue), "fix": ""})
    return {"checks": checks, "leakage": []}


def review(ws, llm, tid, script, tag):
    """Optional Claude review task (settings.review or per recap)."""
    blocks = []
    for i, sgm in enumerate(script["segments"]):
        if sgm["type"] == "hero_clip": continue
        t, m = split_media(tid, sgm["media"])
        ls = store.lines(ws, t, m, sgm["lines"][0], sgm["lines"][1], pad=1)
        blocks.append(f"SEGMENT {i} ({sgm['type']}): {sgm['text']}\nCITED LINES: " + " / ".join(f"L{l['idx']} {l['text']}" for l in ls)[:1500])
    if not blocks: return {"checks": [], "leakage": []}
    return llm.json(f"review-{tag}", P.REVIEW_SYSTEM, "\n\n".join(blocks), SC.REVIEW, hint={"segments": script["segments"]},
                    summary="Review the script against its cited lines")


def metrics(script, checks, wps):
    v = [c["verdict"] for c in checks.get("checks", [])]
    est = sum(len(s["text"].split()) / wps + 0.7 for s in script["segments"] if s["type"] == "narration") \
        + sum(min(12, 2.5 * (s["lines"][1] - s["lines"][0] + 1)) for s in script["segments"] if s["type"] == "hero_clip") \
        + 2.8 * sum(1 for s in script["segments"] if s["type"] == "title_card")
    return {"segments": len(script["segments"]), "supported": v.count("supported"), "partly": v.count("partly"),
            "unsupported": v.count("unsupported"), "leakage": len(checks.get("leakage", [])), "est_seconds": round(est),
            "target_seconds": script["meta"]["target_s"], "narration_words": script["meta"]["narration_words"]}
