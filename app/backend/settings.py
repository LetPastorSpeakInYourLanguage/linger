"""Persistent app settings — higher-order control surfaced in the UI.

A small key/value store. Each known key has a schema entry (default, type, the
env var it may fall back to, and UI metadata). Resolution order when the app
reads a setting: **DB value (set in the UI) → env var → default**, so the
Settings page is authoritative but env still works for headless setups.
"""
from __future__ import annotations

import json
import os

from .db import get_db

# group | label | type | default | env (fallback) | options (for selects)
SCHEMA: dict[str, dict] = {
    # --- transcription ---
    "whisper_model": {"group": "transcription", "label": "Default Whisper model",
                      "type": "select", "default": "small",
                      "env": "RECOMPOSER_WHISPER_MODEL",
                      "options": ["tiny", "tiny.en", "base", "base.en", "small",
                                  "small.en", "medium", "medium.en", "large-v2",
                                  "large-v3", "distil-large-v3"]},
    "whisper_device": {"group": "transcription", "label": "Device",
                       "type": "select", "default": "auto",
                       "env": "RECOMPOSER_WHISPER_DEVICE",
                       "options": ["auto", "cpu", "cuda"]},
    "whisper_compute": {"group": "transcription", "label": "Compute type",
                        "type": "select", "default": "auto",
                        "env": "RECOMPOSER_WHISPER_COMPUTE",
                        "options": ["auto", "int8", "float16", "float32"]},
    # --- AI ---
    "llm_provider": {"group": "ai", "label": "LLM provider", "type": "select",
                     "default": "auto", "env": "RECOMPOSER_LLM_PROVIDER",
                     "options": ["auto", "anthropic", "openai", "gemini",
                                 "ollama", "gpt4all", "none"]},
    "llm_model": {"group": "ai", "label": "LLM model (blank = provider default)",
                  "type": "text", "default": "", "env": "RECOMPOSER_LLM_MODEL"},
    "ollama_url": {"group": "ai", "label": "Ollama URL", "type": "text",
                   "default": "http://localhost:11434", "env": "RECOMPOSER_OLLAMA_URL"},
    "ai_chunk_lines": {"group": "ai", "label": "AI transcript chunk size (lines)",
                       "type": "int", "default": 400, "env": "RECOMPOSER_AI_CHUNK_LINES"},
    # --- recomposition / workflow defaults ---
    "default_recomp_language": {"group": "recomposition", "label": "Default target language",
                                "type": "lang", "default": "en"},
    "default_export_quality": {"group": "recomposition", "label": "Default export quality",
                               "type": "select", "default": "720p",
                               "options": ["480p", "720p", "1080p"]},
    "default_audio_mode": {"group": "recomposition", "label": "Default export audio",
                           "type": "select", "default": "original",
                           "options": ["original", "vocals_only", "dub"]},
    "default_keep_accompaniment": {"group": "recomposition",
                                   "label": "Keep background audio by default",
                                   "type": "bool", "default": True},
    "default_keep_source_vocals": {"group": "recomposition",
                                   "label": "Keep source vocals under dub by default",
                                   "type": "bool", "default": False},
    "default_search_lang": {"group": "recomposition", "label": "Default search language",
                            "type": "lang", "default": "en"},
    "default_smart_search": {"group": "recomposition", "label": "Smart (semantic) search on by default",
                             "type": "bool", "default": False},
}


def _parse(value, typ):
    if typ == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    if typ == "bool":
        return value in (True, 1, "1", "true", "True", "yes", "on")
    return value


def get(key: str):
    spec = SCHEMA.get(key)
    if spec is None:
        return None
    row = get_db().execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    if row is not None:
        try:
            return json.loads(row["value"])
        except (ValueError, TypeError):
            pass
    env = spec.get("env")
    if env and os.environ.get(env) not in (None, ""):
        return _parse(os.environ[env], spec.get("type"))
    return spec["default"]


def all_effective() -> dict:
    return {k: get(k) for k in SCHEMA}


def set_many(updates: dict) -> dict:
    db = get_db()
    for key, value in updates.items():
        spec = SCHEMA.get(key)
        if spec is None:
            continue
        value = _parse(value, spec.get("type"))
        db.execute(
            "INSERT INTO app_settings (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
            (key, json.dumps(value)))
    db.commit()
    return all_effective()
