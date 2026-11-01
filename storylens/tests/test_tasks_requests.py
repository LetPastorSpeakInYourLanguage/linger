"""The Claude-facing surface: task files, validation, requests/ inbox, CATALOG.md, CLAUDE.md, web API."""
import json, threading, time
from pathlib import Path
from storylens import tasks as T, watch, catalog, schemas as SC
from storylens.jobs import Job


def test_workspace_has_claude_files(ws):
    root = Path(ws.root)
    assert "tasks/QUEUE.md" in (root / "CLAUDE.md").read_text() and (root / "requests" / "new").is_dir()
    catalog.write(ws); assert "# Catalog" in (root / "CATALOG.md").read_text()


def test_task_file_validation_and_cache(ws):
    ws.s.answerer = "claude"; ws.s.poll_seconds = 0.02
    job = Job.create(ws, "lens", "x")
    q = T.TaskQueue(ws, job)
    out = {}
    th = threading.Thread(target=lambda: out.setdefault("a", q.json("lens-trait-map-test", "SYS", "INPUT", SC.TRAIT_MAP, summary="map it")),
                          daemon=True)
    th.start()
    for _ in range(250):
        ds = list((Path(ws.root) / "tasks").glob("0001-*/TASK.md"))
        if ds: break
        time.sleep(0.02)
    d = ds[0].parent
    md = (d / "TASK.md").read_text()
    assert "map it" in md and "## Input\n\nINPUT" in md and '"act_types"' in md
    assert "map it" in (Path(ws.root) / "tasks" / "QUEUE.md").read_text()
    (d / "answer.json").write_text('{"description": "x"}')                     # missing keys -> rejected
    for _ in range(200):
        if (d / "ANSWER_ERRORS.md").exists(): break
        time.sleep(0.02)
    assert "missing key 'act_types'" in (d / "ANSWER_ERRORS.md").read_text()
    good = {"description": "kind", "act_types": ["helps"], "keywords": ["help"], "actor_required": False}
    (d / "answer.json").write_text(json.dumps(good)); th.join(5)
    assert out["a"] == good and not (d / "ANSWER_ERRORS.md").exists()
    assert T.TaskQueue(ws, job).json("lens-trait-map-test", "SYS", "INPUT", SC.TRAIT_MAP) == good   # cached: no new task
    assert len(list((Path(ws.root) / "tasks").glob("0*"))) == 1


def test_stale_answers_are_harvested(ws):
    ws.s.answerer = "claude"
    job = Job.create(ws, "lens", "x")
    p = T.TaskQueue(ws, job).submit("t-one", "S", "P", SC.TRAIT_MAP)
    job.update(status="failed"); T.mark_stale(ws)
    assert T.list_tasks(ws, "stale")
    (p.dir / "answer.json").write_text(json.dumps({"description": "d", "act_types": [], "keywords": [], "actor_required": True}))
    assert T.harvest(ws) == 1
    assert T.TaskQueue(ws, None).json("t-one", "S", "P", SC.TRAIT_MAP)["description"] == "d"


def test_requests_inbox_runs_jobs(ws, tmp_path):
    from storylens.demo import sample_srt
    new = Path(ws.root) / "requests" / "new"
    (new / "a.json").write_text(json.dumps({"do": "add_title", "name": "Lighthouse", "kind": "film", "cast": "Maya,Leo,Victor,Ines",
                                            "media": [{"subs": str(sample_srt())}]}))
    watch.process(ws, background=False)
    tid = json.loads((Path(ws.root) / "requests" / "done" / "a.json").read_text())["done"][0]["result"]["title"]
    (new / "b.json").write_text(json.dumps([{"do": "understand", "title": tid, "autonomy": "auto"},
                                            {"do": "lens", "title": tid, "lens": "character:Victor"},
                                            {"do": "recap", "title": tid, "lens": "main", "style": "short_direct", "duration": 45,
                                             "render": False, "autonomy": "auto"}]))
    (new / "c.json").write_text(json.dumps({"do": "recap", "title": tid, "lens": "nonsense:x"}))
    watch.process(ws, background=False)
    done = json.loads((Path(ws.root) / "requests" / "done" / "b.json").read_text())["done"]
    assert [Job(ws, d["job"]).state["status"] for d in done] == ["done", "done", "done"]
    assert "unknown lens" in json.loads((Path(ws.root) / "requests" / "failed" / "c.json").read_text())["error"]
    (new / "d.json").write_text(json.dumps({"do": "find", "query": "lighthouse", "level": "line"}))
    watch.process(ws, background=False)
    assert "# find: lighthouse" in (Path(ws.root) / "requests" / "done" / "d.result.md").read_text()
    cat = (Path(ws.root) / "CATALOG.md").read_text()
    assert tid in cat and "Victor" in cat


def test_server_api(ws, title):
    from fastapi.testclient import TestClient
    from storylens.server import create_app
    c = TestClient(create_app(ws, watcher=False))
    assert c.get("/").status_code == 200 and "storylens" in c.get("/").text
    st = c.get("/api/status").json(); assert st["answerer"] == "mock" and st["open_tasks"] == 0
    assert c.get("/api/titles").json()[0]["id"] == title["id"]
    r = c.post(f"/api/titles/{title['id']}/media", json={"subs": "/nope.srt"}); assert r.status_code == 400
    d = c.get(f"/api/titles/{title['id']}").json(); assert d["understanding"] is None
    assert c.get(f"/api/titles/{title['id']}/beats").status_code == 404
    assert c.get("/api/tasks").json()["tasks"] == []
    assert "# Catalog" in c.get("/api/catalog").json()["markdown"]


def test_lens_request_waits_for_running_understanding(ws, title):
    """Claude often writes [approve G1, recap] in one request file: the recap must wait, not fail."""
    from storylens import actions, understand
    from storylens.jobs import run_job
    u = Job.create(ws, "understand", title["id"], autonomy="auto")
    run_job(u, lambda j: understand.run(ws, j, title["id"], vision="off"))
    busy = Job.create(ws, "understand", title["id"]); busy.update(status="awaiting_review")    # a second run, still at G1
    job, fn = actions.job_for(ws, {"do": "lens", "title": title["id"], "lens": "character:Victor"})
    run_job(job, fn, background=True)
    time.sleep(1.5)
    assert job.state["status"] == "running" and "waiting for" in job.state["message"]
    busy.update(status="done")
    for _ in range(100):
        if job.state["status"] == "done": break
        time.sleep(0.1)
    assert job.state["status"] == "done"
