"""Settings store, stats, profile, and that settings actually drive behavior."""
from backend import jobs, settings
from backend.db import get_db


def test_settings_get_put_and_effective(client):
    r = client.get("/api/settings").json()
    assert "values" in r and "schema" in r
    assert r["values"]["whisper_model"]  # has a default
    assert any(s["key"] == "llm_provider" and s["group"] == "ai" for s in r["schema"])

    upd = client.put("/api/settings", json={"values": {
        "whisper_model": "medium", "default_export_quality": "1080p",
        "ai_chunk_lines": 250, "default_keep_source_vocals": True}}).json()
    assert upd["values"]["whisper_model"] == "medium"
    assert upd["values"]["ai_chunk_lines"] == 250
    assert upd["values"]["default_keep_source_vocals"] is True

    # persisted + typed
    assert settings.get("whisper_model") == "medium"
    assert settings.get("ai_chunk_lines") == 250
    assert settings.get("default_keep_source_vocals") is True


def test_settings_drive_transcription_defaults(client):
    client.put("/api/settings", json={"values": {"whisper_model": "large-v3"}})
    # the transcribe options + the worker both read the setting
    assert client.get("/api/transcribe/options").json()["default_model"] == "large-v3"
    assert jobs._whisper_settings()[0] == "large-v3"
    client.put("/api/settings", json={"values": {"whisper_model": "small"}})  # reset


def test_stats_counts(client, user):
    db = get_db()
    db.execute("INSERT INTO recompositions (title, created_by) VALUES ('S', ?)", (user["id"],))
    db.commit()
    s = client.get("/api/stats").json()
    assert s["recompositions"] >= 1 and s["users"] >= 1
    assert {"media", "cuts", "tags", "embedded", "exports"} <= set(s)


def test_profile_update(client, user):
    r = client.patch(f"/api/users/{user['id']}", json={"color": "#123456"})
    assert r.status_code == 200 and r.json()["color"] == "#123456"


def test_ai_test_endpoint_without_llm(client):
    from backend import llm
    llm.set_llm_engine(None)
    try:
        r = client.post("/api/ai/test").json()
        assert r["ok"] is False and "error" in r
    finally:
        llm.reset()
