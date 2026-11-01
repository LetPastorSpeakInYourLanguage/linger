"""Recap job: lens -> nested selection -> zoom-in -> script -> independent verify -> G2 -> render -> fit -> G3.

params: lens {"kind": main|thread|character|trait, ...}, style, duration (seconds; 0 = unlimited), zoom (bool),
        render (bool), voice, hardsub_blur (bool)."""
from __future__ import annotations
from . import views, script as SCR, render as R, tts as T
from .select import select
from .understand import load
from .llm import LLMRunner
from .util import write_json, write_text, slug, ts


def _gate_md(script, checks, m, view):
    verdict = {c["index"]: c for c in checks.get("checks", [])}
    rows = [f"# G2 — script review: {script.get('title', '')}", f"lens: **{view['title']}** · est {m['est_seconds']}s / target {m['target_seconds'] or '∞'}s · "
            f"supported {m['supported']} · partly {m['partly']} · unsupported {m['unsupported']} · leakage {m['leakage']}", ""]
    for i, s in enumerate(script["segments"]):
        c = verdict.get(i, {})
        flag = {"supported": "✓", "partly": "~", "unsupported": "✗"}.get(c.get("verdict"), "·")
        rows.append(f"{i:02d} {flag} [{s['type']}] {s['media']} L{s['lines'][0]}-L{s['lines'][1]}: {s['text'] or '(original audio)'}")
        if c.get("issue"): rows.append(f"     ↳ {c['issue']}" + (f" — fix: {c['fix']}" if c.get("fix") else ""))
    if checks.get("leakage"): rows += ["", "Outside-knowledge leakage: " + "; ".join(checks["leakage"])]
    return "\n".join(rows)


def run(ws, job, tid, params, collection=None):
    """tid = a title id, or None with collection=<id> for cross-source recaps."""
    p = {"lens": {"kind": "main"}, "style": "recap_channel", "duration": 180, "zoom": True, "render": True, "voice": None, "hardsub_blur": False, **params}
    llm = LLMRunner(ws, job.dir, cancelled=job.cancelled, log=job.log)
    lens = dict(p["lens"]); kind = lens.pop("kind")
    job.stage(f"lens: {kind}", 0.05)
    if collection:
        from . import library
        view = library.build_lens(ws, job, collection, kind, lens)
        U = {"bible": {"logline": view["title"]}, "facts": []}
    else:
        U = load(ws, tid)
        view = views.build(ws, job, tid, kind, lens)
    if not view["items"]: raise RuntimeError("the lens found no items — try another character/trait or a deep sweep")
    write_json(job.artifact("view.json"), view)
    style = p["style"]
    if p.get("style_auto", True) and style == "recap_channel":
        if kind == "trait": style = "compilation"
        if kind == "topic": style = "clips"
    job.stage("selection", 0.2)
    target = int(p["duration"] or 0)
    sel_budget = target * (0.75 if style in ("fan_silent", "compilation", "clips") else 0.85) if target else 0
    sel = select([dict(i) for i in view["items"]], sel_budget, ws.s.wps)
    write_json(job.artifact("selection.json"), sel)
    job.log(f"selected {len(sel)}/{len(view['items'])} items for {target or 'unlimited'}s")
    details, corrections = [], []
    if p["zoom"]:
        job.stage("zoom-in: harvesting details from the subtitles", 0.3)
        details, corrections = SCR.zoom(ws, llm, tid, sel, slug(view["id"]))
        write_json(job.artifact("details.json"), {"details": details, "corrections": corrections})
    instructions = job.instructions()
    if corrections: instructions += "\nCorrections from re-reading the lines:\n" + "\n".join(f"- {c['ref']}: {c['issue']} -> {c['fix']}" for c in corrections)
    tag = slug(f"{view['id']}-{style}-{target}")
    for round_ in range(3):
        job.stage(f"script ({style})" + (f", revision {round_}" if round_ else ""), 0.45)
        sc = SCR.write(ws, llm, tid, U, view, sel, style, target, details, instructions, f"{tag}-r{round_}", p.get("hero_seconds"))
        job.stage("independent verification", 0.55)
        checks = SCR.verify(ws, llm, tid, sc, f"{tag}-r{round_}")
        m = SCR.metrics(sc, checks, ws.s.wps)
        write_json(job.artifact("script.json"), sc); write_json(job.artifact("verify.json"), checks)
        dec = job.gate("G2_script", _gate_md(sc, checks, m, view), m,
                       rules=[lambda m: m["unsupported"] == 0, lambda m: m["leakage"] == 0,
                              lambda m: not m["target_seconds"] or abs(m["est_seconds"] - m["target_seconds"]) <= 0.25 * m["target_seconds"]])
        for k, txt in (dec.get("edits") or {}).items():
            if int(k) < len(sc["segments"]): sc["segments"][int(k)]["text"] = txt
        write_json(job.artifact("script.json"), sc)
        if dec.get("decision") == "revise" and dec.get("notes"):
            instructions += f"\nReviewer notes (revision {round_ + 1}): {dec['notes']}"
            (job.dir / "review" / "G2_script.decision.json").rename(job.dir / "review" / f"G2_script.r{round_}.decision.json")
            continue
        break
    report = [f"# {sc.get('title', 'Recap')}", f"lens: {view['title']} · style {style} · target {target or 'unlimited'}s", "",
              *[f"- [{s['type']}] {s['text'] or '(original audio ' + s['media'] + ' L' + str(s['lines'][0]) + ')'}" for s in sc["segments"]]]
    write_text(job.artifact("report.md"), "\n".join(report))
    srcs = [ws.title(tid)] if tid else [ws.title(x) for x in view["titles"]]
    if p["render"] and any(m.get("video") for t in srcs for m in t["media"]):
        job.stage("voice + render", 0.65)
        tts = T.make_tts(ws, p.get("voice"), log=job.log)
        edl = R.plan(ws, tid, sc, tts, log=job.log)
        edl = R.fit(edl, target, tts, sc, log=job.log)
        write_json(job.artifact("edl.json"), edl)
        out = job.artifact("recap.mp4")
        R.render(ws, tid, edl, out, job.dir / "artifacts" / "parts", hardsub_band=(0.80, 0.97) if p["hardsub_blur"] else None, log=job.log)
        dur = R.duration(edl)
        job.gate("G3_render", f"# G3 — final cut\n\n{out.name}: {ts(dur)} (target {target or '∞'}s). Watch it in the UI, then approve.",
                 {"seconds": round(dur), "target_seconds": target, "voice": tts.name},
                 rules=[lambda m: not m["target_seconds"] or abs(m["seconds"] - m["target_seconds"]) <= 0.1 * m["target_seconds"]])
    elif p["render"]:
        job.log("no video files on this title — script saved, render skipped")
    return sc
