"""Media analysis helpers (all language-agnostic): proxies, shots, VAD, frames, faces & expressions."""
from __future__ import annotations
import json, os, re, subprocess
import numpy as np
from . import MODELS


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def duration(path):
    return float(json.loads(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path]).stdout)["format"]["duration"])


def make_proxy(src, dst, height=360, fps=24):
    """Low-res h264 proxy: fast seeking + fast analysis; renders can still use the source."""
    if not os.path.exists(dst):
        run(["ffmpeg", "-y", "-v", "error", "-i", src, "-vf", f"scale=-2:{height},fps={fps}", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "23", "-g", str(fps), "-c:a", "aac", "-b:a", "128k", dst])
    return dst


def extract_wav(src, dst, sr=16000):
    if not os.path.exists(dst):
        run(["ffmpeg", "-y", "-v", "error", "-i", src, "-ac", "1", "-ar", str(sr), "-vn", dst])
    return dst


def shots(src, thresh=0.3, scale=320):
    """Shot boundaries via ffmpeg's scene-change score (fast, no extra deps)."""
    p = subprocess.run(["ffmpeg", "-v", "info", "-i", src, "-vf", f"scale={scale}:-2,select='gt(scene,{thresh})',showinfo",
                        "-an", "-f", "null", "-"], capture_output=True, text=True)
    return [float(m) for m in re.findall(r"pts_time:([\d.]+)", p.stderr)]


def vad(wav, frame_ms=30, aggressiveness=2):
    """WebRTC VAD -> boolean speech mask at frame_ms resolution (language-agnostic)."""
    import webrtcvad, wave
    v = webrtcvad.Vad(aggressiveness)
    w = wave.open(wav, "rb"); sr = w.getframerate(); data = w.readframes(w.getnframes())
    n = int(sr * frame_ms / 1000) * 2
    return np.array([v.is_speech(data[i:i + n], sr) for i in range(0, len(data) - n, n)], dtype=bool), frame_ms / 1000.0


def smooth_mask(mask, k=5):
    if k <= 1: return mask
    c = np.convolve(mask.astype(float), np.ones(k) / k, mode="same")
    return c > 0.5


def rms_envelope(wav, hop_s=0.1):
    import soundfile as sf
    x, sr = sf.read(wav)
    hop = int(sr * hop_s)
    n = len(x) // hop
    return np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12), hop_s


def snap_to_silence(t, mask, step, search=0.8, direction=0):
    """Move a cut point to the nearest non-speech frame within +-search seconds."""
    i = int(round(t / step)); r = int(search / step)
    best = None
    for d in range(0, r + 1):
        for j in ([i - d, i + d] if direction == 0 else ([i - d] if direction < 0 else [i + d])):
            if 0 <= j < len(mask) and not mask[j]:
                best = j; break
        if best is not None: break
    return (best if best is not None else i) * step


def grab_frames(src, times, out_dir, width=480):
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for t in times:
        p = os.path.join(out_dir, f"f_{t:09.2f}.jpg")
        if not os.path.exists(p):
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", src, "-frames:v", "1", "-vf", f"scale={width}:-2", p])
        paths.append(p)
    return paths


class FaceEmotion:
    """YuNet face detector + MobileFaceNet facial-expression classifier (OpenCV zoo, ONNX)."""
    LABELS = ["angry", "disgust", "fearful", "happy", "neutral", "sad", "surprised"]

    def __init__(self):
        import cv2
        self.cv2 = cv2
        self.det = cv2.FaceDetectorYN.create(os.path.join(MODELS, "yunet.onnx"), "", (320, 320), 0.7)
        self.fer = cv2.dnn.readNet(os.path.join(MODELS, "fer.onnx"))

    def analyze(self, img_path):
        cv2 = self.cv2
        img = cv2.imread(img_path)
        if img is None: return None
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        out = {"sharpness": float(cv2.Laplacian(gray, cv2.CV_64F).var()), "brightness": float(gray.mean()), "faces": []}
        self.det.setInputSize((w, h))
        _, faces = self.det.detect(img)
        for f in (faces if faces is not None else []):
            x, y, fw, fh = [int(v) for v in f[:4]]
            area = fw * fh / (w * h)
            crop = img[max(0, y):y + fh, max(0, x):x + fw]
            if crop.size == 0: continue
            blob = cv2.dnn.blobFromImage(cv2.resize(crop, (112, 112)), 1 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
            self.fer.setInput(blob)
            logits = self.fer.forward()[0]
            p = np.exp(logits - logits.max()); p /= p.sum()
            out["faces"].append({"box": [x, y, fw, fh], "area": round(area, 4), "conf": float(f[-1]),
                                 "expr": self.LABELS[int(p.argmax())], "p": round(float(p.max()), 3),
                                 "probs": {l: round(float(v), 3) for l, v in zip(self.LABELS, p)}})
        return out
