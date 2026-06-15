"""Provider-agnostic LLM operator.

One small interface — `complete_json(system, prompt) -> dict` — over many
backends so AI features never depend on a single vendor:

  anthropic  Claude          (ANTHROPIC_API_KEY)
  openai     ChatGPT / compatible (OPENAI_API_KEY, optional OPENAI_BASE_URL)
  gemini     Google Gemini   (GEMINI_API_KEY or GOOGLE_API_KEY)
  ollama     local models    (RECOMPOSER_OLLAMA_URL, default localhost:11434)
  gpt4all    local models    (pip install gpt4all + RECOMPOSER_GPT4ALL_MODEL)

Pick one with RECOMPOSER_LLM_PROVIDER (+ RECOMPOSER_LLM_MODEL), or leave it on
'auto' to use the first configured provider. HTTP providers go through `requests`
so no vendor SDK is required. Tests swap in a fake.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
from typing import Protocol

PROVIDER_ORDER = ["anthropic", "openai", "gemini", "ollama", "gpt4all"]
DEFAULT_MODELS = {
    "anthropic": "claude-opus-4-8",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-1.5-flash",
    "ollama": "llama3.1",
    "gpt4all": "Meta-Llama-3-8B-Instruct.Q4_0.gguf",
}


def _extract_json(text: str) -> dict:
    """Pull a JSON object out of a model reply (handles ```json fences + prose)."""
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise RuntimeError("LLM did not return JSON")
    return json.loads(text[start:end + 1])


class LLMEngine(Protocol):
    name: str
    provider: str

    def complete_json(self, system: str, prompt: str) -> dict: ...


class _JsonLLM:
    """Base: subclasses implement _complete_text; JSON parsing is shared."""
    provider = "base"

    def complete_json(self, system: str, prompt: str) -> dict:
        return _extract_json(self._complete_text(system, prompt))

    def _complete_text(self, system: str, prompt: str) -> str:
        raise NotImplementedError


def _requests():
    import requests
    return requests


class AnthropicEngine(_JsonLLM):
    provider = "anthropic"

    def __init__(self, model: str):
        self.model = model
        self.name = f"anthropic:{model}"

    def _complete_text(self, system, prompt):
        r = _requests().post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                     "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": self.model, "max_tokens": 4000, "system": system,
                  "messages": [{"role": "user", "content": prompt}]}, timeout=180)
        r.raise_for_status()
        data = r.json()
        return "".join(b.get("text", "") for b in data.get("content", [])
                       if b.get("type") == "text")


class OpenAIEngine(_JsonLLM):
    provider = "openai"

    def __init__(self, model: str):
        self.model = model
        self.name = f"openai:{model}"
        self.base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

    def _complete_text(self, system, prompt):
        r = _requests().post(
            f"{self.base}/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
            json={"model": self.model, "response_format": {"type": "json_object"},
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": prompt}]}, timeout=180)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


class GeminiEngine(_JsonLLM):
    provider = "gemini"

    def __init__(self, model: str):
        self.model = model
        self.name = f"gemini:{model}"

    def _complete_text(self, system, prompt):
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self.model}:generateContent?key={key}")
        r = _requests().post(url, json={
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"}}, timeout=180)
        r.raise_for_status()
        parts = r.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)


class OllamaEngine(_JsonLLM):
    provider = "ollama"

    def __init__(self, model: str):
        self.model = model
        self.name = f"ollama:{model}"
        self.base = _ollama_base()

    def _complete_text(self, system, prompt):
        r = _requests().post(f"{self.base}/api/chat", json={
            "model": self.model, "stream": False, "format": "json",
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}]}, timeout=600)
        r.raise_for_status()
        return r.json()["message"]["content"]


class GPT4AllEngine(_JsonLLM):
    provider = "gpt4all"

    def __init__(self, model: str):
        self.model = model
        self.name = f"gpt4all:{model}"
        self._m = None

    def _complete_text(self, system, prompt):
        from gpt4all import GPT4All
        if self._m is None:
            self._m = GPT4All(self.model)
        with self._m.chat_session(system_prompt=system):
            return self._m.generate(prompt + "\n\nReturn only JSON.", max_tokens=4000)


_BUILDERS = {
    "anthropic": AnthropicEngine, "openai": OpenAIEngine, "gemini": GeminiEngine,
    "ollama": OllamaEngine, "gpt4all": GPT4AllEngine,
}

_ollama_cache: bool | None = None


def _setting(key: str, default):
    """Read an app setting if the table/store is available, else fall back."""
    try:
        from . import settings
        return settings.get(key)
    except Exception:
        return default


def _ollama_base() -> str:
    return _setting("ollama_url", os.environ.get("RECOMPOSER_OLLAMA_URL",
                                                 "http://localhost:11434"))


def _ollama_up() -> bool:
    global _ollama_cache
    if _ollama_cache is not None:
        return _ollama_cache
    _ollama_cache = False
    if importlib.util.find_spec("requests"):
        try:
            _ollama_cache = _requests().get(f"{_ollama_base()}/api/tags", timeout=1.0).ok
        except Exception:
            _ollama_cache = False
    return _ollama_cache


def provider_available(provider: str) -> bool:
    have_requests = importlib.util.find_spec("requests") is not None
    if provider == "anthropic":
        return have_requests and bool(os.environ.get("ANTHROPIC_API_KEY"))
    if provider == "openai":
        return have_requests and bool(os.environ.get("OPENAI_API_KEY"))
    if provider == "gemini":
        return have_requests and bool(os.environ.get("GEMINI_API_KEY")
                                      or os.environ.get("GOOGLE_API_KEY"))
    if provider == "ollama":
        return have_requests and _ollama_up()
    if provider == "gpt4all":
        return (importlib.util.find_spec("gpt4all") is not None
                and bool(os.environ.get("RECOMPOSER_GPT4ALL_MODEL")))
    return False


def configured_providers() -> list[str]:
    return [p for p in PROVIDER_ORDER if provider_available(p)]


def _model_for(provider: str) -> str:
    return (str(_setting("llm_model", os.environ.get("RECOMPOSER_LLM_MODEL", ""))).strip()
            or (os.environ.get("RECOMPOSER_GPT4ALL_MODEL", "") if provider == "gpt4all" else "")
            or DEFAULT_MODELS.get(provider, ""))


def _build(provider: str) -> LLMEngine | None:
    builder = _BUILDERS.get(provider)
    return builder(_model_for(provider)) if builder else None


_engine: LLMEngine | None = None
_resolved = False


def get_llm_engine() -> LLMEngine | None:
    global _engine, _resolved
    if _resolved:
        return _engine
    _resolved = True
    forced = str(_setting("llm_provider",
                          os.environ.get("RECOMPOSER_LLM_PROVIDER", ""))).strip().lower()
    if forced and forced not in ("auto", "none", ""):
        _engine = _build(forced)              # honor an explicit choice
    elif forced == "none":
        _engine = None
    else:
        chosen = next((p for p in PROVIDER_ORDER if provider_available(p)), None)
        _engine = _build(chosen) if chosen else None
    return _engine


def set_llm_engine(engine: LLMEngine | None):
    global _engine, _resolved
    _engine = engine
    _resolved = True


def reset():
    """Re-resolve on next call (after env changes)."""
    global _engine, _resolved, _ollama_cache
    _engine = None
    _resolved = False
    _ollama_cache = None


def available() -> bool:
    return get_llm_engine() is not None


def status() -> dict:
    eng = get_llm_engine()
    return {"available": eng is not None,
            "provider": getattr(eng, "provider", None),
            "model": getattr(eng, "name", None),
            "configured": configured_providers()}
