"""exp01 — Ingest paths for 'movies with embedded subtitles'.

A) soft subtitles (subtitle stream inside MKV/MP4): extract losslessly with ffmpeg.
B) hard subtitles (burned into pixels): OCR bottom band at N fps with tesseract, then
   de-duplicate consecutive frames into timed cues. Evaluated against the true SRT:
   cue recall, character error rate (CER), start/end timing error.
C) SDH statistics on the extracted cues.
"""
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from recaplib import subs
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

W = "/home/user/work/exp01"; os.makedirs(W, exist_ok=True)
SRC = "/home/user/data_untrusted/xiaotangii_tears-of-steel-dialogue-dataset/data/tears_raw.mp4"
SRT = "/home/user/data_untrusted/xiaotangii_tears-of-steel-dialogue-dataset/data/tears_of_steel.srt"
PROXY = "/home/user/work/tos/proxy.mp4"
res = {}

def sh(cmd): subprocess.run(cmd, check=True, capture_output=True)

# A) soft subs
mkv = f"{W}/tos_softsub.mkv"
sh(["ffmpeg", "-y", "-v", "error", "-i", PROXY, "-i", SRT, "-map", "0", "-map", "1", "-c", "copy", "-c:s", "srt", "-metadata:s:s:0", "language=eng", mkv])
streams = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", mkv], capture_output=True, text=True).stdout)["streams"]
sub_streams = [s for s in streams if s["codec_type"] == "subtitle"]
sh(["ffmpeg", "-y", "-v", "error", "-i", mkv, "-map", "0:s:0", f"{W}/extracted.srt"])
a, b = subs.load(SRT), subs.load(f"{W}/extracted.srt")
res["soft"] = {"subtitle_streams": [(s.get("codec_name"), s.get("tags", {}).get("language")) for s in sub_streams],
               "cues_true": len(a), "cues_extracted": len(b),
               "identical_text": sum(x.text == y.text for x, y in zip(a, b)), "max_time_err_s": max(abs(x.start - y.start) for x, y in zip(a, b))}
print("soft", res["soft"])

# B) hard subs: burn, then OCR
burn = f"{W}/tos_hardsub_720.mp4"
if not os.path.exists(burn):
    t = time.time()
    sh(["ffmpeg", "-y", "-v", "error", "-i", SRC, "-vf", f"scale=1280:-2,subtitles={SRT}:force_style='FontSize=20,Outline=1'", "-c:v", "libx264",
        "-preset", "veryfast", "-crf", "22", "-an", burn])
    res["burn_seconds"] = round(time.time() - t, 1)
FPS = 2
fr_dir = f"{W}/ocr_frames"; os.makedirs(fr_dir, exist_ok=True)
if not os.listdir(fr_dir):
    sh(["ffmpeg", "-y", "-v", "error", "-i", burn, "-vf", f"fps={FPS},crop=iw:ih*0.30:0:ih*0.70,format=gray", f"{fr_dir}/%05d.png"])
import cv2, numpy as np
frames = sorted(os.listdir(fr_dir))
t0 = time.time(); texts = []
for i, f in enumerate(frames):
    img = cv2.imread(os.path.join(fr_dir, f), cv2.IMREAD_GRAYSCALE)
    # white text with dark outline: keep bright pixels; skip OCR if almost no bright pixels (no subtitle)
    _, th = cv2.threshold(img, 200, 255, cv2.THRESH_BINARY)
    if th.mean() < 0.4:
        texts.append(""); continue
    inv = 255 - th
    out = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "6", "-l", "eng"], input=cv2.imencode(".png", inv)[1].tobytes(),
                         capture_output=True).stdout.decode("utf-8", "ignore")
    texts.append(" ".join(out.split()))
res["ocr_seconds"] = round(time.time() - t0, 1); res["ocr_frames"] = len(frames)
# frames -> cues: merge runs of similar text
cues = []
for i, tx in enumerate(texts):
    t = (i + 0.5) / FPS
    if len(tx) < 2:
        continue
    if cues and fuzz.ratio(cues[-1]["text"], tx) > 75 and t - cues[-1]["end"] <= 1.0 / FPS + 1e-6:
        cues[-1]["end"] = t; cues[-1]["all"].append(tx)
    else:
        cues.append({"start": t, "end": t, "text": tx, "all": [tx]})
for c in cues:  # majority/longest reading
    c["text"] = max(set(c["all"]), key=lambda s: (c["all"].count(s), len(s)))
json.dump([{k: c[k] for k in ("start", "end", "text")} for c in cues], open(f"{W}/ocr_cues.json", "w"), indent=0)
# evaluate: match each true cue (dialogue text, joined lines) to best OCR cue overlapping in time
truth = [c for c in a if c.text]
matched, cers, dstart, dend = 0, [], [], []
for c in truth:
    cand = [o for o in cues if o["end"] >= c.start - 1 and o["start"] <= c.end + 1]
    if not cand: continue
    o = max(cand, key=lambda o: fuzz.ratio(o["text"].lower(), c.text.lower()))
    cer = Levenshtein.normalized_distance(o["text"].lower(), c.text.lower())
    if cer < 0.5:
        matched += 1; cers.append(cer); dstart.append(abs(o["start"] - c.start)); dend.append(abs(o["end"] - c.end))
res["hard"] = {"true_cues": len(truth), "ocr_cues": len(cues), "recall": round(matched / len(truth), 3),
               "mean_CER": round(float(np.mean(cers)), 3), "median_CER": round(float(np.median(cers)), 3),
               "mean_start_err_s": round(float(np.mean(dstart)), 2), "mean_end_err_s": round(float(np.mean(dend)), 2),
               "fps": FPS}
print("hard", res["hard"])
# C) SDH profile of ToS
res["sdh_profile_tos"] = subs.sdh_profile(a)
json.dump(res, open(os.path.join(os.path.dirname(__file__), "results.json"), "w"), indent=1)
print(json.dumps(res, indent=1))
