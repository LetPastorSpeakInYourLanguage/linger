"""Workspace = the folder that is the app's source of truth (see docs/AGENTIC.md).

<ws>/CLAUDE.md  CATALOG.md  settings.json  instructions.md
<ws>/tasks/QUEUE.md  tasks/<NNNN-task>/{TASK.md, answer.json, meta.json}      what Claude answers (tasks.py)
<ws>/requests/new|done|failed/*.json                                         what Claude asks for (watch.py, actions.py)
<ws>/library/<title>/title.json  instructions.md  corrections.jsonl  index.sqlite
                    evidence/<media>/cues.jsonl media.json shots.json speech.json keyframes/
                    understanding/vNNN/{cards/,facts.jsonl,beats.jsonl,edges.jsonl,moments.jsonl,characters.json,bible.json,MANIFEST.json}
                    understanding/CURRENT
                    views/<view-id>/view.json
<ws>/jobs/<job>/job.json state.json events.jsonl review/ inbox/ artifacts/
"""
from __future__ import annotations
import re, shutil
from pathlib import Path
from . import config as C
from .util import read_json, write_json, write_text, read_jsonl, append_jsonl, slug, now

VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".m4v", ".webm", ".ts", ".wmv",
             ".mp3", ".m4a", ".wav", ".ogg", ".opus", ".flac", ".aac"}   # audio-only media (podcasts, sermons) too
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".ogg", ".opus", ".flac", ".aac"}
SUB_EXT = {".srt", ".vtt", ".ass", ".ssa", ".sub", ".txt", ".md", ".json"}
KINDS = {"film": "narrative", "series": "narrative", "podcast": "discourse", "talkshow": "discourse", "sermon": "discourse", "lecture": "discourse"}


def profile(t) -> str:
    """narrative (films, series, telenovelas) or discourse (podcasts, talk shows, sermons, lectures)."""
    return KINDS.get(t.get("kind", "film"), "narrative")
EP_RE = re.compile(r"[Ss](\d{1,2})[ ._-]?[Ee](\d{1,3})|(\d{1,2})x(\d{2})")

CLAUDE_MD = (Path(__file__).parent / "CLAUDE_WORKSPACE.md").read_text(encoding="utf-8")


