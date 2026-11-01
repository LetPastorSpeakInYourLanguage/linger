import json, threading, time
from pathlib import Path
from storylens import subs, understand, views, recap, store
from storylens.jobs import Job, run_job, pending_steps
from storylens.select import select


def test_sdh_and_labels():
    c = subs.parse_text(0, 0, 1, "- [laughs] JOHN: Get down!\n- (gunshot) No!")
    assert c.text == "Get down! No!" and c.speaker_label == "John" and c.sdh == {"humor": 1, "violence": 1}


def test_scan_folder_pairs_by_name(ws, tmp_path):
    d = tmp_path / "show"; d.mkdir()
    for n in ("Show.S01E01.mkv", "Show.S01E01.en.srt", "Show.S01E02.mkv", "Show.S01E02.srt"): (d / n).write_text("x")
    t = ws.create_title("Show", "series"); added = ws.scan_folder(t["id"], d)
    assert len(added) == 2 and added[0]["subs"].endswith(".en.srt") and added[1]["episode"] == 2


def _understand(ws, title):
    job = Job.create(ws, "understand", title["id"], autonomy="auto")
    run_job(job, lambda j: understand.run(ws, j, title["id"], vision="off"))
    assert job.state["status"] == "done", job.state
    return job


def test_pipeline_mock_end_to_end(ws, title):
    _understand(ws, title)
    U = understand.load(ws, title["id"])
    assert U["beats"] and U["facts"] and U["bible"]["logline"]
    assert {e["kind"] for e in U["edges"]} >= {"caused_by"}
    assert store.search(ws, title["id"], "lighthouse")
    v = views.build(ws, None, title["id"], "main", {})
    assert v["items"] and views.get_view(ws, title["id"], "main")
    for lens, style in (({"kind": "main"}, "recap_channel"), ({"kind": "character", "name": "Victor"}, "character"),
                        ({"kind": "trait", "query": "being a good friend", "actor": "Leo"}, "compilation")):
        job = Job.create(ws, "recap", title["id"], autonomy="auto")
        run_job(job, lambda j: recap.run(ws, j, title["id"], {"lens": lens, "style": style, "duration": 60, "render": False}))
        assert job.state["status"] == "done", job.state
        sc = json.loads(job.artifact("script.json").read_text())
        assert sc["segments"] and all(s["media"] == "m001" for s in sc["segments"])


def test_corrections_apply(ws, title):
    _understand(ws, title)
    b = understand.load(ws, title["id"])["beats"][0]
    ws.add_correction(title["id"], b["id"], "tier", "P0")
    assert next(x for x in understand.load(ws, title["id"])["beats"] if x["id"] == b["id"])["tier"] == "P0"


def test_nested_selection():
    items = [{"ref": f"b{i}", "media": "m", "t0": i, "text": "word " * (8 + i % 7), "tier": ["P0", "P1", "P2", "P3"][i % 4],
              "salience": 100 - i, "requires": [f"b{i-4}"] if i >= 4 and i % 4 == 0 else []} for i in range(30)]
    prev = set()
    for B in (30, 60, 120, 300):
        sel = select([dict(i) for i in items], B)
        ids = {s["ref"] for s in sel}
        assert prev <= ids; prev = ids
        assert all(r in ids for s in sel for r in s["requires"])


def test_folder_backend_with_agent(ws, title):
    """The folder backend waits for response.json; a simulated agent answers each step (here: with the mock)."""
    from storylens.llm.mock import MockBackend
    from storylens.llm.runner import Call
    ws.s.llm_backend = "folder"; ws.s.folder_poll_seconds = 0.05
    stop = threading.Event()
    def agent():
        mock = MockBackend(ws.s)
        while not stop.is_set():
            for d in pending_steps(ws):
                d = Path(d); task = d.name.split("-", 1)[1]
                if (d / "response.json").exists(): continue
                hint = json.loads((d / "hint.json").read_text()) if (d / "hint.json").exists() else None
                data, _ = mock.complete(Call(task, "", "", None, "", "", 0, hint=hint))
                (d / "response.json").write_text(json.dumps(data))
            time.sleep(0.05)
    th = threading.Thread(target=agent, daemon=True); th.start()
    try:
        _understand(ws, title)
    finally:
        stop.set()
    assert not pending_steps(ws)
