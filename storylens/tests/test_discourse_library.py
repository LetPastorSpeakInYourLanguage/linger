import json
from pathlib import Path
from importlib import resources
from storylens import subs, understand, views, recap, library
from storylens.jobs import Job, run_job


def _samples(name): return Path(str(resources.files("storylens") / "samples" / name))


def test_timestamped_transcript_and_merge():
    c = subs.load(_samples("long_table_ep1.md"))
    m = subs.merge_fragments(c)
    assert len(c) > len(m) > 5 and m[0].start == c[0].start and all(x.idx == i for i, x in enumerate(m))


def _podcast(ws):
    t = ws.create_title("Long Table", "podcast", cast=["Sam", "Nadia Okafor", "Ruth Adeyemi"])
    for i, fn in enumerate(("long_table_ep1.md", "long_table_ep2.md")):
        ws.add_media(t["id"], subs=_samples(fn), season=1, episode=i + 1)
    job = Job.create(ws, "understand", t["id"], autonomy="auto")
    run_job(job, lambda j: understand.run(ws, j, t["id"], vision="off"))
    assert job.state["status"] == "done", job.state
    return t["id"]


def test_discourse_topic_lens_and_clips(ws):
    tid = _podcast(ws)
    U = understand.load(ws, tid)
    assert any(f["kind"] == "claim" and f.get("topics") for f in U["facts"])
    v = views.build(ws, None, tid, "topic", {"query": "meaning of life", "speaker": ""})
    assert v["items"] and all("claim" in i for i in v["items"])
    job = Job.create(ws, "recap", tid, autonomy="auto")
    run_job(job, lambda j: recap.run(ws, j, tid, {"lens": {"kind": "topic", "query": "meaning of life"}, "style": "clips", "duration": 60, "render": False}))
    sc = json.loads(job.artifact("script.json").read_text())
    assert sc["segments"] and all(s["type"] == "hero_clip" for s in sc["segments"])


def test_pattern_lens(ws):
    tid = _podcast(ws)
    v = views.build(ws, None, tid, "pattern", {"speaker": ""})
    assert v["pattern"] and len(v["pattern"]) >= 3 and v["items"]
    assert all(i.get("label") for i in v["items"]) and {i["role"] for i in v["items"]} <= set(v["pattern"])
    job = Job.create(ws, "recap", tid, autonomy="auto")
    run_job(job, lambda j: recap.run(ws, j, tid, {"lens": {"kind": "pattern", "speaker": ""}, "style": "clips", "duration": 60, "render": False}))
    sc = json.loads(job.artifact("script.json").read_text())
    assert all(" — Long Table" in s["text"] and "·" in s["text"] for s in sc["segments"] if s["type"] == "hero_clip")     # step label — source


def test_cross_source_library(ws, title):
    tid = _podcast(ws)
    job = Job.create(ws, "understand", title["id"], autonomy="auto")
    run_job(job, lambda j: understand.run(ws, j, title["id"], vision="off"))
    library.build_index(ws)
    for level in library.LEVELS:
        assert library.search(ws, "friend lighthouse meaning", level=level), level
    c = library.create_collection(ws, "Everything friendly", [tid, title["id"]])
    v = library.build_lens(ws, None, c["id"], "topic", {"query": "what makes a good friend"})
    assert {i["title_id"] for i in v["items"]} == {tid, title["id"]}
    assert all("::" in i["media"] for i in v["items"])
    job = Job.create(ws, "recap", c["id"], autonomy="auto")
    run_job(job, lambda j: recap.run(ws, j, None, {"lens": {"kind": "topic", "query": "what makes a good friend"}, "style": "clips",
                                                  "duration": 60, "render": False}, collection=c["id"]))
    assert job.state["status"] == "done", job.state
    sc = json.loads(job.artifact("script.json").read_text())
    assert {s["media"].split("::")[0] for s in sc["segments"]} <= {tid, title["id"]}
    ov = library.build_lens(ws, None, "all", "overview", {})
    assert ov["items"] and len(ov["titles"]) == 2
