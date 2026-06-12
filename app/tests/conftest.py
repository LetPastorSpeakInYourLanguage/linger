"""Test fixtures: temp DB + media store, TestClient with the real worker
thread, fake transcription engine (never downloads whisper models), and a
synthetic test video generated with ffmpeg lavfi (no binary fixtures)."""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

# must be set before backend.db is imported — it reads the env at import time
_tmp = tempfile.mkdtemp(prefix="recomposer_test_")
os.environ["RECOMPOSER_DB"] = str(Path(_tmp) / "test.db")
os.environ["RECOMPOSER_MEDIA"] = str(Path(_tmp) / "media")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend import jobs  # noqa: E402
from backend.db import get_db  # noqa: E402
from backend.main import app  # noqa: E402


def _fake_transcribe(ctx, payload):
    """Stands in for whisper: instant, no model downloads. Creates one track
    named like the real engine would so payload plumbing is observable."""
    model = payload.get("model") or "small"
    ctx.report(f"fake transcription model={model}", progress=50)
    db = get_db()
    tid = db.execute("INSERT INTO tracks (media_id, name) VALUES (?,?)",
                     (ctx.media_id, f"WhisperX ({model})")).lastrowid
    db.execute("INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text) "
               "VALUES (?,?,?,?,?,?)",
               (ctx.media_id, tid, 0, 0.2, 1.4, "fake transcript line"))
    db.commit()
    jobs._set_media(ctx.media_id, "ready")


def _sleepy(ctx, payload):
    """Test-only kind: runs until cancelled (or seconds elapse)."""
    end = time.time() + payload.get("seconds", 10)
    while time.time() < end:
        ctx.check_cancel()
        time.sleep(0.05)


# registered before the worker thread starts (TestClient startup)
jobs.HANDLERS["transcribe"] = _fake_transcribe
jobs.HANDLERS["test_sleep"] = _sleepy


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def user(client):
    return client.post("/api/users", json={"name": "tester"}).json()


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory):
    p = tmp_path_factory.mktemp("src") / "sample.mp4"
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30",
         "-f", "lavfi", "-i", "sine=frequency=440",
         "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         str(p)],
        capture_output=True, check=True)
    return p


def wait_for(fn, timeout=30, every=0.15):
    """Poll fn until truthy; return its value."""
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(every)
    raise AssertionError(f"timed out after {timeout}s waiting for {fn}")
