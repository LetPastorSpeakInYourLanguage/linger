"""The requests/ inbox: how Claude (or you) asks storylens to do things by writing a file.

  requests/new/<anything>.json     write a request here ({"do": ..., see actions.py})
  requests/done/<name>.json        moved here when accepted: {"request", "job" | "result", "t"}
  requests/done/<name>.result.md   readable result for find / add_title
  requests/failed/<name>.json      {"request", "error"} when it could not be done

`storylens serve` runs this watcher in the background; `storylens watch` runs it alone (no web app).
Each tick it also harvests answers Claude wrote for tasks of jobs that are no longer running, so nothing is lost.
"""
from __future__ import annotations
import json, threading, time, traceback
from pathlib import Path
from .util import read_json, write_json, write_text, now
from . import actions, tasks, catalog
from .jobs import run_job


def rdir(ws, sub) -> Path:
    p = Path(ws.root) / "requests" / sub; p.mkdir(parents=True, exist_ok=True); return p


def _result_md(d, res):
    if d["do"] == "find":
        rows = res["results"]
        L = [f"# find: {d['query']}  (level {d.get('level', 'claim')}, {len(rows)} results)", ""]
        for r in rows:
            if "ref" in r:
                L.append(f"- **{r.get('title_name', '')}** `{r.get('title', '')}::{r.get('media', '')}` {r['ref']}"
                         f" {('[' + r['speaker'] + '] ') if r.get('speaker') else ''}{r['text']}")
            else:
                L.append(f"- **{r.get('title_name', '')}** {r.get('media') or ''} hits={r.get('hits')} — {' | '.join(r.get('examples', []))}")
        return "\n".join(L) + "\n"
    return "```json\n" + json.dumps(res, indent=1, ensure_ascii=False)[:20000] + "\n```\n"


def process(ws, background=True):
    """Handle every file in requests/new. Returns the list of (name, outcome)."""
    out = []
    for p in sorted(rdir(ws, "new").glob("*.json")):
        name = p.stem
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            if time.time() - p.stat().st_mtime < 3: continue     # probably still being written
            write_json(rdir(ws, "failed") / f"{name}.json", {"error": f"not valid JSON: {e}", "t": now()}); p.unlink(); continue
        reqs = d if isinstance(d, list) else [d]
        done = []
        try:
            for r in reqs:
                if r.get("do") in actions.JOB_ACTIONS:
                    job, fn = actions.job_for(ws, r)
                    run_job(job, fn, background=background)
                    done.append({"request": r, "job": job.id, "job_folder": f"jobs/{job.id}"})
                else:
                    res = actions.do_now(ws, r)
                    write_text(rdir(ws, "done") / f"{name}.result.md", _result_md(r, res))
                    done.append({"request": r, "result": res if r["do"] != "find" else {"count": len(res["results"]), "file": f"requests/done/{name}.result.md"}})
            write_json(rdir(ws, "done") / f"{name}.json", {"done": done, "t": now()}); out.append((name, "done"))
        except Exception as e:
            write_json(rdir(ws, "failed") / f"{name}.json", {"request": d, "done_before_error": done, "error": f"{type(e).__name__}: {e}",
                                                             "trace": traceback.format_exc()[-1500:], "t": now()})
            out.append((name, f"failed: {e}"))
        p.unlink(missing_ok=True)
    return out


def tick(ws, background=True):
    res = process(ws, background)
    tasks.harvest(ws)
    return res


def start_thread(ws, stop: threading.Event | None = None):
    stop = stop or threading.Event()
    tasks.mark_stale(ws); catalog.write(ws); tasks.write_queue(ws)

    def loop():
        while not stop.is_set():
            try: tick(ws)
            except Exception: traceback.print_exc()
            stop.wait(max(1.0, ws.s.poll_seconds))
    th = threading.Thread(target=loop, daemon=True, name="storylens-requests"); th.start()
    return stop


def watch_forever(ws):
    print(f"storylens is watching {ws.root}\n  Claude: tasks/QUEUE.md (answer tasks) · requests/new/*.json (ask for work) · CATALOG.md\n  Ctrl+C to stop")
    stop = start_thread(ws)
    try:
        while True: time.sleep(3600)
    except KeyboardInterrupt:
        stop.set()
