"""Standalone passive executor for Recomposer (P8.3 foundation).

Runs anywhere with the heavy deps installed (e.g. a Colab T4) and drains the
host instance's queue for the job kinds it handles, over HTTP — no inbound
connection to the executor needed. The host marks those kinds remote with
RECOMPOSER_REMOTE_KINDS so its in-process worker leaves them alone.

Usage:
    RECOMPOSER_WORKER_TOKEN=secret \
    python -m executor.worker --server http://HOST:8000 --kinds separate,dub

It reuses the backend job handlers, so the executor must point at the SAME
database/media (e.g. shared Google Drive) as the host. This is intentionally a
thin reference client; flesh out storage sharing per your deployment.
"""
import argparse
import os
import time

import requests


def run(server: str, kinds: list[str], token: str, worker_id: str, poll: float):
    sess = requests.Session()
    base = server.rstrip("/")
    print(f"[executor] {worker_id} polling {base} for kinds={kinds}")
    # Importing handlers lazily so the script can be copied without the full app
    from backend import jobs  # noqa: F401  (registers HANDLERS via @handler)

    while True:
        try:
            r = sess.post(f"{base}/api/worker/claim", json={
                "worker_id": worker_id, "kinds": kinds, "token": token}, timeout=30)
            r.raise_for_status()
            job = r.json().get("job")
        except Exception as e:
            print(f"[executor] claim error: {e}")
            time.sleep(poll)
            continue
        if not job:
            time.sleep(poll)
            continue

        jid, kind = job["id"], job["kind"]
        print(f"[executor] running job {jid} ({kind})")
        ctx = _RemoteCtx(sess, base, jid, token, worker_id)
        try:
            handler = jobs.HANDLERS[kind]
            handler(ctx, job.get("payload") or {})
            sess.post(f"{base}/api/worker/{jid}/complete",
                      json={"token": token, "detail": "done"}, timeout=30)
            print(f"[executor] job {jid} complete")
        except Exception as e:
            sess.post(f"{base}/api/worker/{jid}/fail",
                      json={"token": token, "error": str(e)}, timeout=30)
            print(f"[executor] job {jid} failed: {e}")


class _RemoteCtx:
    """JobContext-shaped object that reports progress via heartbeats over HTTP."""

    def __init__(self, sess, base, job_id, token, worker_id):
        self._sess, self._base = sess, base
        self.job_id, self._token, self._worker = job_id, token, worker_id
        self.media_id = None

    def report(self, detail="", progress=None):
        try:
            self._sess.post(f"{self._base}/api/worker/{self.job_id}/heartbeat",
                            json={"token": self._token, "worker_id": self._worker,
                                  "detail": detail}, timeout=15)
        except Exception:
            pass

    def heartbeat(self):
        self.report()

    def check_cancel(self):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=os.environ.get("RECOMPOSER_SERVER", "http://localhost:8000"))
    ap.add_argument("--kinds", default=os.environ.get("RECOMPOSER_WORKER_KINDS", "separate,dub"))
    ap.add_argument("--worker-id", default=os.environ.get("RECOMPOSER_WORKER_ID", "executor-1"))
    ap.add_argument("--poll", type=float, default=3.0)
    args = ap.parse_args()
    token = os.environ.get("RECOMPOSER_WORKER_TOKEN", "")
    if not token:
        raise SystemExit("set RECOMPOSER_WORKER_TOKEN (must match the host)")
    run(args.server, [k.strip() for k in args.kinds.split(",") if k.strip()],
        token, args.worker_id, args.poll)


if __name__ == "__main__":
    main()
