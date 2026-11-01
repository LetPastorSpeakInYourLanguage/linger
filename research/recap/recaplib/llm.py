"""LLM operator for the understanding / scripting passes.

Backends
  anthropic : real API (ANTHROPIC_API_KEY + RECAP_LLM=anthropic). Model via RECAP_LLM_MODEL.
  replay    : file protocol. Each call writes   <run_dir>/<task>.prompt.md
              and reads                          <run_dir>/<task>.response.json
              If the response is missing, PendingLLM is raised listing the prompt path.
              In this research sandbox (no API key) the responses were authored by Claude
              in-session from exactly these prompt files, so every LLM output in the
              experiments is reproducible/auditable and can be re-run against the API.
"""
from __future__ import annotations
import hashlib, json, os, re


class PendingLLM(Exception):
    pass


def extract_json(text: str):
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*([\[{].*[\]}])\s*```", text, re.S)
    if m:
        text = m.group(1)
    i = min([p for p in (text.find("{"), text.find("[")) if p >= 0] or [0])
    j = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[i:j + 1])


class LLM:
    def __init__(self, run_dir: str, backend: str | None = None, model: str | None = None):
        self.run_dir = run_dir
        os.makedirs(run_dir, exist_ok=True)
        self.backend = backend or os.environ.get("RECAP_LLM", "replay")
        self.model = model or os.environ.get("RECAP_LLM_MODEL", "claude-opus-5-5")
        self.calls = []

    def complete_json(self, task: str, system: str, prompt: str, max_tokens=16000):
        p_path = os.path.join(self.run_dir, f"{task}.prompt.md")
        r_path = os.path.join(self.run_dir, f"{task}.response.json")
        body = f"<!-- SYSTEM -->\n{system}\n\n<!-- USER -->\n{prompt}\n"
        with open(p_path, "w") as f:
            f.write(body)
        h = hashlib.sha256(body.encode()).hexdigest()[:12]
        self.calls.append({"task": task, "prompt_chars": len(body), "prompt_sha": h, "est_tokens": len(body) // 4})
        if self.backend == "anthropic":
            if not os.path.exists(r_path):
                import requests
                r = requests.post(os.environ.get("RECAP_ANTHROPIC_URL", "https://api.anthropic.com/v1/messages"),
                                  headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
                                  json={"model": self.model, "max_tokens": max_tokens, "system": system,
                                        "messages": [{"role": "user", "content": prompt}]}, timeout=600)
                r.raise_for_status()
                txt = "".join(b.get("text", "") for b in r.json()["content"] if b["type"] == "text")
                with open(r_path, "w") as f:
                    json.dump(extract_json(txt), f, indent=1)
        if not os.path.exists(r_path):
            raise PendingLLM(p_path)
        with open(r_path) as f:
            return json.load(f)
