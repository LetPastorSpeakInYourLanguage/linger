"""Multi-provider LLM operator: JSON extraction + env-driven provider selection."""
import os

import pytest

from backend import llm


def test_extract_json_variants():
    assert llm._extract_json('{"a": 1}') == {"a": 1}
    assert llm._extract_json('here you go:\n{"a": 2} thanks') == {"a": 2}
    assert llm._extract_json('```json\n{"a": 3}\n```') == {"a": 3}
    with pytest.raises(RuntimeError):
        llm._extract_json("no json here")


KEYS = ["RECOMPOSER_LLM_PROVIDER", "RECOMPOSER_LLM_MODEL", "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "RECOMPOSER_GPT4ALL_MODEL"]


def _clean_env(**overrides):
    """Clear all LLM env keys, apply overrides; return a restore callable."""
    saved = {k: os.environ.get(k) for k in KEYS}
    env = {k: None for k in KEYS}
    env.update(overrides)
    for k, v in env.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    llm.reset()

    def restore():
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        llm.reset()
    return restore


def test_forced_provider_is_honored():
    restore = _clean_env(RECOMPOSER_LLM_PROVIDER="ollama")
    try:
        eng = llm.get_llm_engine()
        assert eng and eng.provider == "ollama"
    finally:
        restore()


def test_auto_selects_by_priority_and_keys():
    restore = _clean_env(OPENAI_API_KEY="sk-test")
    try:
        # auto prefers the highest-priority configured provider (no api-key
        # providers above openai here); ollama may also be up locally
        assert llm.get_llm_engine().provider == "openai"
        assert "openai" in llm.configured_providers()
    finally:
        restore()

    restore = _clean_env(ANTHROPIC_API_KEY="x", OPENAI_API_KEY="y")
    try:
        assert llm.get_llm_engine().provider == "anthropic"  # outranks openai
        assert {"anthropic", "openai"} <= set(llm.configured_providers())
    finally:
        restore()


def test_none_disables_llm():
    restore = _clean_env(RECOMPOSER_LLM_PROVIDER="none")
    try:
        assert llm.get_llm_engine() is None
        assert llm.available() is False
    finally:
        restore()


def test_model_override():
    restore = _clean_env(OPENAI_API_KEY="x", RECOMPOSER_LLM_MODEL="gpt-4o")
    try:
        assert llm.get_llm_engine().name == "openai:gpt-4o"
    finally:
        restore()
