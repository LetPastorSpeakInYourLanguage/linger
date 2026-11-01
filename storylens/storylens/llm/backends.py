from __future__ import annotations
import base64, json, os, re, time
from pathlib import Path


class LLMError(RuntimeError):
    pass


class PendingAnswer(RuntimeError):
    pass


def extract_json(text: str):
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*([\[{].*[\]}])\s*```", text, re.S)
    if m: text = m.group(1)
    starts = [p for p in (text.find("{"), text.find("[")) if p >= 0]
    if not starts: raise LLMError("no JSON in response")
    i, j = min(starts), max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[i:j + 1])


class AnthropicBackend:
    name = "anthropic"

    def __init__(self, settings):
        import anthropic
        self.anthropic = anthropic
        self.client = anthropic.Anthropic(max_retries=4, timeout=900)
        self.s = settings
        self.fallbacks_ok = settings.fallbacks
        self.structured_ok = settings.structured_outputs

    def complete(self, call):
        content = []
        for img in call.images or []:
            data = base64.standard_b64encode(Path(img).read_bytes()).decode()
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}})
        content.append({"type": "text", "text": call.prompt})
        output_config = {"effort": call.effort}
        structured = self.structured_ok and call.schema is not None
        if structured: output_config["format"] = {"type": "json_schema", "schema": call.schema}
        kwargs = dict(model=call.model, max_tokens=call.max_tokens,
                      system=[{"type": "text", "text": call.system, "cache_control": {"type": "ephemeral"}}],
                      messages=[{"role": "user", "content": content}], output_config=output_config)
        A = self.anthropic
        for attempt in range(3):
            try:
                if self.fallbacks_ok:
                    with self.client.beta.messages.stream(**kwargs, betas=["server-side-fallback-2026-07-01"], fallbacks="default") as st:
                        msg = st.get_final_message()
                else:
                    with self.client.messages.stream(**kwargs) as st:
                        msg = st.get_final_message()
                break
            except A.BadRequestError as e:
                text = str(e).lower()
                if self.fallbacks_ok and ("fallback" in text or "beta" in text):
                    self.fallbacks_ok = False; continue          # account/platform without server-side fallback
                if structured and ("output_config" in text or "schema" in text or "format" in text):
                    structured = False; output_config.pop("format", None)
                    kwargs["messages"][0]["content"][-1]["text"] += "\n\nReturn ONLY the JSON object, no prose."
                    continue                                     # schema feature not accepted: prompt-JSON instead
                raise LLMError(f"Bad request: {e}") from e
            except A.AuthenticationError as e:
                raise LLMError("Anthropic authentication failed — set ANTHROPIC_API_KEY (or run `ant auth login`).") from e
            except (A.RateLimitError, A.APIConnectionError, A.InternalServerError) as e:
                if attempt == 2: raise LLMError(f"API unavailable after retries: {e}") from e
                time.sleep(10 * (attempt + 1))
        if msg.stop_reason == "refusal":
            raise LLMError(f"model declined this step ({getattr(msg.stop_details, 'category', None)})")
        if msg.stop_reason == "max_tokens":
            raise LLMError("response hit max_tokens — lower chunk_lines in settings")
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        data = json.loads(text) if structured else extract_json(text)
        u = msg.usage
        usage = {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                 "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0, "model": msg.model}
        return data, usage


class FolderBackend:
    """Agentic / human-in-the-loop backend: waits for response.json written by an agent or a person."""
    name = "folder"

    def __init__(self, settings, cancelled=lambda: False):
        self.s = settings; self.cancelled = cancelled

    def complete(self, call):
        d = Path(call.step_dir)
        (d / "WAITING").write_text("waiting for response.json (see AGENTS.md)", encoding="utf-8")
        t0 = time.time()
        while not (d / "response.json").exists():
            if self.cancelled(): raise LLMError("job cancelled")
            if self.s.folder_timeout_seconds and time.time() - t0 > self.s.folder_timeout_seconds:
                raise PendingAnswer(str(d))
            time.sleep(self.s.folder_poll_seconds)
        time.sleep(0.2)
        try:
            data = json.loads((d / "response.json").read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = extract_json((d / "response.json").read_text(encoding="utf-8"))
        (d / "WAITING").unlink(missing_ok=True)
        return data, {"answered_by": "folder"}


def make_backend(settings, cancelled=lambda: False):
    b = settings.llm_backend
    if b == "auto":
        b = "anthropic" if (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_PROFILE")) else "folder"
    if b == "anthropic": return AnthropicBackend(settings)
    if b == "folder": return FolderBackend(settings, cancelled)
    if b == "mock":
        from .mock import MockBackend
        return MockBackend(settings)
    raise LLMError(f"unknown llm_backend {b}")
