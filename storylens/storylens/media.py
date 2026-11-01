"""Media helpers (all optional: everything degrades gracefully without ffmpeg / onnxruntime).

ffmpeg/ffprobe must be on PATH for video features (https://ffmpeg.org/download.html).
"""
from __future__ import annotations
import json, re, shutil, subprocess, urllib.request
from pathlib import Path
import numpy as np

SILERO_URL = "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"


def have_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def run(cmd, check=True):
    return subprocess.run(cmd, capture_output=True, text=True, check=check, encoding="utf-8", errors="replace")


def probe(video) -> dict:
    out = json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(video)]).stdout)
    streams = out.get("streams", [])
    return {"duration": float(out.get("format", {}).get("duration") or 0),
            "video": [s for s in streams if s.get("codec_type") == "video"][:1],
            "audio_langs": [s.get("tags", {}).get("language") for s in streams if s.get("codec_type") == "audio"],
            "subtitle_streams": [{"index": s["index"], "codec": s.get("codec_name"), "language": s.get("tags", {}).get("language"),
                                  "title": s.get("tags", {}).get("title")} for s in streams if s.get("codec_type") == "subtitle"]}


TEXT_SUB_CODECS = {"subrip", "srt", "ass", "ssa", "webvtt", "mov_text", "text"}


def extract_soft_subs(video, out_srt, prefer=("eng", "en", None)) -> bool:
    """Extract an embedded *text* subtitle stream (English preferred) losslessly. Image subs (PGS/VobSub) need OCR."""
    info = probe(video)
    cands = [s for s in info["subtitle_streams"] if s["codec"] in TEXT_SUB_CODECS]
    if not cands: return False
    cands.sort(key=lambda s: prefer.index(s["language"]) if s["language"] in prefer else len(prefer))
    r = run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-map", f"0:{cands[0]['index']}", str(out_srt)], check=False)
    return r.returncode == 0 and Path(out_srt).exists()


def shots(video, thresh=0.3, scale=320):
    p = subprocess.run(["ffmpeg", "-v", "info", "-i", str(video), "-vf", f"scale={scale}:-2,select='gt(scene,{thresh})',showinfo",
                        "-an", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return [round(float(m), 3) for m in re.findall(r"pts_time:([\d.]+)", p.stderr)]


def frame(video, t, out, width=640):
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "4", str(out)], check=False)
    return Path(out).exists()


def extract_wav(video, out, sr=16000):
    if not Path(out).exists():
        run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-ac", "1", "-ar", str(sr), "-vn", str(out)])
    return out


def silero_available() -> bool:
    try:
        import onnxruntime, soundfile  # noqa
        return True
    except Exception:
        return False


def silero_model(models_dir) -> Path:
    p = Path(models_dir) / "silero_vad.onnx"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(SILERO_URL, p)
    return p


def speech_probability(wav, models_dir):
    """Silero VAD v5 -> speech probability per 32 ms (language-agnostic)."""
    import onnxruntime as ort, soundfile as sf
    x, sr = sf.read(str(wav), dtype="float32")
    sess = ort.InferenceSession(str(silero_model(models_dir)))
    state = np.zeros((2, 1, 128), np.float32); ctx = np.zeros(64, np.float32); out = []
    for i in range(0, len(x) - 512 + 1, 512):
        o, state = sess.run(None, {"input": np.concatenate([ctx, x[i:i + 512]])[None, :], "state": state, "sr": np.array(16000, np.int64)})
        out.append(float(o[0, 0])); ctx = x[i + 512 - 64:i + 512]
    return np.array(out, np.float32), 512 / sr


def resync(cues, prob, step, scales=(1.0, 25 / 23.976, 23.976 / 25), max_offset=12.0):
    """Find (scale, offset) so subtitle activity best matches speech activity; returns (scale, offset, corr)."""
    grid_step = 0.064
    n = int(len(prob) * step / grid_step)
    v = np.interp(np.arange(n) * grid_step, np.arange(len(prob)) * step, prob)
    vz = (v - v.mean()) / (v.std() + 1e-9)
    def act(scale, off):
        a = np.zeros(n)
        for c in cues:
            i, j = int((c.start * scale + off) / grid_step), int((c.end * scale + off) / grid_step)
            if j > 0 and i < n: a[max(0, i):min(n, j)] = 1
        return a
    best = (-9.0, 1.0, 0.0)
    for s in scales:
        for o in np.arange(-max_offset, max_offset, 0.128):
            a = act(s, o)
            if a.std() == 0: continue
            r = float((vz * (a - a.mean())).mean() / a.std())
            if r > best[0]: best = (r, s, float(o))
    r0, s0, o0 = best
    for o in np.arange(o0 - 0.15, o0 + 0.15, 0.016):
        a = act(s0, o)
        r = float((vz * (a - a.mean())).mean() / a.std())
        if r > best[0]: best = (r, s0, float(o))
    return best[1], best[2], best[0]


def has_video_stream(path) -> bool:
    try: return bool(probe(path)["video"])
    except Exception: return False


def audio_visual_proxy(audio, out, title=""):
    """(title is drawn by the lower thirds of each clip; the proxy itself stays font-free for portability)"""
    """Audio-only sources (podcasts, sermon audio): a cover + live waveform video so they can be cut like video."""
    out = Path(out)
    if out.exists(): return out
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-v", "error", "-i", str(audio), "-filter_complex",
         "[0:a]showwaves=s=854x160:mode=cline:colors=0x7aa2ff:rate=15[w];color=c=0x111827:s=854x480:r=15[bg];"
         "[bg][w]overlay=0:300:shortest=1,format=yuv420p[v]", "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "ultrafast",
         "-crf", "32", "-c:a", "aac", "-b:a", "128k", str(out)])
    return out
