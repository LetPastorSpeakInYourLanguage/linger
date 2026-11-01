"""storylens command line. Run `storylens --help`. The web app: `storylens serve`."""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
from . import config as C, __version__
from .workspace import Workspace
from .jobs import Job, run_job, list_jobs, pending_steps


def _ws(a):
    s = C.load(a.workspace)
    if getattr(a, "llm", None): s.llm_backend = a.llm
    return Workspace(s).init()


def _interactive_gate(name, md, metrics):
    print("\n" + "=" * 78 + f"\n{md}\n" + "=" * 78)
    if not sys.stdin.isatty():
        print(f"(waiting for a decision: storylens approve <job> {name}  — or approve in the web UI)"); return None
    ans = input(f"[{name}] approve (a) / revise with notes (r) / reject (x) / decide later in the UI (enter): ").strip().lower()
    if ans == "a": return {"decision": "approve"}
    if ans == "x": return {"decision": "reject"}
    if ans == "r": return {"decision": "revise", "notes": input("notes for the revision: ")}
    return None


def _run(ws, kind, tid, params, fn, a):
    job = Job.create(ws, kind, tid, params, instructions=getattr(a, "instructions", "") or "",
                     autonomy="auto" if getattr(a, "yes", False) else "autopilot" if getattr(a, "autopilot", False) else None)
    job.on_gate = _interactive_gate
    print(f"job {job.id}  (folder: {job.dir})")
    run_job(job, lambda j: fn(j))
    st = job.state; print(f"→ {st['status']}: {st.get('message', '')}")
    arts = sorted(p.name for p in (job.dir / "artifacts").glob("*") if p.is_file())
    if arts: print("artifacts:", ", ".join(arts), f"\n  in {job.dir / 'artifacts'}")
    return job


