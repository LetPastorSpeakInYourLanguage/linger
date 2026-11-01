"""The Claude task queue — the ONLY way storylens thinks.

There is no API. Every piece of understanding/writing is a task folder in the shared workspace that Claude (the
desktop app, working in this folder) answers:

  tasks/QUEUE.md                         open tasks, in the order to do them (regenerated continuously)
  tasks/<NNNN>-<kind>-<name>/TASK.md     instructions + example answer + all the input (self-contained)
  tasks/<NNNN>-<kind>-<name>/answer.json Claude writes this
  tasks/<NNNN>-<kind>-<name>/ANSWER_ERRORS.md   written by storylens if the answer is invalid (fix and rewrite)
  tasks/<NNNN>-<kind>-<name>/meta.json   status: open | done | cancelled, job, cache key

Answers are cached by content hash (<ws>/.cache/answers), so re-running a job never asks the same question twice.
For tests and the offline demo an `answerer` function can answer instantly (storylens.testing).
"""
from __future__ import annotations
import json, os, re, threading, time
from pathlib import Path
from .util import read_json, write_json, write_text, sha, now, slug

_lock = threading.Lock()
_said = [0.0]


class TaskError(RuntimeError):
    pass


def example_from_schema(schema, depth=0):
    """A readable example answer generated from the JSON schema."""
    t = schema.get("type")
    if t == "object":
        return {k: example_from_schema(v, depth + 1) for k, v in schema.get("properties", {}).items()}
    if t == "array":
        if "first_line" in schema.get("description", ""): return [0, 0]
        return [example_from_schema(schema.get("items", {}), depth + 1)]
    return {"string": "…", "integer": 0, "boolean": False}.get(t, None)


def compact_json(x, ind=0, width=110):
    """JSON with small objects and scalar lists on one line (much shorter TASK.md than indent=1)."""
    one = json.dumps(x, ensure_ascii=False)
    pad, sub = " " * ind, " " * (ind + 2)
    if len(one) + ind <= width or not isinstance(x, (dict, list)) or not x: return one
    if isinstance(x, list):
        return "[\n" + ",\n".join(sub + compact_json(v, ind + 2, width) for v in x) + "\n" + pad + "]"
    return "{\n" + ",\n".join(f"{sub}{json.dumps(k)}: {compact_json(v, ind + 2, width).lstrip()}" for k, v in x.items()) + "\n" + pad + "}"


def validate(data, schema, path="answer"):
    errs = []
    t = schema.get("type")
    if t == "object":
        if not isinstance(data, dict): return [f"{path}: expected an object"]
        for k in schema.get("required", []):
            if k not in data: errs.append(f"{path}: missing key '{k}'")
        for k, sub in schema.get("properties", {}).items():
            if k in data and data[k] is not None: errs += validate(data[k], sub, f"{path}.{k}")
    elif t == "array":
        if not isinstance(data, list): return [f"{path}: expected a list"]
        for i, x in enumerate(data):
            errs += validate(x, schema.get("items", {}), f"{path}[{i}]")
            if len(errs) > 25: break
    elif t == "integer" and not (isinstance(data, int) and not isinstance(data, bool)):
        if isinstance(data, float) and data.is_integer(): return []
        errs.append(f"{path}: expected an integer")
    elif t == "string" and not isinstance(data, str): errs.append(f"{path}: expected a string")
    elif t == "boolean" and not isinstance(data, bool): errs.append(f"{path}: expected true/false")
    return errs


def tasks_dir(ws) -> Path: return Path(ws.root) / "tasks"


def list_tasks(ws, status=None):
    out = []
    for m in sorted(tasks_dir(ws).glob("*/meta.json")):
        d = read_json(m)
        if d and (status is None or d.get("status") == status): out.append({**d, "dir": str(m.parent)})
    return out


def open_reviews(ws):
    """Gates waiting for a decision (jobs/<job>/review/<gate>.md without <gate>.decision.json)."""
    out = []
    for st in Path(ws.jobs).glob("*/state.json"):
        if read_json(st, {}).get("status") != "awaiting_review": continue
        for md in sorted((st.parent / "review").glob("*.md")):
            if not (md.parent / f"{md.stem}.decision.json").exists():
                out.append({"job": st.parent.name, "gate": md.stem, "file": f"jobs/{st.parent.name}/review/{md.name}",
                            "title": read_json(st.parent / "job.json", {}).get("title", "")})
    return out


