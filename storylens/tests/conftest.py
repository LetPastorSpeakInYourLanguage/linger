import pytest
from storylens import config as C
from storylens.workspace import Workspace
from storylens.demo import sample_srt


@pytest.fixture
def ws(tmp_path):
    s = C.load(tmp_path / "ws"); s.answerer = "mock"; s.tts = "none"
    return Workspace(s).init()


@pytest.fixture
def title(ws):
    t = ws.create_title("Lighthouse", "film", cast=["Maya", "Leo", "Victor", "Ines"])
    ws.add_media(t["id"], subs=sample_srt())
    return ws.title(t["id"])