class Workspace:
    def __init__(self, settings: C.Settings):
        self.s = settings
        self.root = Path(settings.workspace)
        self.library = self.root / "library"
        self.jobs = self.root / "jobs"

    # ---------- setup
    def init(self):
        for d in (self.library, self.jobs): d.mkdir(parents=True, exist_ok=True)
        if not (self.root / "settings.json").exists(): self.s.save()
        for sub in ("tasks", "requests/new", "requests/done", "requests/failed"): (self.root / sub).mkdir(parents=True, exist_ok=True)
        cm = self.root / "CLAUDE.md"
        if not cm.exists() or "<!-- storylens:managed" in cm.read_text(encoding="utf-8"):
            write_text(cm, CLAUDE_MD + "\n<!-- storylens:managed — delete this line to keep your own edits -->\n")
        if not (self.root / "instructions.md").exists():
            write_text(self.root / "instructions.md", "# Global instructions (apply to every job)\n\n"
                       "- Present tense, chronological, cite subtitle line ids for every claim.\n"
                       "- Never use knowledge about the title from outside the provided subtitles/frames.\n")
        return self

    # ---------- titles
    def tdir(self, tid) -> Path: return self.library / tid

    def titles(self):
        out = []
        for p in sorted(self.library.glob("*/title.json")):
            t = read_json(p); t["understanding_version"] = self.current_version(t["id"]); out.append(t)
        return out

    def title(self, tid) -> dict:
        t = read_json(self.tdir(tid) / "title.json")
        if t is None: raise KeyError(f"unknown title {tid}")
        return t

    def save_title(self, t): write_json(self.tdir(t["id"]) / "title.json", t)

    def create_title(self, name, kind="film", language="", cast=None):
        tid = slug(name)
        base, i = tid, 2
        while self.tdir(tid).exists(): tid = f"{base}-{i}"; i += 1
        t = {"id": tid, "name": name, "kind": kind, "language": language, "cast": cast or [], "media": [], "created": now()}
        self.save_title(t)
        write_text(self.tdir(tid) / "instructions.md", f"# Notes for {name}\n\n(Add title-specific guidance here, e.g. 'the twins are played by one actor'.)\n")
        return t

    def add_media(self, tid, video=None, subs=None, season=None, episode=None, label=None):
        t = self.title(tid)
        mid = f"m{len(t['media']) + 1:03d}"
        if season is None and (video or subs):
            m = EP_RE.search(Path(video or subs).name)
            if m: season, episode = int(m.group(1) or m.group(3)), int(m.group(2) or m.group(4))
        entry = {"id": mid, "video": str(Path(video).resolve()) if video else None, "subs": str(Path(subs).resolve()) if subs else None,
                 "season": season, "episode": episode, "label": label or Path(video or subs or mid).stem}
        t["media"].append(entry)
        t["media"].sort(key=lambda m: ((m.get("season") or 0), (m.get("episode") or 0), m["id"]))
        if len(t["media"]) > 1 and t["kind"] == "film" and any(m.get("episode") for m in t["media"]): t["kind"] = "series"
        self.save_title(t)
        return entry

    def scan_folder(self, tid, folder):
        """Pair videos with subtitle files by name (movie.mkv + movie.srt / movie.en.srt); subtitle-only also allowed."""
        folder = Path(folder); added = []
        vids = sorted(p for p in folder.rglob("*") if p.suffix.lower() in VIDEO_EXT)
        subs = sorted(p for p in folder.rglob("*") if p.suffix.lower() in SUB_EXT)
        subs = [s for s in subs if s.suffix.lower() not in (".txt", ".md", ".json") or any(s.stem.lower().startswith(v.stem.lower()) for v in vids)] \
            if vids else subs
        def pick(stem):
            c = [s for s in subs if s.name.lower().startswith(stem.lower())]
            en = [s for s in c if re.search(r"\.(en|eng|english)\.", s.name, re.I)]
            return (en or c or [None])[0]
        used = set()
        for v in vids:
            s = pick(v.stem); used.add(s)
            added.append(self.add_media(tid, video=v, subs=s))
        for s in subs:
            if s not in used and not any(s.name.lower().startswith(v.stem.lower()) for v in vids):
                added.append(self.add_media(tid, subs=s))
        return added

    # ---------- understanding versions
    def udir(self, tid) -> Path: return self.tdir(tid) / "understanding"

    def current_version(self, tid):
        p = self.udir(tid) / "CURRENT"
        return p.read_text().strip() if p.exists() else None

    def vdir(self, tid, version=None) -> Path:
        v = version or self.current_version(tid)
        if not v: raise FileNotFoundError("title has no understanding yet")
        return self.udir(tid) / v

    def new_version(self, tid) -> str:
        vs = sorted(p.name for p in self.udir(tid).glob("v[0-9][0-9][0-9]")) if self.udir(tid).exists() else []
        v = f"v{(int(vs[-1][1:]) + 1) if vs else 1:03d}"
        (self.udir(tid) / v).mkdir(parents=True, exist_ok=True)
        return v

    def set_current(self, tid, version): write_text(self.udir(tid) / "CURRENT", version)

    def edir(self, tid, mid) -> Path: return self.tdir(tid) / "evidence" / mid

    # ---------- corrections & instructions
    def corrections(self, tid): return read_jsonl(self.tdir(tid) / "corrections.jsonl")

    def add_correction(self, tid, target, field, value, reason="", by="human"):
        append_jsonl(self.tdir(tid) / "corrections.jsonl", {"target": target, "field": field, "value": value, "reason": reason, "by": by, "t": now()})

    def instructions(self, tid=None, job_dir=None) -> str:
        parts = []
        for p in [self.root / "instructions.md"] + ([self.tdir(tid) / "instructions.md"] if tid else []):
            if p.exists():
                txt = p.read_text(encoding="utf-8").strip()
                if txt and "(Add title-specific guidance here" not in txt: parts.append(txt)
        if job_dir:
            j = read_json(Path(job_dir) / "job.json", {})
            if j.get("instructions"): parts.append("Job instructions: " + j["instructions"])
            inbox = Path(job_dir) / "inbox"
            if inbox.exists():
                parts += [f"Message: {p.read_text(encoding='utf-8').strip()}" for p in sorted(inbox.glob("*.md"))]
        return "\n\n".join(parts)

    def delete_title(self, tid): shutil.rmtree(self.tdir(tid), ignore_errors=True)
