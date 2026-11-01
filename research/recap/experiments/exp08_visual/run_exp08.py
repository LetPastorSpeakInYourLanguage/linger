"""exp08 — Grounding narration in footage (language-agnostic signals only).

1. Cut-point hygiene: subtitle-boundary cuts vs VAD speech; snap to silence; % of cuts inside speech.
2. Per-second visual timeline at 1 fps: faces (YuNet), expression (FER MobileFaceNet), sharpness,
   brightness, shot boundaries, audio loudness.
3. LLM 'moments' (from exp05 scene cards) vs detected expression intensity in their time ranges.
4. Still selection per beat: best frame by sharpness + face size + expressiveness, away from shot cuts.
5. Contact sheet of selected stills (visual artifact).
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from recaplib import subs, video
HERE = os.path.dirname(os.path.abspath(__file__)); W = "/home/user/work/exp08"; os.makedirs(W, exist_ok=True)
SRC = "/home/user/data_untrusted/xiaotangii_tears-of-steel-dialogue-dataset/data/tears_raw.mp4"
SRT = "/home/user/data_untrusted/xiaotangii_tears-of-steel-dialogue-dataset/data/tears_of_steel.srt"
U = json.load(open("/home/user/wt/exp05-understanding-passes/research/recap/experiments/exp05_understanding/tos_understanding.json"))
cues = subs.load(SRT); by = {c.idx: c for c in cues}
res = {}
# 1. cut hygiene
wav = video.extract_wav(SRC, "/home/user/work/tos/audio16k.wav")
mask, step = video.vad(wav, 30, 3); mask = video.smooth_mask(mask, 5)
def in_speech(t): i = int(t / step); return bool(mask[i]) if 0 <= i < len(mask) else False
raw_cuts = [c.start for c in cues] + [c.end for c in cues]
snapped = [video.snap_to_silence(c.start, mask, step, 0.6, -1) for c in cues] + [video.snap_to_silence(c.end, mask, step, 0.8, +1) for c in cues]
res["cut_hygiene"] = {"cuts": len(raw_cuts), "inside_speech_raw": round(np.mean([in_speech(t) for t in raw_cuts]), 3),
                      "inside_speech_snapped": round(np.mean([in_speech(t) for t in snapped]), 3),
                      "mean_shift_s": round(float(np.mean([abs(a - b) for a, b in zip(raw_cuts, snapped)])), 3),
                      "speech_fraction_of_film": round(float(mask.mean()), 3)}
print(res["cut_hygiene"])
# 2. timeline at 1 fps from source (better faces than the proxy)
dur = video.duration(SRC); times = list(np.arange(0.5, dur, 1.0))
fr_dir = f"{W}/frames1fps"
if not os.path.exists(fr_dir) or len(os.listdir(fr_dir)) < len(times) - 2:
    os.makedirs(fr_dir, exist_ok=True)
    video.run(["ffmpeg", "-y", "-v", "error", "-i", SRC, "-vf", "fps=1,scale=960:-2", "-q:v", "3", f"{fr_dir}/%05d.jpg"])
frames = sorted(os.listdir(fr_dir))
fe = video.FaceEmotion()
shots = json.load(open("/home/user/work/tos/shots.json"))
rms, hop = video.rms_envelope(wav, 0.5)
TL = []
for i, f in enumerate(frames):
    t = i + 0.5
    a = fe.analyze(os.path.join(fr_dir, f)) or {"faces": [], "sharpness": 0, "brightness": 0}
    faces = [x for x in a["faces"] if x["area"] > 0.004]
    big = max(faces, key=lambda x: x["area"]) if faces else None
    expr = (1 - big["probs"]["neutral"]) if big else 0.0
    loud = float(rms[int(t / hop)]) if int(t / hop) < len(rms) else 0
    TL.append({"t": t, "file": f, "faces": len(faces), "face_area": big["area"] if big else 0, "expr": big["expr"] if big else None,
               "expressive": round(expr, 3), "sharp": a["sharpness"], "bright": a["brightness"], "loud": loud,
               "near_cut": any(abs(t - s) < 0.6 for s in shots)})
json.dump(TL, open(f"{W}/timeline.json", "w"))
res["timeline"] = {"frames": len(TL), "frames_with_faces": sum(1 for x in TL if x["faces"]),
                   "expr_hist": {e: sum(1 for x in TL if x["expr"] == e) for e in fe.LABELS}, "shots": len(shots)}
print(res["timeline"])
# 3. LLM moments vs detected signals
loud_all = np.array([x["loud"] for x in TL]); ex_all = np.array([x["expressive"] for x in TL])
mres = []
for s in U["cards"][0]["scenes"]:
    for m in s.get("moments", []):
        a, z = by[m["lines"][0]].start, by[m["lines"][1]].end
        seg = [x for x in TL if a - 0.5 <= x["t"] <= z + 0.5]
        if not seg: continue
        mres.append({"lines": m["lines"], "llm": f"{m['emotion']}/{m['intensity']}", "t": [round(a, 1), round(z, 1)],
                     "expr_mean": round(float(np.mean([x["expressive"] for x in seg])), 3),
                     "loud_pct": round(float((loud_all < np.mean([x["loud"] for x in seg])).mean()), 2),
                     "top_expr": max(seg, key=lambda x: x["expressive"])["expr"]})
# correlation of LLM intensity with loudness percentile / expressiveness
li = np.array([int(m["llm"].rsplit("/", 1)[1]) for m in mres])
res["moments"] = {"n": len(mres), "corr_intensity_loudness": round(float(np.corrcoef(li, [m["loud_pct"] for m in mres])[0, 1]), 3),
                  "corr_intensity_expressive": round(float(np.corrcoef(li, [m["expr_mean"] for m in mres])[0, 1]), 3),
                  "film_mean_expressive": round(float(ex_all.mean()), 3), "moments_mean_expressive": round(float(np.mean([m["expr_mean"] for m in mres])), 3),
                  "items": mres}
print({k: v for k, v in res["moments"].items() if k != "items"})
# 4. stills per beat
sh_all = np.array([x["sharp"] for x in TL]); sh_n = lambda v: min(1.0, v / (np.percentile(sh_all, 90) + 1e-9))
stills = {}
for b in U["beats"]:
    a, z = b["t_range"]
    cand = [x for x in TL if a - 1 <= x["t"] <= z + 1.5 and x["bright"] > 25] or [min(TL, key=lambda x: abs(x["t"] - a))]
    def score(x): return 0.45 * sh_n(x["sharp"]) + 0.3 * min(1, x["face_area"] / 0.05) + 0.25 * x["expressive"] - (0.3 if x["near_cut"] else 0)
    best = max(cand, key=score)
    stills[b["id"]] = {"t": best["t"], "file": best["file"], "score": round(score(best), 3), "faces": best["faces"], "expr": best["expr"]}
json.dump(stills, open(os.path.join(HERE, "stills.json"), "w"), indent=1)
res["stills"] = {"beats": len(stills), "with_face": sum(1 for s in stills.values() if s["faces"]), "mean_score": round(float(np.mean([s["score"] for s in stills.values()])), 3)}
# 5. contact sheet
import cv2
tiles = []
for b in sorted(U["beats"], key=lambda b: b["t"]):
    s = stills[b["id"]]; im = cv2.imread(os.path.join(fr_dir, s["file"])); im = cv2.resize(im, (480, 200))
    cv2.rectangle(im, (0, 170), (480, 200), (0, 0, 0), -1)
    cv2.putText(im, f"{b['tier']} {b['short'][:44]}", (6, 191), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    tiles.append(im)
while len(tiles) % 3: tiles.append(np.zeros_like(tiles[0]))
sheet = np.vstack([np.hstack(tiles[i:i + 3]) for i in range(0, len(tiles), 3)])
cv2.imwrite(os.path.join(HERE, "stills_contact_sheet.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 80])
json.dump(res, open(os.path.join(HERE, "results.json"), "w"), indent=1)
print(res["stills"])
