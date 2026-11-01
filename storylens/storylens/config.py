"""Settings: defaults < workspace settings.json < environment variables (STORYLENS_*)."""
from __future__ import annotations
import json, os
from dataclasses import dataclass, field, asdict
from pathlib import Path

DEFAULT_MODEL = "claude-opus-5-5"


@dataclass
class Settings:
    workspace: str = ""
    llm_backend: str = "auto"          # auto | anthropic | folder | mock
    model: str = DEFAULT_MODEL         # main reasoning model (integration, scripts, verification)
    bulk_model: str = DEFAULT_MODEL    # per-chunk extraction (P1, lens, trait checks); e.g. claude-sonnet-5-5 to save cost
    effort: dict = field(default_factory=lambda: {"cards": "medium", "integrate": "high", "causal": "medium",
                                                  "view": "medium", "script": "high", "verify": "medium", "zoom": "medium"})
    fallbacks: bool = True             # server-side refusal fallback ("default" routing)
    structured_outputs: bool = True    # JSON-schema constrained outputs
    max_tokens: int = 64000
    max_parallel: int = 4              # parallel LLM calls (per-episode P1, lens, verification)
    chunk_lines: int = 160             # subtitle lines per P1 chunk
    autonomy: str = "gates"            # gates | autopilot  (human review at G1/G2/G3 or auto-pass on metrics)
    folder_poll_seconds: float = 2.0
    folder_timeout_seconds: float = 0  # 0 = wait forever for an agent/human to answer a folder step
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
            if hasattr(s, k) and k != "workspace":
                if k == "effort": s.effort.update(v)
                else: setattr(s, k, v)
    env = {"STORYLENS_LLM": "llm_backend", "STORYLENS_MODEL": "model", "STORYLENS_BULK_MODEL": "bulk_model",
           "STORYLENS_AUTONOMY": "autonomy", "STORYLENS_TTS": "tts", "STORYLENS_VOICE": "voice"}
    for e, k in env.items():
        if os.environ.get(e): setattr(s, k, os.environ[e])
    if os.environ.get("STORYLENS_PORT"): s.port = int(os.environ["STORYLENS_PORT"])
    return s
