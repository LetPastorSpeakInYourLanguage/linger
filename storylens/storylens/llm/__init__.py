"""LLM layer. Every call is a *step* written to disk (prompt.md, schema.json -> response.json, meta.json),
cached by content hash, and answered by one of three interchangeable backends:

  anthropic  Claude via the official Anthropic SDK (streaming, JSON-schema structured outputs, refusal fallbacks)
  folder     agentic/human: the step waits until an agent (e.g. Claude Code) or person writes response.json
  mock       deterministic offline stand-in so the whole app runs without any key (low quality, for demos/tests)
"""
from .runner import LLMRunner, LLMError, PendingAnswer  # noqa
