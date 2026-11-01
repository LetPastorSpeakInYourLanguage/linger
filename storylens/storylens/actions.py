"""Everything you can ask storylens to do, as one function taking a plain dict.

Used by the requests/ folder watcher (Claude writes requests/new/*.json), the CLI and the web app, so the three
behave the same. A request is {"do": <action>, ...}:

  {"do": "add_title", "name": "Grace Church", "kind": "sermon", "folder": "D:/Sermons", "cast": ["Pastor Ruth"]}
  {"do": "scan", "title": "grace-church", "folder": "D:/Sermons/2026"}
  {"do": "understand", "title": "grace-church"}                         (+ "reingest": true, "vision": "on")
  {"do": "lens", "title": "grace-church", "lens": "topic:Pastor Ruth/women and marriage"}
  {"do": "lens", "collection": "all", "lens": "topic:/the meaning of life"}
  {"do": "recap", "title": "my-show", "lens": "main", "style": "recap_channel", "duration": 600, "instructions": "…"}
  {"do": "recap", "collection": "philosophy", "lens": "topic:Alex/free will", "style": "clips", "duration": 300}
  {"do": "decide", "job": "<job id>", "gate": "G2_script", "decision": "approve|revise|reject", "notes": "…"}
  {"do": "send", "job": "<job id>", "text": "less snark"}        {"do": "cancel", "job": "<job id>"}
  {"do": "rerun", "job": "<job id>"}                              (an interrupted/failed job, answers are reused)
  {"do": "find", "query": "meaning of life", "level": "claim", "speaker": "", "collection": "all"}
  {"do": "collection", "name": "Philosophy", "titles": ["within-reason", "long-table"]}
  {"do": "catalog"}
Optional on job actions: "instructions", "autonomy" (gates | autopilot | auto).
"""
from __future__ import annotations
from .jobs import Job

LENS_KINDS = ("main", "character", "thread", "trait", "topic", "pattern", "overview")
RECAP_KEYS = ("lens", "style", "duration", "render", "review", "voice", "hardsub_blur", "hero_seconds")
STYLES = ("recap_channel", "dramatic_comedic", "short_direct", "fan_silent", "detailed_full", "character", "compilation", "clips")


def parse_lens(spec, actor=None, deep=False):
    """'main' | 'character:NAME' | 'thread:ID' | 'trait:[ACTOR/]QUERY' | 'topic:[SPEAKER/]QUERY' | 'pattern:[SPEAKER]' | 'overview',
    or an already-parsed dict."""
    if isinstance(spec, dict):
        if spec.get("kind") not in LENS_KINDS: raise ValueError(f"unknown lens kind {spec.get('kind')!r}; use one of {LENS_KINDS}")
        return dict(spec)
    if not spec or spec == "main": return {"kind": "main"}
    k, _, rest = spec.partition(":")
    if k == "character": return {"kind": "character", "name": rest}
    if k == "thread": return {"kind": "thread", "thread": rest}
    if k == "overview": return {"kind": "overview"}
    if k == "pattern": return {"kind": "pattern", "speaker": rest}
    if k in ("topic", "trait"):
        who, _, q = rest.partition("/") if "/" in rest else ("", "", rest)
        if k == "topic": return {"kind": "topic", "query": q, "speaker": who}
        return {"kind": "trait", "query": q, "actor": who or actor or "", "deep": deep}
    raise ValueError(f"unknown lens {spec!r}; use main | character:NAME | thread:ID | trait:[ACTOR/]QUERY | topic:[SPEAKER/]QUERY | pattern:[SPEAKER] | overview")


ALIVE = ("queued", "running", "waiting_for_claude", "awaiting_review")


def after_understanding(ws, fn, tid=None):
    """Lens/recap requests often arrive together with (or right after) the approval of an understanding — e.g. Claude
    writes [decide G1, recap] in one file. Wait for running understand jobs of that title (or of any title, for a
    collection) instead of failing."""
    import time
    from .jobs import list_jobs
    def run(job):
        said = False
        while True:
            busy = [j for j in list_jobs(ws) if j["kind"] == "understand" and j["state"].get("status") in ALIVE
                    and (tid is None or j["title"] == tid)]
            if not busy: break
            if not said: job.log(f"waiting for {busy[0]['id']} (understanding) to finish"); said = True
            job.check_cancel(); time.sleep(1.0)
        return fn(job)
    return run


