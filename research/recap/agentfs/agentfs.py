"""agentfs — minimal reference implementation of the folder protocol (02_agentic_folder_protocol.md).

No server, no DB: a job is a folder; a step is a folder; workers claim steps by atomic rename; humans answer
gates by writing a decision file. Any agent runtime (Agent SDK, Claude Code headless, Messages-API loop, a human)
can be a worker. JSON is used for zero dependencies (YAML is equivalent).
"""
from __future__ import annotations
import hashlib, json, os, socket, time

def _w(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1) if not isinstance(obj, str) else f.write(obj)
    os.replace(tmp, path)                                   # atomic publish

def log(job, event, **kw):
    with open(os.path.join(job, "events.jsonl"), "a") as f:
        f.write(json.dumps({"t": time.time(), "event": event, **kw}) + "\n")

def new_job(root, job_id, spec):
    job = os.path.join(root, "jobs", job_id)
    for d in ("steps", "review", "inbox", "outbox", "artifacts"): os.makedirs(os.path.join(job, d), exist_ok=True)
    _w(os.path.join(job, "job.json"), spec); _w(os.path.join(job, "state.json"), {"status": "planning", "steps": {}})
    log(job, "job_created", kind=spec.get("kind")); return job

def add_step(job, step_id, prompt, context=None, needs=(), worker="llm", schema=None):
    d = os.path.join(job, "steps", step_id)
    _w(os.path.join(d, "prompt.md"), prompt)
    for name, content in (context or {}).items(): _w(os.path.join(d, "context", name), content)
    key = hashlib.sha256((prompt + json.dumps(context or {}, sort_keys=True) + json.dumps(schema)).encode()).hexdigest()[:16]
    _w(os.path.join(d, "meta.json"), {"needs": list(needs), "worker": worker, "cache_key": key, "schema": schema})
    open(os.path.join(d, "READY"), "w").close(); log(job, "step_ready", step=step_id); return d

def claim(job, worker_id=None):
    """Atomically claim the first READY step whose dependencies are done."""
    worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
    for s in sorted(os.listdir(os.path.join(job, "steps"))):
        d = os.path.join(job, "steps", s)
        meta = json.load(open(os.path.join(d, "meta.json")))
        if not all(os.path.exists(os.path.join(job, "steps", n, "response.json")) for n in meta["needs"]): continue
        try:
            os.rename(os.path.join(d, "READY"), os.path.join(d, f"CLAIMED.{worker_id}"))
        except FileNotFoundError:
            continue
        log(job, "step_claimed", step=s, worker=worker_id); return s, d
    return None, None

def complete(job, step_id, response, tokens=None, model=None):
    d = os.path.join(job, "steps", step_id)
    _w(os.path.join(d, "response.json"), response)
    meta = json.load(open(os.path.join(d, "meta.json"))); meta.update({"done": time.time(), "tokens": tokens, "model": model})
    _w(os.path.join(d, "meta.json"), meta); log(job, "step_done", step=step_id)

def request_gate(job, gate, markdown, metrics, autopilot_rules=None):
    _w(os.path.join(job, "review", f"{gate}.md"), markdown); _w(os.path.join(job, "review", f"{gate}.metrics.json"), metrics)
    spec = json.load(open(os.path.join(job, "job.json")))
    if spec.get("autonomy") == "autopilot" and autopilot_rules and all(rule(metrics) for rule in autopilot_rules):
        _w(os.path.join(job, "review", f"{gate}.decision.json"), {"decision": "approve", "by": "autopilot"})
    log(job, "gate_requested", gate=gate)

def gate_decision(job, gate):
    p = os.path.join(job, "review", f"{gate}.decision.json")
    return json.load(open(p)) if os.path.exists(p) else None

def instructions(root, title, job):
    """Merge instruction layers (later wins): global -> title -> job -> inbox messages."""
    parts = []
    for p in (os.path.join(root, "instructions.md"), os.path.join(root, "library", title, "instructions.md")):
        if os.path.exists(p): parts.append(open(p).read())
    spec = json.load(open(os.path.join(job, "job.json")))
    if spec.get("instructions"): parts.append(spec["instructions"])
    inbox = os.path.join(job, "inbox")
    parts += [open(os.path.join(inbox, f)).read() for f in sorted(os.listdir(inbox))]
    return "\n\n---\n".join(parts)