def parse_lens(spec, actor=None, deep=False):
    if not spec or spec == "main": return {"kind": "main"}
    k, _, rest = spec.partition(":")
    if k == "character": return {"kind": "character", "name": rest}
    if k == "thread": return {"kind": "thread", "thread": rest}
    if k == "topic":
        sp, _, q = rest.partition("/") if "/" in rest else ("", "", rest)
        return {"kind": "topic", "query": q, "speaker": sp}
    if k == "overview": return {"kind": "overview"}
    if k == "trait":
        act, _, q = rest.partition("/") if "/" in rest else ("", "", rest)
        return {"kind": "trait", "query": q, "actor": act or actor or "", "deep": deep}
    raise SystemExit(f"unknown lens {spec}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="storylens", description="Subtitle-first story understanding and recaps.")
    ap.add_argument("--workspace", "-w", help="workspace folder (default: $STORYLENS_WORKSPACE or ~/storylens-workspace)")
    ap.add_argument("--llm", choices=["auto", "anthropic", "folder", "mock"], help="override the LLM backend for this command")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create the workspace")
    x = sub.add_parser("add", help="add a title (film or series) with media")
    x.add_argument("name"); x.add_argument("--video", action="append", default=[]); x.add_argument("--subs", action="append", default=[])
    x.add_argument("--folder", help="scan a folder: pairs videos/audio with .srt/.vtt/.ass/.txt transcripts by name")
    x.add_argument("--kind", choices=["film", "series", "podcast", "talkshow", "sermon", "lecture"], default="film")
    x.add_argument("--cast", default="", help="comma-separated character names (optional, improves naming)")
    sub.add_parser("titles", help="list titles")
    x = sub.add_parser("understand", help="build the understanding (P1 cards+ledger, P2, P2c) — gate G1")
    x.add_argument("title"); x.add_argument("--autopilot", action="store_true", help="auto-approve gates whose metrics pass")
    x.add_argument("--yes", action="store_true", help="approve every gate (unattended)"); x.add_argument("--reingest", action="store_true")
    x.add_argument("--vision", choices=["auto", "on", "off"], default="auto"); x.add_argument("--instructions", default="")
    x = sub.add_parser("lens", help="build a lens: main | character:NAME | thread:ID | trait:[ACTOR/]QUERY | topic:[SPEAKER/]QUERY "
                                    "(with --collection: title arg is ignored; also overview)")
    x.add_argument("title"); x.add_argument("spec"); x.add_argument("--deep", action="store_true"); x.add_argument("--force", action="store_true")
    x.add_argument("--collection", help="cross-source lens over a collection ('all' = every title)")
    x = sub.add_parser("recap", help="make a recap (script + verify + render) — gates G2/G3")
    x.add_argument("title"); x.add_argument("--lens", default="main"); x.add_argument("--deep", action="store_true")
    x.add_argument("--style", default="recap_channel", choices=["recap_channel", "dramatic_comedic", "short_direct", "fan_silent", "detailed_full", "character", "compilation", "clips"])
    x.add_argument("--collection", help="cross-source recap over a collection ('all' = every title); title arg is ignored")
    x.add_argument("--duration", type=int, default=180, help="seconds; 0 = unlimited"); x.add_argument("--no-render", action="store_true")
    x.add_argument("--no-zoom", action="store_true"); x.add_argument("--voice"); x.add_argument("--hardsub-blur", action="store_true")
    x.add_argument("--autopilot", action="store_true"); x.add_argument("--yes", action="store_true"); x.add_argument("--instructions", default="")
    x = sub.add_parser("search", help="full-text search the understanding"); x.add_argument("title"); x.add_argument("query")
    x = sub.add_parser("find", help="search ALL sources at a level of detail: title|episode|point|claim|line")
    x.add_argument("query"); x.add_argument("--level", default="claim", choices=["title", "episode", "point", "claim", "line"])
    x.add_argument("--speaker", default=""); x.add_argument("--collection", default="all")
    x = sub.add_parser("collection", help="collections of titles for cross-source lenses/recaps")
    x.add_argument("action", choices=["list", "create", "reindex"]); x.add_argument("name", nargs="?"); x.add_argument("--titles", default="*")
    sub.add_parser("jobs", help="list jobs")
    sub.add_parser("pending", help="list LLM steps waiting for an agent/human answer (folder backend)")
    x = sub.add_parser("approve", help="decide a review gate"); x.add_argument("job"); x.add_argument("gate")
    x.add_argument("--revise", help="notes: ask for a revision"); x.add_argument("--reject", action="store_true")
    x = sub.add_parser("send", help="send an instruction to a running job"); x.add_argument("job"); x.add_argument("text")
    x = sub.add_parser("cancel", help="cancel a job"); x.add_argument("job")
    x = sub.add_parser("serve", help="start the web app"); x.add_argument("--port", type=int); x.add_argument("--host")
    x = sub.add_parser("demo", help="create a demo title from the bundled sample and run it with the mock LLM")
    x.add_argument("--real", action="store_true", help="use the configured LLM backend instead of the mock")
    a = ap.parse_args(argv)
    ws = _ws(a)

    if a.cmd == "init":
        print(f"workspace ready: {ws.root}\nsettings: {ws.root / 'settings.json'}  (llm_backend={ws.s.llm_backend}, model={ws.s.model})")
    elif a.cmd == "add":
        t = ws.create_title(a.name, a.kind, cast=[c.strip() for c in a.cast.split(",") if c.strip()])
        if a.folder: ws.scan_folder(t["id"], a.folder)
        for i in range(max(len(a.video), len(a.subs))):
            ws.add_media(t["id"], video=a.video[i] if i < len(a.video) else None, subs=a.subs[i] if i < len(a.subs) else None)
        t = ws.title(t["id"]); print(f"title '{t['id']}' ({t['kind']}) with {len(t['media'])} media")
        for m in t["media"]: print(f"  {m['id']}: video={m['video']} subs={m['subs']}")
    elif a.cmd == "titles":
        for t in ws.titles(): print(f"{t['id']:30s} {t['kind']:7s} media={len(t['media'])} understanding={t['understanding_version']}")
    elif a.cmd == "understand":
        from . import understand
        _run(ws, "understand", a.title, {"vision": a.vision}, lambda j: understand.run(ws, j, a.title, reingest=a.reingest, vision=a.vision), a)
    elif a.cmd == "lens":
        from . import views, library
        lens = parse_lens(a.spec, deep=a.deep); kind = lens.pop("kind")
        job = Job.create(ws, "lens", a.collection or a.title, {"kind": kind, **lens})
        v = library.build_lens(ws, job, a.collection, kind, lens, force=a.force) if a.collection else views.build(ws, job, a.title, kind, lens, force=a.force)
        print(f"{v['title']} — {len(v['items'])} items\n{v.get('summary', '')}")
        for it in v["items"]:
            who = f"[{it['speaker']}{'?' if it.get('speaker_uncertain') else ''}] " if it.get("speaker") else ""
            print(f"  [{it['tier']}] {it['media']} L{it['lines'][0]:>4} sal={it['salience']:>3} {who}{it['text'][:110]}")
    elif a.cmd == "recap":
        from . import recap
        params = {"lens": parse_lens(a.lens, deep=a.deep), "style": a.style, "duration": a.duration, "render": not a.no_render,
                  "zoom": not a.no_zoom, "voice": a.voice, "hardsub_blur": a.hardsub_blur}
        if a.collection:
            _run(ws, "recap", a.collection, params, lambda j: recap.run(ws, j, None, params, collection=a.collection), a)
        else:
            _run(ws, "recap", a.title, params, lambda j: recap.run(ws, j, a.title, params), a)
    elif a.cmd == "search":
        from . import store
        for r in store.search(ws, a.title, a.query): print(f"{r['kind']:6s} {r['ref']:28s} {r['text'][:110]}")
    elif a.cmd == "find":
        from . import library
        for r in library.search(ws, a.query, a.level, a.speaker, a.collection):
            if a.level in ("title", "episode"):
                print(f"{r['title_name'][:30]:30s} {r['media'] or '':6s} hits={r['hits']:3d} claims={r['claims']:3d}  {' | '.join(r['examples'])[:120]}")
            else:
                print(f"{r['title_name'][:24]:24s} {r['ref']:22s} {(r['speaker'] or '')[:14]:14s} {r['text'][:100]}")
    elif a.cmd == "collection":
        from . import library
        if a.action == "create":
            c = library.create_collection(ws, a.name, [t.strip() for t in a.titles.split(",") if t.strip()]); print("created", c["id"], c["titles"])
        elif a.action == "reindex":
            print("library index:", library.build_index(ws))
        else:
            for c in library.collections(ws): print(f"{c['id']:24s} {c['name']:30s} {', '.join(c['titles'])}")
    elif a.cmd == "jobs":
        for j in list_jobs(ws): print(f"{j['id']:38s} {j['kind']:10s} {j['title']:24s} {j['state'].get('status', ''):16s} {j['state'].get('stage', '')}")
    elif a.cmd == "pending":
        ps = pending_steps(ws)
        print("\n".join(ps) if ps else "no steps waiting"); print("\nAnswer: write response.json (matching schema.json) in each folder. See AGENTS.md.")
    elif a.cmd == "approve":
        job = Job(ws, a.job)
        job.decide(a.gate, "reject" if a.reject else "revise" if a.revise else "approve", a.revise or "")
        print("decision written")
    elif a.cmd == "send":
        Job(ws, a.job).send(a.text); print("sent")
    elif a.cmd == "cancel":
        Job(ws, a.job).cancel(); print("cancel requested")
    elif a.cmd == "serve":
        from .server import serve
        serve(ws, host=a.host or ws.s.host, port=a.port or ws.s.port)
    elif a.cmd == "demo":
        from .demo import run_demo
        run_demo(ws, real=a.real)


if __name__ == "__main__":
    main()
