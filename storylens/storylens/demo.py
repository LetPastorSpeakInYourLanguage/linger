"""`storylens demo`: an original sample story (bundled, CC0) + a generated test video, run end-to-end."""
from __future__ import annotations
import shutil, subprocess
from importlib import resources
from pathlib import Path
from . import media as M
from .jobs import Job, run_job


def sample_srt() -> Path:
    return Path(str(resources.files("storylens") / "samples" / "lighthouse.srt"))


def make_demo_video(out: Path, seconds: float):
    if not M.have_ffmpeg() or out.exists(): return out.exists()
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=s=854x480:r=25:d={seconds:.1f}", "-f", "lavfi",
                    "-i", f"sine=frequency=220:duration={seconds:.1f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
                    "-c:a", "aac", "-shortest", str(out)], check=True)
    return True


def create_demo_title(ws):
    t = next((t for t in ws.titles() if t["id"].startswith("the-lighthouse-keeper")), None)
    if t: return t
    t = ws.create_title("The Lighthouse Keeper (demo)", "film", cast=["Maya", "Leo", "Victor", "Ines"])
    srt = Path(ws.root) / "demo" / "lighthouse.srt"; srt.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(sample_srt(), srt)
    from . import subs
    end = subs.load(srt)[-1].end + 6
    vid = Path(ws.root) / "demo" / "lighthouse.mp4"
    ws.add_media(t["id"], video=vid if make_demo_video(vid, end) else None, subs=srt)
    return ws.title(t["id"])


def run_demo(ws, real=False):
    from . import understand, recap
    if not real: ws.s.llm_backend = "mock"
    t = create_demo_title(ws)
    print(f"demo title '{t['id']}' (LLM backend: {ws.s.llm_backend}; video: {'yes' if t['media'][0]['video'] else 'no — install ffmpeg to render'})")
    j = Job.create(ws, "understand", t["id"], autonomy="auto"); run_job(j, lambda job: understand.run(ws, job, t["id"]))
    print("understanding:", j.state["status"], j.state.get("message", ""))
    for lens, style in (({"kind": "main"}, "recap_channel"), ({"kind": "character", "name": "Victor"}, "character"),
                        ({"kind": "trait", "query": "being a good friend", "actor": "Leo"}, "compilation")):
        j = Job.create(ws, "recap", t["id"], {"lens": lens, "style": style, "duration": 60}, autonomy="auto")
        run_job(j, lambda job: recap.run(ws, job, t["id"], {"lens": lens, "style": style, "duration": 60, "render": True}))
        print(f"recap {lens['kind']:9s}: {j.state['status']} — artifacts in {j.dir / 'artifacts'}")
    print("\nOpen the app:  storylens serve   →  http://127.0.0.1:8765")