def write_queue(ws):
    """tasks/QUEUE.md — what Claude reads first."""
    with _lock:
        open_ = list_tasks(ws, "open"); revs = open_reviews(ws)
        lines = ["# storylens — Claude task queue", "",
                 f"**{len(open_)} open task(s)**, {len(revs)} review(s) waiting. Updated {time.strftime('%Y-%m-%d %H:%M:%S')}.", "",
                 "Do the tasks top to bottom. For each: read `TASK.md`, write `answer.json` in the same folder. If",
                 "`ANSWER_ERRORS.md` appears a few seconds later, fix the answer. Finishing tasks unlocks new ones (integration after",
                 "all parts of an episode, the script after a lens…), so re-read this file until nothing is open.", "", "## Tasks", ""]
        for t in open_:
            err = " ⚠ **has ANSWER_ERRORS.md**" if (Path(t["dir"]) / "ANSWER_ERRORS.md").exists() else ""
            lines.append(f"- [ ] `{Path(t['dir']).name}/TASK.md` — {t['summary']}{err}")
        if not open_: lines.append("Nothing to do right now.")
        lines += ["", "## Reviews waiting for the user", ""]
        for r in revs:
            lines.append(f"- `{r['file']}` ({r['title']}) — show it to the user; when they decide, write a request "
                         f"`{{\"do\": \"decide\", \"job\": \"{r['job']}\", \"gate\": \"{r['gate']}\", \"decision\": \"approve\"}}`")
        if not revs: lines.append("None.")
        write_text(tasks_dir(ws) / "QUEUE.md", "\n".join(lines) + "\n")


def mark_stale(ws):
    """At startup: open tasks of jobs that are no longer running become 'stale' (answers are still harvested)."""
    alive = ("running", "queued", "awaiting_review", "waiting_for_claude")
    for t in list_tasks(ws, "open"):
        st = read_json(Path(ws.jobs) / t.get("job", "-") / "state.json", {}).get("status")
        if t.get("job") and st not in alive:
            m = Path(t["dir"]) / "meta.json"; d = read_json(m); d["status"] = "stale"; write_json(m, d)
    write_queue(ws)


def harvest(ws):
    """Cache valid answers Claude wrote for stale/cancelled tasks, so re-running the job reuses them."""
    n = 0
    for t in list_tasks(ws):
        if t["status"] not in ("stale", "cancelled"): continue
        d = Path(t["dir"]); a = d / "answer.json"
        if not a.exists(): continue
        try:
            data = json.loads(a.read_text(encoding="utf-8"))
            if validate(data, read_json(d / "schema.json", {})): continue
        except (json.JSONDecodeError, OSError):
            continue
        write_json(Path(ws.root) / ".cache" / "answers" / f"{t['key']}.json", data)
        m = read_json(d / "meta.json"); m.update(status="done", answered=now(), harvested=True); write_json(d / "meta.json", m); n += 1
    return n


def cancel_job_tasks(ws, job_id):
    for t in list_tasks(ws, "open"):
        if t.get("job") == job_id:
            m = Path(t["dir"]) / "meta.json"; d = read_json(m); d["status"] = "cancelled"; write_json(m, d)
    write_queue(ws)


class Pending:
    def __init__(self, d, key, schema, kind): self.dir, self.key, self.schema, self.kind = Path(d), key, schema, kind


