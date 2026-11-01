"""Small helpers: atomic JSON/JSONL IO, ids, hashing, time formatting. Windows-safe (pathlib, os.replace)."""
from __future__ import annotations
import hashlib, json, os, re, time, uuid
from pathlib import Path


def read_json(p, default=None):
    p = Path(p)
    if not p.exists(): return default
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(p, obj):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def write_text(p, text):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(text, encoding="utf-8"); os.replace(tmp, p)


def read_jsonl(p):
    p = Path(p)
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_jsonl(p, rows):
    write_text(p, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def append_jsonl(p, row):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def slug(s: str, n=48) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.lower()).strip("-")
    return (s or "x")[:n]


def sha(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p if isinstance(p, bytes) else json.dumps(p, sort_keys=True, ensure_ascii=False).encode())
    return h.hexdigest()[:16]


def now() -> float:
    return time.time()


def ts(sec: float) -> str:
    sec = max(0, int(sec)); h, r = divmod(sec, 3600); m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def new_id(prefix: str) -> str:
    return f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
