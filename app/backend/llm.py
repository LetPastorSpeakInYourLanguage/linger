"""Optional LLM backend (the official Anthropic SDK) behind a tiny interface, so
AI features (compose ordering, titling) work when ANTHROPIC_API_KEY is set and
degrade gracefully otherwise. Tests swap in a fake.
"""
from __future__ import annotations

import json
import os
from typing import Protocol

# Latest Claude models (see project guidance): compose = quality, bulk = cheap.
COMPOSE_MODEL = os.environ.get("RECOMPOSER_LLM_MODEL", "claude-opus-4-8")


class LLMEngine(Protocol):
    name: str

    def complete_json(self, system: str, prompt: str) -> dict:
        """Return a parsed JSON object from the model."""


class AnthropicEngine:
    def __init__(self, model: str = COMPOSE_MODEL):
        self.model = model
        self.name = f"anthropic:{model}"

    def complete_json(self, system: str, prompt: str) -> dict:
        import anthropic
        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        msg = client.messages.create(
            model=self.model, max_tokens=2000, system=system,
            messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            raise RuntimeError("LLM did not return JSON")
        return json.loads(text[start:end + 1])


_engine: LLMEngine | None = None
_resolved = False


def get_llm_engine() -> LLMEngine | None:
    global _engine, _resolved
    if _resolved:
        return _engine
    _resolved = True
    import importlib.util
    if os.environ.get("ANTHROPIC_API_KEY") and importlib.util.find_spec("anthropic"):
        _engine = AnthropicEngine()
    return _engine


def set_llm_engine(engine: LLMEngine | None):
    global _engine, _resolved
    _engine = engine
    _resolved = True


def available() -> bool:
    return get_llm_engine() is not None