class TaskQueue:
    """Drop-in for the old LLM runner: .json(task, system, prompt, schema, ...) blocks until Claude answers."""

    def __init__(self, ws, job, answerer=None):
        self.ws, self.job = ws, job
        self.answerer = answerer if answerer is not None else (_mock_answerer() if ws.s.answerer == "mock" else None)
        self.cache = Path(ws.root) / ".cache" / "answers"
        self.usage = {"tasks": 0, "cached": 0, "rejected": 0}

    # ----- create
    def submit(self, task, system, prompt, schema, images=None, hint=None, summary=None, **_):
        key = sha(system, prompt, schema, [Path(i).name for i in images or []])
        cached = read_json(self.cache / f"{key}.json")
        if cached is not None:
            self.usage["cached"] += 1
            return cached
        with _lock:
            n = max([int(p.name[:4]) for p in tasks_dir(self.ws).glob("[0-9][0-9][0-9][0-9]-*")] or [0]) + 1
            d = tasks_dir(self.ws) / f"{n:04d}-{slug(task, 60)}"
            d.mkdir(parents=True, exist_ok=True)
        ex = compact_json(example_from_schema(schema)) if schema else "{}"
        imgs = ""
        for img in images or []:
            (d / Path(img).name).write_bytes(Path(img).read_bytes()); imgs += f"- `{Path(img).name}`\n"
        body = (f"# Task {d.name}\n\n{summary or task}\n\n## What to do\n\n{system}\n\n"
                + (f"## Images (in this folder)\n\n{imgs}\n" if imgs else "")
                + f"## Input\n\n{prompt}\n\n## Answer format\n\nWrite `answer.json` in this folder: valid JSON with exactly this shape "
                  f"(lists may have any length; use \"\" / [] when something does not apply):\n\n```json\n{ex}\n```\n")
        write_text(d / "TASK.md", body)
        if schema: write_json(d / "schema.json", schema)
        if hint is not None and (self.answerer or os.environ.get("STORYLENS_WRITE_HINTS")):   # hints only feed the offline answerer
            try: write_json(d / "hint.json", hint)
            except TypeError: pass
        write_json(d / "meta.json", {"id": d.name, "task": task, "kind": task.split("-")[0], "summary": summary or task, "job": self.job.id if self.job else "",
                                     "title": (self.job.spec.get("title") if self.job else ""), "key": key, "status": "open", "created": now()})
        self.usage["tasks"] += 1
        p = Pending(d, key, schema, task)
        if self.answerer:
            write_json(d / "answer.json", self.answerer(task, hint))
        else:
            write_queue(self.ws)
            if self.job:
                self.job.log(f"waiting for Claude: {d.name}"); self.job.update(status="waiting_for_claude")
        return p

    # ----- wait
    def wait(self, p):
        if not isinstance(p, Pending): return p
        tries = 0
        while True:
            a = p.dir / "answer.json"
            if a.exists():
                time.sleep(0.3)
                try:
                    data = json.loads(a.read_text(encoding="utf-8"))
                    errs = validate(data, p.schema) if p.schema else []
                except json.JSONDecodeError as e:
                    data, errs = None, [f"answer.json is not valid JSON: {e}"]
                if not errs:
                    write_json(self.cache / f"{p.key}.json", data)
                    m = read_json(p.dir / "meta.json"); m.update(status="done", answered=now()); write_json(p.dir / "meta.json", m)
                    (p.dir / "ANSWER_ERRORS.md").unlink(missing_ok=True)
                    write_queue(self.ws)
                    if self.job and not self.answerer and self.job.state.get("status") == "waiting_for_claude":
                        self.job.update(status="running", message="")
                    return data
                tries += 1; self.usage["rejected"] += 1
                a.rename(p.dir / f"answer.rejected-{tries}.json")
                write_text(p.dir / "ANSWER_ERRORS.md", "# The answer was not accepted\n\nFix these problems and write `answer.json` again:\n\n"
                           + "\n".join(f"- {e}" for e in errs[:30]) + "\n")
                write_queue(self.ws)
                if self.answerer: raise TaskError(f"{p.dir.name}: invalid answer: {errs[:3]}")
            if not self.answerer and time.time() - _said[0] > 30:
                _said[0] = time.time()
                print(f"⏳ waiting for Claude — {len(list_tasks(self.ws, 'open'))} open task(s) in {tasks_dir(self.ws) / 'QUEUE.md'}", flush=True)
            if self.job and self.job.cancelled():
                cancel_job_tasks(self.ws, self.job.id); from .jobs import Cancelled; raise Cancelled("cancelled")
            time.sleep(self.ws.s.poll_seconds)

    def json(self, task, system, prompt, schema, images=None, hint=None, summary=None, **kw):
        return self.wait(self.submit(task, system, prompt, schema, images=images, hint=hint, summary=summary))

    def many(self, specs):
        """Queue several tasks at once (Claude can do them in one sitting), then wait for all of them."""
        ps = [self.submit(**s) for s in specs]
        return [self.wait(p) for p in ps]


def _mock_answerer():
    from .testing import MockAnswerer
    m = MockAnswerer()
    return lambda task, hint: m.answer(task, hint)
