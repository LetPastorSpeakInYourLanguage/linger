from __future__ import annotations
import threading
from dataclasses import dataclass, field
from pathlib import Path
from ..util import write_text, write_json, read_json, sha, now, append_jsonl
from .backends import make_backend, LLMError, PendingAnswer  # noqa


@dataclass
class Call:
    task: str
    system: str
    prompt: str
    schema: dict | None
    model: str
    effort: str
    max_tokens: int
    images: list = field(default_factory=list)
    step_dir: str = ""
    hint: object = None          # structured input for the mock backend (ignored by real backends)


def _validate(data, schema, path="$"):
    """Light structural check (required keys / types) so a malformed answer fails loudly at the step."""
    if schema is None: return
    t = schema.get("type")
    if t == "object":
        if not isinstance(data, dict): raise LLMError(f"{path}: expected object")
        for k in schema.get("required", []):
            if k not in data: raise LLMError(f"{path}: missing '{k}'")
        for k, sub in schema.get("properties", {}).items():
            if k in data and data[k] is not None: _validate(data[k], sub, f"{path}.{k}")
    elif t == "array":
        if not isinstance(data, list): raise LLMError(f"{path}: expected array")
        for i, x in enumerate(data[:200]): _validate(x, schema.get("items", {}), f"{path}[{i}]")


class LLMRunner:
    """Writes every LLM call as a step folder inside the job, with a workspace-wide content cache."""

    def __init__(self, ws, job_dir, cancelled=lambda: False, log=print):
        self.ws, self.s = ws, ws.s
        self.job_dir = Path(job_dir)
        self.backend = make_backend(self.s, cancelled)
        self.cache = Path(ws.root) / ".cache" / "llm"
        self.lock = threading.Lock(); self.n = 0; self.log = log
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cached_steps": 0}

    def json(self, task, system, prompt, schema, role="main", effort_key="script", images=None, hint=None, max_tokens=None):
        model = self.s.bulk_model if role == "bulk" else self.s.model
        effort = self.s.effort.get(effort_key, "medium")
        key = sha(system, prompt, schema, model, [Path(i).name for i in images or []])
        with self.lock:
            self.n += 1; n = self.n
        d = self.job_dir / "steps" / f"{n:04d}-{task}"
        d.mkdir(parents=True, exist_ok=True)
        write_text(d / "prompt.md", f"<!-- task: {task} | model: {model} | effort: {effort} | cache_key: {key} -->\n\n"
                                    f"# SYSTEM\n\n{system}\n\n# USER\n\n{prompt}\n")
        if schema is not None: write_json(d / "schema.json", schema)
        for img in images or []:
            (d / Path(img).name).write_bytes(Path(img).read_bytes())
        cached = read_json(self.cache / f"{key}.json")
        if cached is not None:
            write_json(d / "response.json", cached)
            write_json(d / "meta.json", {"task": task, "cache_key": key, "cached": True, "model": model})
            self.usage["cached_steps"] += 1
            return cached
        call = Call(task, system, prompt, schema, model, effort, max_tokens or self.s.max_tokens, list(images or []), str(d), hint)
        t0 = now()
        data, usage = self.backend.complete(call)
        _validate(data, schema)
        write_json(d / "response.json", data)
        meta = {"task": task, "cache_key": key, "cached": False, "model": model, "effort": effort, "seconds": round(now() - t0, 1), **usage}
        write_json(d / "meta.json", meta)
        write_json(self.cache / f"{key}.json", data)
        with self.lock:
            self.usage["calls"] += 1
            for k in ("input_tokens", "output_tokens", "cache_read_input_tokens"): self.usage[k] += usage.get(k, 0) or 0
        append_jsonl(self.job_dir / "events.jsonl", {"t": now(), "event": "llm_step", "task": task, **{k: meta.get(k) for k in ("seconds", "input_tokens", "output_tokens")}})
        return data
