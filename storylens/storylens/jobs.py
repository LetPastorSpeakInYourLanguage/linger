"""Jobs: folder-based, resumable, reviewable units of work (docs/AGENTIC.md).

jobs/<id>/job.json        {"kind", "title", "params", "instructions", "autonomy"}
jobs/<id>/state.json      {"status": queued|running|awaiting_review|waiting_for_agent|done|failed|cancelled, "stage", "progress", "message"}
jobs/<id>/events.jsonl    append-only log
jobs/<id>/steps/NNNN-*    one folder per LLM call (prompt.md, schema.json, response.json, meta.json)
jobs/<id>/review/<gate>.md + <gate>.metrics.json -> <gate>.decision.json   (human or autopilot)
jobs/<id>/inbox/*.md      instructions sent while the job runs (merged into later prompts)
jobs/<id>/artifacts/      outputs (script.json, edl.json, recap.mp4, report.md …)
"""
from __future__ import annotations
import threading, time, traceback
from pathlib import Path
from .util import read_json, write_json, write_text, append_jsonl, new_id, now


class Cancelled(RuntimeError):
    pass


class Job:
    def __init__(self, ws, job_id):
        self.ws, self.id = ws, job_id
        self.dir = Path(ws.jobs) / job_id
        self.spec = read_json(self.dir / "job.json", {})
        self.on_gate = None   # optional callable(name, markdown, metrics) -> decision dict (CLI interactive review)

    # ---------- lifecycle
    @classmethod
    def create(cls, ws, kind, title, params=None, instructions="", autonomy=None):
        jid = new_id(kind)
        d = Path(ws.jobs) / jid
        for sub in ("steps", "review", "inbox", "artifacts"): (d / sub).mkdir(parents=True, exist_ok=True)
        write_json(d / "job.json", {"id": jid, "kind": kind, "title": title, "params": params or {}, "instructions": instructions,
                                    "autonomy": autonomy or ws.s.autonomy, "created": now()})  # autonomy: gates | autopilot | auto
        write_json(d / "state.json", {"status": "queued", "stage": "", "progress": 0.0, "message": "", "updated": now()})
        job = cls(ws, jid); job.event("created", kind=kind, title=title)
        return job

    @property
    def state(self): return read_json(self.dir / "state.json", {})

    def update(self, **kw):
        st = self.state; st.update(kw); st["updated"] = now(); write_json(self.dir / "state.json", st)

    def event(self, event, **kw):
        append_jsonl(self.dir / "events.jsonl", {"t": now(), "event": event, **kw})

    def log(self, msg):
        self.event("log", msg=msg); self.update(message=msg)

    def stage(self, name, progress=None):
        self.update(stage=name, **({"progress": progress} if progress is not None else {})); self.event("stage", stage=name)

    def cancelled(self) -> bool: return (self.dir / "CANCEL").exists()

    def check_cancel(self):
        if self.cancelled(): raise Cancelled("cancelled")

    def cancel(self): write_text(self.dir / "CANCEL", "1")

    def artifact(self, name) -> Path: return self.dir / "artifacts" / name

    def instructions(self) -> str: return self.ws.instructions(self.spec.get("title"), self.dir)

    def send(self, text):
        n = len(list((self.dir / "inbox").glob("*.md"))) + 1
        write_text(self.dir / "inbox" / f"{n:03d}.md", text); self.event("inbox", text=text)

    # ---------- review gates
    def gate(self, name, markdown, metrics=None, rules=None):
        """Block until the gate is decided. Autopilot approves when every rule(metrics) holds."""
        write_text(self.dir / "review" / f"{name}.md", markdown)
        write_json(self.dir / "review" / f"{name}.metrics.json", metrics or {})
        dec_p = self.dir / "review" / f"{name}.decision.json"
        mode = self.spec.get("autonomy")
        if mode in ("autopilot", "auto") and not dec_p.exists():
            failed = [i for i, r in enumerate(rules or []) if not r(metrics or {})]
            if not failed:
                write_json(dec_p, {"decision": "approve", "by": "autopilot", "t": now()})
            elif mode == "auto":   # unattended: approve anyway, but record what a human should look at
                write_json(dec_p, {"decision": "approve", "by": "auto", "warnings": f"{len(failed)} gate rule(s) not met", "t": now()})
                self.event("gate_warning", gate=name, failed_rules=failed, metrics=metrics)
        self.event("gate", gate=name); self.update(status="awaiting_review", stage=f"review: {name}")
        if not dec_p.exists() and self.on_gate:
            d = self.on_gate(name, markdown, metrics or {})
            if d: self.decide(name, d.get("decision", "approve"), d.get("notes", ""), d.get("edits"), by="cli")
        while not dec_p.exists():
            self.check_cancel(); time.sleep(1.0)
        d = read_json(dec_p)
        self.event("gate_decided", gate=name, **d); self.update(status="running")
        if d.get("decision") == "reject": raise Cancelled(f"rejected at {name}: {d.get('notes', '')}")
        return d

    def decide(self, gate, decision, notes="", edits=None, by="human"):
        write_json(self.dir / "review" / f"{gate}.decision.json", {"decision": decision, "notes": notes, "edits": edits or {}, "by": by, "t": now()})


def list_jobs(ws, title=None):
    out = []
    for p in sorted(Path(ws.jobs).glob("*/job.json"), reverse=True):
        j = read_json(p); j["state"] = read_json(p.parent / "state.json", {})
        if title is None or j.get("title") == title: out.append(j)
    return out


def pending_steps(ws):
    """Steps waiting for an agent/human answer — only in jobs that are still alive."""
    out = []
    for p in Path(ws.jobs).glob("*/steps/*/WAITING"):
        st = read_json(p.parent.parent.parent / "state.json", {}).get("status")
        if st in ("running", "queued", "awaiting_review", "waiting_for_agent"): out.append(str(p.parent))
    return sorted(out)


def run_job(job, fn, background=False):
    """Run fn(job) with status bookkeeping; in a thread when background=True (web server)."""
    def target():
        job.update(status="running"); job.event("started")
        try:
            fn(job)
            job.update(status="done", progress=1.0, stage="done"); job.event("done")
        except Cancelled as e:
            job.update(status="cancelled", message=str(e)); job.event("cancelled", msg=str(e))
        except Exception as e:
            job.update(status="failed", message=f"{type(e).__name__}: {e}")
            job.event("failed", error=str(e), trace=traceback.format_exc()[-3000:])
            if not background: raise
    if background:
        th = threading.Thread(target=target, daemon=True); th.start(); return th
    target()