def job_for(ws, d):
    """Create the job for a job-kind request. Returns (job, fn) — run with jobs.run_job(job, fn, background=...)."""
    from . import understand, views, recap, library
    do = d["do"]; ins, aut = d.get("instructions", ""), d.get("autonomy")
    col, tid = d.get("collection"), d.get("title")
    if do == "understand":
        if not tid: raise ValueError("understand needs 'title'")
        ws.title(tid)
        job = Job.create(ws, "understand", tid, {"vision": d.get("vision", "auto"), "reingest": bool(d.get("reingest"))}, ins, aut)
        return job, lambda j: understand.run(ws, j, tid, reingest=bool(d.get("reingest")), vision=d.get("vision", "auto"))
    if do == "lens":
        lens = parse_lens(d.get("lens", "main"), deep=bool(d.get("deep"))); kind = lens.pop("kind")
        if not (tid or col): raise ValueError("lens needs 'title' or 'collection'")
        job = Job.create(ws, "lens", col or tid, {"kind": kind, **lens}, ins, aut)
        if col: return job, after_understanding(ws, lambda j: library.build_lens(ws, j, col, kind, lens, force=bool(d.get("force"))))
        return job, after_understanding(ws, lambda j: views.build(ws, j, tid, kind, lens, force=bool(d.get("force"))), tid)
    if do == "recap":
        p = {k: d[k] for k in RECAP_KEYS if k in d}
        p["lens"] = parse_lens(p.get("lens", "main"), deep=bool(d.get("deep")))
        if p.get("style") and p["style"] not in STYLES: raise ValueError(f"unknown style {p['style']!r}; use one of {STYLES}")
        if not (tid or col): raise ValueError("recap needs 'title' or 'collection'")
        job = Job.create(ws, "recap", col or tid, p, ins, aut)
        if col: return job, after_understanding(ws, lambda j: recap.run(ws, j, None, p, collection=col))
        return job, after_understanding(ws, lambda j: recap.run(ws, j, tid, p), tid)
    if do == "rerun":
        old = Job(ws, d["job"]).spec
        if not old: raise ValueError(f"no job {d['job']}")
        req = {"do": old["kind"], "instructions": old.get("instructions", ""), "autonomy": old.get("autonomy"), **old.get("params", {})}
        if old["kind"] == "lens": req["lens"] = {"kind": req.pop("kind"), **{k: v for k, v in old["params"].items() if k != "kind"}}
        is_col = old["title"] == "all" or not any(t["id"] == old["title"] for t in ws.titles())
        req["collection" if is_col else "title"] = old["title"]
        return job_for(ws, req)
    raise ValueError(f"{do!r} is not a job action")


JOB_ACTIONS = ("understand", "lens", "recap", "rerun")


def do_now(ws, d):
    """Immediate (non-job) actions. Returns a JSON-able result."""
    from . import library, catalog
    do = d["do"]
    if do == "add_title":
        cast = d.get("cast", [])
        cast = [c.strip() for c in (cast.split(",") if isinstance(cast, str) else cast) if c.strip()]
        t = ws.create_title(d["name"], d.get("kind", "film"), cast=cast)
        if d.get("folder"): ws.scan_folder(t["id"], d["folder"])
        for m in d.get("media", []): ws.add_media(t["id"], video=m.get("video"), subs=m.get("subs"), season=m.get("season"), episode=m.get("episode"))
        t = ws.title(t["id"]); catalog.write(ws)
        return {"title": t["id"], "media": [{"id": m["id"], "video": m["video"], "subs": m["subs"]} for m in t["media"]]}
    if do == "scan":
        ws.scan_folder(d["title"], d["folder"]); catalog.write(ws); return {"media": len(ws.title(d["title"])["media"])}
    if do == "decide":
        Job(ws, d["job"]).decide(d["gate"], d.get("decision", "approve"), d.get("notes", ""), d.get("edits"), by=d.get("by", "claude"))
        return {"ok": True}
    if do == "send": Job(ws, d["job"]).send(d["text"]); return {"ok": True}
    if do == "cancel": Job(ws, d["job"]).cancel(); return {"ok": True}
    if do == "find":
        rows = library.search(ws, d["query"], d.get("level", "claim"), d.get("speaker", ""), d.get("collection", "all"), d.get("limit", 60))
        return {"results": rows}
    if do == "collection":
        c = library.create_collection(ws, d["name"], d.get("titles", []), d.get("description", "")); catalog.write(ws); return c
    if do == "catalog": catalog.write(ws); return {"ok": True}
    raise ValueError(f"unknown action {do!r}")
