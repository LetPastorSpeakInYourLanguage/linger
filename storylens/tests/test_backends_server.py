import json
from types import SimpleNamespace as NS
from storylens.llm.backends import AnthropicBackend
from storylens.llm.runner import Call
from storylens import schemas as SC


class FakeStream:
    def __init__(self, captured, **kw): captured.update(kw); self.kw = kw
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def get_final_message(self):
        return NS(stop_reason="end_turn", stop_details=None, model=self.kw["model"],
                  content=[NS(type="thinking", thinking=""), NS(type="text", text=json.dumps({"description": "d", "act_types": ["helps"], "keywords": ["k"], "actor_required": False}))],
                  usage=NS(input_tokens=10, output_tokens=5, cache_read_input_tokens=0))


def test_anthropic_backend_request_shape(ws, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    b = AnthropicBackend(ws.s); cap = {}
    monkeypatch.setattr(b.client.beta.messages, "stream", lambda **kw: FakeStream(cap, **kw))
    data, usage = b.complete(Call("t", "SYS", "USER", SC.TRAIT_MAP, "claude-opus-5-5", "medium", 1000))
    assert data["act_types"] == ["helps"] and usage["output_tokens"] == 5
    assert cap["model"] == "claude-opus-5-5" and cap["fallbacks"] == "default" and cap["betas"] == ["server-side-fallback-2026-07-01"]
    assert cap["output_config"]["format"]["type"] == "json_schema" and cap["output_config"]["effort"] == "medium"
    assert cap["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_server_api(ws, title):
    from fastapi.testclient import TestClient
    from storylens.server import create_app
    c = TestClient(create_app(ws))
    assert c.get("/").status_code == 200 and "storylens" in c.get("/").text
    st = c.get("/api/status").json(); assert st["backend"] == "mock"
    assert c.get("/api/titles").json()[0]["id"] == title["id"]
    r = c.post(f"/api/titles/{title['id']}/media", json={"subs": "/nope.srt"}); assert r.status_code == 400
    d = c.get(f"/api/titles/{title['id']}").json(); assert d["understanding"] is None
    assert c.get(f"/api/titles/{title['id']}/beats").status_code == 404
