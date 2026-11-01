"""exp01 OCR v2 — subtitle-specific text mask (white glyphs with dark outline), crop, 2x upscale,
token filtering, temporal voting. Re-uses frames extracted by run_exp01.py."""
import json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
import cv2, numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from recaplib import subs
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein
W = "/home/user/work/exp01"; FPS = 2
SRT = "/home/user/data_untrusted/xiaotangii_tears-of-steel-dialogue-dataset/data/tears_of_steel.srt"
WORD = re.compile(r"^[A-Za-z'’\-.,!?;:…]+$")


def text_mask(g):
    bright = g > 200
    dark = cv2.dilate((g < 70).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    m = (bright & dark).astype(np.uint8)
    # glyph pixels must be dense in rows (text lines), and horizontally centred
    rows = m.sum(1); cols = m.sum(0)
    if m.sum() < 150: return None
    ys = np.where(rows > 3)[0]; xs = np.where(cols > 0)[0]
    if len(ys) == 0: return None
    cx = (xs.min() + xs.max()) / 2 / g.shape[1]
    if not 0.3 < cx < 0.7: return None
    y0, y1 = max(0, ys.min() - 4), min(g.shape[0], ys.max() + 5); x0, x1 = max(0, xs.min() - 6), min(g.shape[1], xs.max() + 7)
    crop = g[y0:y1, x0:x1]
    _, th = cv2.threshold(crop, 190, 255, cv2.THRESH_BINARY)
    th = cv2.resize(255 - th, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    return cv2.copyMakeBorder(th, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)


def ocr(path):
    g = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    im = text_mask(g)
    if im is None: return ""
    if im.shape[0] > 260 or im.shape[1] > 2600: return ""   # not a subtitle-shaped region
    try:
        out = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "6", "-l", "eng"], input=cv2.imencode(".png", im)[1].tobytes(),
                             capture_output=True, timeout=8).stdout.decode("utf-8", "ignore")
    except subprocess.TimeoutExpired:
        return ""
    toks = [t for t in out.split() if WORD.match(t) and any(c.isalpha() for c in t)]
    good = sum(1 for t in toks if len(t) > 1 or t in ("I", "a", "A"))
    return " ".join(toks) if toks and good / len(toks) > 0.6 else ""


frames = sorted(os.listdir(f"{W}/ocr_frames"))
import time as _t
_t0 = _t.time()
with ThreadPoolExecutor(3) as ex:
    texts = []
    for i, tx in enumerate(ex.map(ocr, [f"{W}/ocr_frames/{f}" for f in frames])):
        texts.append(tx)
        if i % 200 == 0: print("frame", i, round(_t.time() - _t0), "s", flush=True)
cues = []
for i, tx in enumerate(texts):
    t = (i + 0.5) / FPS
    if len(tx) < 2: continue
    if cues and fuzz.ratio(cues[-1]["all"][-1], tx) > 60 and t - cues[-1]["end"] <= 1.01 / FPS:
        cues[-1]["end"] = t; cues[-1]["all"].append(tx)
    else:
        cues.append({"start": t, "end": t, "all": [tx]})
cues = [c for c in cues if len(c["all"]) >= 2 or len(c["all"][0]) > 12]   # temporal stability
for c in cues:
    c["text"] = max(c["all"], key=lambda s: sum(fuzz.ratio(s, o) for o in c["all"]))  # medoid reading
    c["start"] -= 0.5 / FPS; c["end"] += 0.5 / FPS
truth = [c for c in subs.load(SRT) if c.text]
matched, cers, ds, de = 0, [], [], []
for c in truth:
    cand = [o for o in cues if o["end"] >= c.start - 1 and o["start"] <= c.end + 1]
    if not cand: continue
    o = max(cand, key=lambda o: fuzz.ratio(o["text"].lower(), c.text.lower()))
    cer = Levenshtein.normalized_distance(o["text"].lower(), c.text.lower())
    if cer < 0.5: matched += 1; cers.append(cer); ds.append(abs(o["start"] - c.start)); de.append(abs(o["end"] - c.end))
res = {"true_cues": len(truth), "ocr_cues": len(cues), "recall": round(matched / len(truth), 3), "mean_CER": round(float(np.mean(cers)), 3),
       "median_CER": round(float(np.median(cers)), 3), "mean_start_err_s": round(float(np.mean(ds)), 2), "mean_end_err_s": round(float(np.mean(de)), 2)}
print(res)
r = json.load(open("results.json")); r["hard_v2"] = res; json.dump(r, open("results.json", "w"), indent=1)
json.dump([{k: c[k] for k in ("start", "end", "text")} for c in cues], open(f"{W}/ocr_cues_v2.json", "w"), indent=0)
