"""storylens command line. Run `storylens --help`. The web app: `storylens serve`."""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
from . import config as C, __version__
from .workspace import Workspace
from .jobs import Job, run_job, list_jobs
from .actions import parse_lens


def _ws(a):
    s = C.load(a.workspace)
    if getattr(a, "offline", False): s.answerer = "mock"
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


def main(argv=None):
    ap = argparse.ArgumentParser(prog="storylens", description="Subtitle-first story understanding and recaps.")
    ap.add_argument("--workspace", "-w", help="workspace folder (default: $STORYLENS_WORKSPACE or ~/storylens-workspace)")
    ap.add_argument("--offline", action="store_true", help="answer tasks with the built-in offline heuristic instead of Claude (tests/demos; low quality)")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create the workspace")
    x = sub.add_parser("add", help="add a title (film or series) with media")
    x.add_argument("name"); x.add_argument("--video", action="append", default=[]); x.add_argument("--subs", action="append", default=[])
    x.add_argument("--folder", help="scan a folder: pairs videos/audio with .srt/.vtt/.ass/.txt transcripts by name")
    x.add_argument("--kind", choices=["film", "series", "podcast", "talkshow", "sermon", "lecture"], default="film")
    x.add_argument("--cast", default="", help="comma-separated character names (optional, improves naming)")
    sub.add_parser("titles", help="list titles")
    x = sub.add_parser("understand", help="build the understanding (P1 facts+beats per part, P2 integration) — gate G1")
    x.add_argument("title"); x.add_argument("--autopilot", action="store_true", help="auto-approve gates whose metrics pass")
    x.add_argument("--yes", action="store_true", help="approve every gate (unattended)"); x.add_argument("--reingest", action="store_true")
    x.add_argument("--vision", choices=["auto", "on", "off"], default="auto"); x.add_argument("--instructions", default="")
    x = sub.add_parser("lens", help="build a lens: main | character:NAME | thread:ID | trait:[ACTOR/]QUERY | topic:[SPEAKER/]QUERY | pattern:[SPEAKER] "
                                    "(with --collection: title arg is ignored; also overview)")
    x.add_argument("title"); x.add_argument("spec"); x.add_argument("--deep", action="store_true"); x.add_argument("--force", action="store_true")
    x.add_argument("--collection", help="cross-source lens over a collection ('all' = every title)")
    x = sub.add_parser("recap", help="make a recap (script + checks + render) — gates G2/G3")
    x.add_argument("title"); x.add_argument("--lens", default="main"); x.add_argument("--deep", action="store_true")
    x.add_argument("--style", default="recap_channel", choices=["recap_channel", "dramatic_comedic", "short_direct", "fan_silent", "detailed_full", "character", "compilation", "clips"])
    x.add_argument("--collection", help="cross-source recap over a collection ('all' = every title); title arg is ignored")
    x.add_argument("--duration", type=int, default=180, help="seconds; 0 = unlimited"); x.add_argument("--no-render", action="store_true")
    x.add_argument("--review", action="store_true", help="add a Claude review task for the script (deterministic checks always run)")
    x.add_argument("--voice"); x.add_argument("--hardsub-blur", action="store_true")
    x.add_argument("--autopilot", action="store_true"); x.add_argument("--yes", action="store_true"); x.add_argument("--instructions", default="")
    x = sub.add_parser("search", help="full-text search the understanding"); x.add_argument("title"); x.add_argument("query")
    x = sub.add_parser("find", help="search ALL sources at a level of detail: title|episode|point|claim|line")
    x.add_argument("query"); x.add_argument("--level", default="claim", choices=["title", "episode", "point", "claim", "line"])
    x.add_argument("--speaker", default=""); x.add_argument("--collection", default="all")
    x = sub.add_parser("collection", help="collections of titles for cross-source lenses/recaps")
    x.add_argument("action", choices=["list", "create", "reindex"]); x.add_argument("name", nargs="?"); x.add_argument("--titles", default="*")
    sub.add_parser("jobs", help="list jobs")
    x = sub.add_parser("tasks", help="list Claude tasks (open by default) and reviews waiting"); x.add_argument("--all", action="store_true")
    sub.add_parser("watch", help="watch the workspace: run requests/new/*.json that Claude writes (serve does this too)")
    x = sub.add_parser("request", help="run a request JSON now, as Claude would via requests/new (e.g. '{\"do\": \"find\", \"query\": \"grace\"}')")
    x.add_argument("json")
    x = sub.add_parser("approve", help="decide a review gate"); x.add_argument("job"); x.add_argument("gate")
    x.add_argument("--revise", help="notes: ask for a revision"); x.add_argument("--reject", action="store_true")
    x = sub.add_parser("send", help="send an instruction to a running job"); x.add_argument("job"); x.add_argument("text")
    x = sub.add_parser("cancel", help="cancel a job"); x.add_argument("job")
    x = sub.add_parser("serve", help="start the web app"); x.add_argument("--port", type=int); x.add_argument("--host")
    x = sub.add_parser("demo", help="bundled sample film + podcast, run end to end (offline heuristic answers by default)")
    x.add_argument("--claude", action="store_true", help="queue real tasks for Claude instead of answering them offline")
    a = ap.parse_args(argv)
    ws = _ws(a)

    if a.cmd == "init":
        from . import catalog, tasks
        catalog.write(ws); tasks.write_queue(ws)
        print(f"workspace ready: {ws.root}\n  share this folder with the Claude desktop app; Claude reads CLAUDE.md there.\n  settings: {ws.root / 'settings.json'}")
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
        try: lens = parse_lens(a.spec, deep=a.deep)
        except ValueError as e: raise SystemExit(str(e))
        kind = lens.pop("kind")
        job = Job.create(ws, "lens", a.collection or a.title, {"kind": kind, **lens})
        v = library.build_lens(ws, job, a.collection, kind, lens, force=a.force) if a.collection else views.build(ws, job, a.title, kind, lens, force=a.force)
        print(f"{v['title']} — {len(v['items'])} items\n{v.get('summary', '')}")
        for it in v["items"]:
            who = f"[{it['speaker']}{'?' if it.get('speaker_uncertain') else ''}] " if it.get("speaker") else ""
            print(f"  [{it['tier']}] {it['media']} L{it['lines'][0]:>4} sal={it['salience']:>3} {who}{it['text'][:110]}")
    elif a.cmd == "recap":
        from . import recap
        try: lens = parse_lens(a.lens, deep=a.deep)
        except ValueError as e: raise SystemExit(str(e))
        params = {"lens": lens, "style": a.style, "duration": a.duration, "render": not a.no_render,
                  "voice": a.voice, "hardsub_blur": a.hardsub_blur, **({"review": True} if a.review else {})}
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
    elif a.cmd == "tasks":
        from .tasks import list_tasks, open_reviews
        ts = list_tasks(ws, None if a.all else "open")
        for t in ts: print(f"{t['status']:9s} {t['id']:52s} {t['summary'][:90]}")
        if not ts: print("no open tasks")
        for r in open_reviews(ws): print(f"review    {r['file']}  ({r['title']})")
        print(f"\nClaude works from {ws.root / 'tasks' / 'QUEUE.md'} (see CLAUDE.md).")
    elif a.cmd == "watch":
        from .watch import watch_forever
        watch_forever(ws)
    elif a.cmd == "request":
        from . import actions
        d = json.loads(a.json)
        if d.get("do") in actions.JOB_ACTIONS:
            job, fn = actions.job_for(ws, d); job.on_gate = _interactive_gate
            print(f"job {job.id}"); run_job(job, fn); print(f"→ {job.state['status']}: {job.state.get('message', '')}")
        else:
            print(json.dumps(actions.do_now(ws, d), indent=1, ensure_ascii=False)[:20000])
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
        run_demo(ws, claude=a.claude)


if __name__ == "__main__":
    main()
