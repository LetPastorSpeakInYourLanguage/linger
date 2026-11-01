"""Settings: defaults < workspace settings.json < environment variables (STORYLENS_*)."""
from __future__ import annotations
import json, os
from dataclasses import dataclass, field, asdict
from pathlib import Path

@dataclass
class Settings:
    workspace: str = ""
    answerer: str = "claude"           # claude = tasks wait in tasks/ for Claude (desktop app) | mock = offline demo/tests
    autonomy: str = "gates"            # gates (you approve G1/G2/G3) | autopilot (approve when checks pass) | auto (approve all)
    chunk_lines: int = 220             # subtitle lines per understanding task (bigger = fewer tasks for Claude)
    vision: str = "off"                # off | gaps: one keyframe contact-sheet task per media for dialogue-free stretches
    review: bool = False               # extra Claude review task for every script (deterministic checks always run)
    max_parallel: int = 4
    poll_seconds: float = 1.5
    tts: str = "auto"                  # auto | kokoro | system | none
    voice: str = "am_michael"
    wps: float = 2.6                   # narration words per second used for planning
    host: str = "127.0.0.1"
    port: int = 8765

    def save(self):
        p = Path(self.workspace) / "settings.json"
        d = asdict(self); d.pop("workspace")
        p.write_text(json.dumps(d, indent=2), encoding="utf-8")


def default_workspace() -> Path:
    return Path(os.environ.get("STORYLENS_WORKSPACE", Path.home() / "storylens-workspace"))


def load(workspace: str | os.PathLike | None = None) -> Settings:
    ws = Path(workspace) if workspace else default_workspace()
    s = Settings(workspace=str(ws.resolve()))
    p = ws / "settings.json"
    if p.exists():
        for k, v in json.loads(p.read_text(encoding="utf-8")).items():
            if hasattr(s, k) and k != "workspace": setattr(s, k, v)
    env = {"STORYLENS_ANSWERER": "answerer", "STORYLENS_AUTONOMY": "autonomy", "STORYLENS_TTS": "tts", "STORYLENS_VOICE": "voice"}
    for e, k in env.items():
        if os.environ.get(e): setattr(s, k, os.environ[e])
    if os.environ.get("STORYLENS_PORT"): s.port = int(os.environ["STORYLENS_PORT"])
    return s
