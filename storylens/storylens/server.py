"""Web app: FastAPI JSON API + a no-build single-page UI (static/). Everything the UI does is also a file in the
workspace, so agents and humans can work side by side (docs/AGENTIC.md)."""
from __future__ import annotations
import json, os, shutil
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Body
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from . import __version__, media as M, store, views, understand, recap, library
from .jobs import Job, run_job, list_jobs
from . import tasks as T, catalog, watch
from .util import read_json, read_jsonl, write_json, write_text

STATIC = Path(__file__).parent / "static"


def create_app(ws, watcher=True):
    app = FastAPI(title="storylens", version=__version__)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    for p in Path(ws.jobs).glob("*/state.json"):     # jobs that were running when the server stopped
        st = read_json(p)
        if st.get("status") in ("running", "queued", "awaiting_review", "waiting_for_claude"):
            st["status"], st["message"] = "interrupted", "storylens restarted — rerun the job (answered tasks are reused)"; write_json(p, st)
    if watcher: watch.start_thread(ws)
    else: T.mark_stale(ws)

    def U(tid):
        try: return understand.load(ws, tid)
        except FileNotFoundError: raise HTTPException(404, "no understanding yet — run Understand first")

    @app.get("/", response_class=HTMLResponse)
    def index(): return (STATIC / "index.html").read_text(encoding="utf-8")

    # ---------------- status & settings
    @app.get("/api/status")
    def status():
        def has(mod):
            try: __import__(mod); return True
            except Exception: return False
        return {"version": __version__, "workspace": str(ws.root), "settings": {k: v for k, v in vars(ws.s).items() if k != "workspace"},
                "answerer": ws.s.answerer, "ffmpeg": M.have_ffmpeg(), "kokoro": has("kokoro_onnx"), "pyttsx3": has("pyttsx3"),
                "vad": M.silero_available(), "open_tasks": len(T.list_tasks(ws, "open")), "reviews": len(T.open_reviews(ws))}

    @app.post("/api/settings")
    def settings(d: dict = Body(...)):
        for k, v in d.items():
            if hasattr(ws.s, k) and k not in ("workspace",):
                setattr(ws.s, k, type(getattr(ws.s, k))(v) if not isinstance(getattr(ws.s, k), (dict, list)) else v)
        ws.s.save(); return status()

    @app.get("/api/instructions")
    def get_ins(): return {"text": (Path(ws.root) / "instructions.md").read_text(encoding="utf-8")}

    @app.put("/api/instructions")
    def put_ins(d: dict = Body(...)): write_text(Path(ws.root) / "instructions.md", d["text"]); return {"ok": True}

    # ---------------- titles & media
    @app.get("/api/titles")
    def titles(): return ws.titles()

    @app.post("/api/titles")
    def create_title(d: dict = Body(...)):
        t = ws.create_title(d["name"], d.get("kind", "film"), cast=[c.strip() for c in d.get("cast", "").split(",") if c.strip()])
        if d.get("folder"): ws.scan_folder(t["id"], d["folder"])
        return ws.title(t["id"])

    @app.delete("/api/titles/{tid}")
    def delete_title(tid: str): ws.delete_title(tid); return {"ok": True}

    @app.get("/api/titles/{tid}")
    def title(tid: str):
        t = ws.title(tid); out = {"title": t, "understanding": None}
        if ws.current_version(tid):
            u = U(tid)
            out["understanding"] = {"version": u["version"], "manifest": u["manifest"], "bible": u["bible"], "characters": u["characters"],
                                    "tiers": {k: sum(1 for b in u["beats"] if b.get("tier") == k) for k in ("P0", "P1", "P2", "P3")}}
        out["instructions"] = (ws.tdir(tid) / "instructions.md").read_text(encoding="utf-8")
        out["media_info"] = {m["id"]: read_json(ws.edir(tid, m["id"]) / "media.json") for m in t["media"]}
        return out

    @app.post("/api/titles/{tid}/media")
    def add_media(tid: str, d: dict = Body(...)):
        for k in ("video", "subs"):
            if d.get(k) and not Path(d[k]).exists(): raise HTTPException(400, f"{k} path not found on this computer: {d[k]}")
        return ws.add_media(tid, video=d.get("video") or None, subs=d.get("subs") or None, season=d.get("season"), episode=d.get("episode"))

    @app.post("/api/titles/{tid}/scan")
    def scan(tid: str, d: dict = Body(...)):
        if not Path(d["folder"]).is_dir(): raise HTTPException(400, "folder not found")
        return ws.scan_folder(tid, d["folder"])

    @app.post("/api/titles/{tid}/upload-subs")
    async def upload_subs(tid: str, file: UploadFile = File(...)):
        dest = ws.tdir(tid) / "uploads" / Path(file.filename).name; dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f: shutil.copyfileobj(file.file, f)
        return ws.add_media(tid, subs=str(dest))

    @app.delete("/api/titles/{tid}/media/{mid}")
    def del_media(tid: str, mid: str):
        t = ws.title(tid); t["media"] = [m for m in t["media"] if m["id"] != mid]; ws.save_title(t); return t

    @app.put("/api/titles/{tid}/instructions")
    def put_title_ins(tid: str, d: dict = Body(...)): write_text(ws.tdir(tid) / "instructions.md", d["text"]); return {"ok": True}

    # ---------------- understanding explorer
    @app.get("/api/titles/{tid}/beats")
    def beats(tid: str, tier: str = "", q: str = ""):
        bs = U(tid)["beats"]
        if tier: bs = [b for b in bs if b.get("tier") in tier.split(",")]
        if q: bs = [b for b in bs if q.lower() in (b["text"] + " " + " ".join(b["who"])).lower()]
        return bs

    @app.get("/api/titles/{tid}/facts")
    def facts(tid: str, actor: str = "", act: str = "", kind: str = "", q: str = "", limit: int = 500):
        fs = U(tid)["facts"]
        if actor: fs = [f for f in fs if actor.lower() in (f["actor"] + "|" + f["target"]).lower()]
        if act: fs = [f for f in fs if f["act_type"] == act]
        if kind: fs = [f for f in fs if f["kind"] == kind]
        if q: fs = [f for f in fs if q.lower() in f["text"].lower()]
        return fs[:limit]

    @app.get("/api/titles/{tid}/scenes")
    def scenes(tid: str): return U(tid)["scenes"]

    @app.get("/api/titles/{tid}/edges")
    def edges(tid: str): return U(tid)["edges"]

    @app.get("/api/titles/{tid}/lines")
    def lines(tid: str, media: str, l0: int, l1: int, pad: int = 2): return store.lines(ws, tid, media, l0, l1, pad)

    @app.get("/api/titles/{tid}/search")
    def search(tid: str, q: str): return store.search(ws, tid, q)

    @app.post("/api/titles/{tid}/corrections")
    def correct(tid: str, d: dict = Body(...)):
        ws.add_correction(tid, d["target"], d["field"], d["value"], d.get("reason", ""))
        store.build_index(ws, tid)
        try: library.build_index(ws)
        except Exception: pass
        return {"ok": True}

    # ---------------- cross-source layer
    @app.get("/api/collections")
    def get_collections(): return library.collections(ws)

    @app.post("/api/collections")
    def new_collection(d: dict = Body(...)): return library.create_collection(ws, d["name"], d.get("titles") or ["*"], d.get("description", ""))

    @app.get("/api/library/search")
    def lib_search(q: str, level: str = "claim", speaker: str = "", collection: str = "all"):
        return library.search(ws, q, level, speaker, collection)

    @app.post("/api/library/reindex")
    def lib_reindex(): library.build_index(ws); return {"ok": True}

    @app.get("/api/collections/{cid}/lenses")
    def lib_lenses(cid: str): return library.list_lenses(ws, cid)

    @app.get("/api/collections/{cid}/lenses/{vid}")
    def lib_lens(cid: str, vid: str):
        v = library.get_lens(ws, cid, vid)
        if not v: raise HTTPException(404, "no such lens")
        return v

    @app.post("/api/collections/{cid}/lens")
    def lib_build(cid: str, d: dict = Body(...)):
        lens = dict(d["lens"]); kind = lens.pop("kind")
        return start("lens", cid, {"kind": kind, **lens}, lambda j: library.build_lens(ws, j, cid, kind, lens, force=d.get("force", False)), d)

    @app.post("/api/collections/{cid}/recap")
    def lib_recap(cid: str, d: dict = Body(...)):
        params = {k: d[k] for k in ("lens", "style", "duration", "render", "review", "voice", "hardsub_blur") if k in d}
        return start("recap", cid, params, lambda j: recap.run(ws, j, None, params, collection=cid), d)

    @app.get("/api/titles/{tid}/views")
    def list_views(tid: str): return views.list_views(ws, tid)

    @app.get("/api/titles/{tid}/views/{vid}")
    def get_view(tid: str, vid: str):
        v = views.get_view(ws, tid, vid)
        if not v: raise HTTPException(404, "no such lens")
        return v

    # ---------------- jobs
    def start(kind, tid, params, fn, d):
        job = Job.create(ws, kind, tid, params, instructions=d.get("instructions", ""), autonomy=d.get("autonomy") or None)
        run_job(job, fn, background=True); return {"job": job.id}

    @app.post("/api/titles/{tid}/understand")
    def do_understand(tid: str, d: dict = Body(default={})):
        return start("understand", tid, {"vision": d.get("vision", "auto")},
                     lambda j: understand.run(ws, j, tid, reingest=d.get("reingest", False), vision=d.get("vision", "auto")), d)

    @app.post("/api/titles/{tid}/lens")
    def do_lens(tid: str, d: dict = Body(...)):
        lens = dict(d["lens"]); kind = lens.pop("kind")
        return start("lens", tid, {"kind": kind, **lens}, lambda j: views.build(ws, j, tid, kind, lens, force=d.get("force", False)), d)

    @app.post("/api/titles/{tid}/recap")
    def do_recap(tid: str, d: dict = Body(...)):
        params = {k: d[k] for k in ("lens", "style", "duration", "render", "review", "voice", "hardsub_blur") if k in d}
        return start("recap", tid, params, lambda j: recap.run(ws, j, tid, params), d)

    @app.get("/api/jobs")
    def jobs(title: str = ""): return list_jobs(ws, title or None)[:200]

    @app.get("/api/jobs/{jid}")
    def job(jid: str):
        j = Job(ws, jid)
        if not j.spec: raise HTTPException(404, "no such job")
        gates = []
        for md in sorted((j.dir / "review").glob("*.md")):
            g = md.stem
            gates.append({"gate": g, "markdown": md.read_text(encoding="utf-8"), "metrics": read_json(j.dir / "review" / f"{g}.metrics.json", {}),
                          "decision": read_json(j.dir / "review" / f"{g}.decision.json")})
        tl = [{"id": t["id"], "status": t["status"], "summary": t["summary"]} for t in T.list_tasks(ws) if t.get("job") == jid]
        return {"job": j.spec, "state": j.state, "events": read_jsonl(j.dir / "events.jsonl")[-80:], "gates": gates,
                "artifacts": sorted(p.name for p in (j.dir / "artifacts").glob("*") if p.is_file()), "tasks": tl,
                "script": read_json(j.dir / "artifacts" / "script.json"), "verify": read_json(j.dir / "artifacts" / "verify.json")}

    @app.post("/api/jobs/{jid}/rerun")
    def rerun(jid: str):
        from . import actions
        job, fn = actions.job_for(ws, {"do": "rerun", "job": jid}); run_job(job, fn, background=True); return {"job": job.id}

    @app.post("/api/jobs/{jid}/decide")
    def decide(jid: str, d: dict = Body(...)):
        Job(ws, jid).decide(d["gate"], d["decision"], d.get("notes", ""), d.get("edits")); return {"ok": True}

    @app.post("/api/jobs/{jid}/send")
    def send(jid: str, d: dict = Body(...)): Job(ws, jid).send(d["text"]); return {"ok": True}

    @app.post("/api/jobs/{jid}/cancel")
    def cancel(jid: str): Job(ws, jid).cancel(); return {"ok": True}

    @app.get("/api/jobs/{jid}/artifacts/{name}")
    def artifact(jid: str, name: str):
        p = (Job(ws, jid).dir / "artifacts" / name).resolve()
        if not p.exists() or Job(ws, jid).dir.resolve() not in p.parents: raise HTTPException(404)
        return FileResponse(p)

    # ---------------- Claude tasks (normally Claude answers them in the folder; the UI can paste an answer too)
    @app.get("/api/tasks")
    def task_list(status: str = "open"):
        return {"tasks": T.list_tasks(ws, None if status == "all" else status)[-300:], "reviews": T.open_reviews(ws),
                "queue": str(T.tasks_dir(ws) / "QUEUE.md"), "workspace": str(ws.root)}

    @app.get("/api/tasks/{tid_}")
    def task_get(tid_: str):
        d = (T.tasks_dir(ws) / tid_).resolve()
        if T.tasks_dir(ws).resolve() not in d.parents or not (d / "TASK.md").exists(): raise HTTPException(404)
        err = d / "ANSWER_ERRORS.md"
        return {"id": tid_, "meta": read_json(d / "meta.json"), "task": (d / "TASK.md").read_text(encoding="utf-8"),
                "answer": read_json(d / "answer.json"), "errors": err.read_text(encoding="utf-8") if err.exists() else ""}

    @app.post("/api/tasks/{tid_}/answer")
    def task_answer(tid_: str, d: dict = Body(...)):
        p = (T.tasks_dir(ws) / tid_).resolve()
        if T.tasks_dir(ws).resolve() not in p.parents or read_json(p / "meta.json", {}).get("status") not in ("open", "stale"):
            raise HTTPException(400, "not an open task")
        try: data = d["answer"] if isinstance(d["answer"], (dict, list)) else json.loads(d["answer"])
        except json.JSONDecodeError as e: raise HTTPException(400, f"not valid JSON: {e}")
        write_json(p / "answer.json", data); return {"ok": True}

    @app.get("/api/catalog")
    def get_catalog():
        catalog.write(ws); return {"markdown": (Path(ws.root) / "CATALOG.md").read_text(encoding="utf-8")}

    # ---------------- media preview (original video, for the clip player)
    @app.get("/api/titles/{tid}/video/{mid}")
    def video(tid: str, mid: str):
        m = next((m for m in ws.title(tid)["media"] if m["id"] == mid), None)
        if not m or not m.get("video") or not Path(m["video"]).exists(): raise HTTPException(404, "no video for this media")
        return FileResponse(m["video"])

    return app


def serve(ws, host="127.0.0.1", port=8765):
    import uvicorn
    print(f"storylens {__version__}  workspace: {ws.root}\n→ open http://{host}:{port}\n"
          f"  Claude desktop: share {ws.root} and ask Claude to follow CLAUDE.md (tasks/QUEUE.md, requests/new/)")
    uvicorn.run(create_app(ws), host=host, port=port, log_level="warning")
