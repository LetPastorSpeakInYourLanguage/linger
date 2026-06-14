"""P8.3 foundation: remote executor HTTP claim/heartbeat/complete protocol."""
import os

from backend import jobs

from .conftest import wait_for


def _job(client, jid):
    return next(j for j in client.get("/api/jobs").json() if j["id"] == jid)


def test_remote_kind_is_left_for_worker_and_claimed(client):
    os.environ["RECOMPOSER_WORKER_TOKEN"] = "secret"
    os.environ["RECOMPOSER_REMOTE_KINDS"] = "test_remote"
    try:
        jid = jobs.enqueue("test_remote", None, {"hello": "world"})
        # the in-process worker must NOT run a remote-reserved kind
        import time
        time.sleep(1.0)
        assert _job(client, jid)["status"] == "queued"

        # wrong token rejected
        bad = client.post("/api/worker/claim",
                          json={"worker_id": "colab", "kinds": ["test_remote"], "token": "x"})
        assert bad.status_code == 403

        # claim over HTTP
        r = client.post("/api/worker/claim",
                        json={"worker_id": "colab", "kinds": ["test_remote"], "token": "secret"})
        assert r.status_code == 200
        job = r.json()["job"]
        assert job and job["id"] == jid and job["payload"]["hello"] == "world"
        assert _job(client, jid)["status"] == "running"

        # heartbeat + complete
        assert client.post(f"/api/worker/{jid}/heartbeat",
                           json={"worker_id": "colab", "token": "secret"}).status_code == 200
        assert client.post(f"/api/worker/{jid}/complete",
                           json={"token": "secret", "detail": "done remotely"}).status_code == 200
        assert _job(client, jid)["status"] == "done"
    finally:
        os.environ.pop("RECOMPOSER_WORKER_TOKEN", None)
        os.environ.pop("RECOMPOSER_REMOTE_KINDS", None)
        jobs.wake()


def test_worker_endpoints_off_without_token(client):
    os.environ.pop("RECOMPOSER_WORKER_TOKEN", None)
    r = client.post("/api/worker/claim",
                    json={"worker_id": "w", "kinds": ["x"], "token": ""})
    assert r.status_code == 403
