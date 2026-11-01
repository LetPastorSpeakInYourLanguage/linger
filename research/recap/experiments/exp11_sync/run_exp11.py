"""exp11 — Language-agnostic alignment of English subtitles to any-language audio.

The recap pipeline reads meaning ONLY from the English subtitle text; it touches the audio only through
language-independent signals (voice activity, loudness). Two practical problems remain:
 (1) subtitles from another release are offset and/or stretched (25 fps PAL vs 23.976 fps);
 (2) subtitle in/out points are padded, so cuts land mid-word.
We (a) compare WebRTC vs Silero VAD as the speech signal, (b) recover synthetic offsets/stretches by
maximizing correlation between the subtitle activity curve and the VAD speech curve, (c) re-measure
cut hygiene with the better VAD.
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from recaplib import subs, video
HERE = os.path.dirname(os.path.abspath(__file__))
SRT = "/home/user/data_untrusted/xiaotangii_tears-of-steel-dialogue-dataset/data/tears_of_steel.srt"
wav = "/home/user/work/tos/audio16k.wav"
cues = [c for c in subs.load(SRT) if c.text]
STEP = 0.032
res = {}
p_sil, st = video.silero_vad(wav)
m_web, st_w = video.vad(wav, 30, 3)
T = len(p_sil) * st
grid = np.arange(0, T, STEP)
sil = np.interp(grid, np.arange(len(p_sil)) * st, p_sil)
web = np.interp(grid, np.arange(len(m_web)) * st_w, m_web.astype(float))


def activity(cs, scale=1.0, offset=0.0):
    a = np.zeros(len(grid))
    for c in cs:
        i, j = int((c.start * scale + offset) / STEP), int((c.end * scale + offset) / STEP)
        a[max(0, i):max(0, min(len(a), j))] = 1
    return a


truth = activity(cues)
res["vad_quality"] = {}
for name, v in (("webrtc", web), ("silero", sil)):
    b = v > 0.5
    res["vad_quality"][name] = {"speech_fraction": round(float(b.mean()), 3),
                                "recall_inside_subtitles": round(float(b[truth == 1].mean()), 3),
                                "false_speech_outside_subtitles": round(float(b[truth == 0].mean()), 3),
                                "corr_with_subtitle_activity": round(float(np.corrcoef(v, truth)[0, 1]), 3)}
print(res["vad_quality"])


def recover(cs, v, scales=(1.0, 25 / 23.976, 23.976 / 25), offs=np.arange(-12, 12, 0.064)):
    vz = (v - v.mean()) / (v.std() + 1e-9); best = (-9, None, None)
    for s in scales:
        for o in offs:
            a = activity(cs, s, o)
            if a.std() == 0: continue
            r = float((vz * (a - a.mean())).mean() / a.std())
            if r > best[0]: best = (r, s, o)
    # refine offset
    s0, o0 = best[1], best[2]
    for o in np.arange(o0 - 0.1, o0 + 0.1, 0.008):
        a = activity(cs, s0, o); r = float((vz * (a - a.mean())).mean() / a.std())
        if r > best[0]: best = (r, s0, o)
    return best


tests = [("offset+2.5s", 1.0, 2.5), ("offset-6.0s", 1.0, -6.0), ("PAL->film stretch", 23.976 / 25, 0.0), ("stretch+offset", 25 / 23.976, -3.2), ("none", 1.0, 0.0)]
res["sync_recovery"] = {}
for name, s_true, o_true in tests:
    # corrupt the subtitle timing: t' = t*s + o; recovery must find the inverse
    bad = [subs.Cue(c.idx, c.start * s_true + o_true, c.end * s_true + o_true, c.raw, c.text) for c in cues]
    row = {}
    for vn, v in (("webrtc", web), ("silero", sil)):
        r, s_hat, o_hat = recover(bad, v)
        fixed = [(c.start * s_hat + o_hat) for c in bad]
        err = np.abs(np.array(fixed) - np.array([c.start for c in cues]))
        row[vn] = {"scale": round(s_hat, 5), "offset": round(o_hat, 3), "corr": round(r, 3), "median_cue_err_s": round(float(np.median(err)), 3), "max_cue_err_s": round(float(err.max()), 3)}
    res["sync_recovery"][name] = row
    print(name, row)
# cut hygiene with silero (cf. exp08 with webrtc)
mask = video.smooth_mask(p_sil > 0.5, 3)
def in_speech(t): i = int(t / st); return bool(mask[i]) if 0 <= i < len(mask) else False
raw = [c.start for c in cues] + [c.end for c in cues]
snapped = [video.snap_to_silence(c.start, mask, st, 0.6, -1) for c in cues] + [video.snap_to_silence(c.end, mask, st, 0.8, +1) for c in cues]
res["cut_hygiene_silero"] = {"inside_speech_raw": round(float(np.mean([in_speech(t) for t in raw])), 3),
                             "inside_speech_snapped": round(float(np.mean([in_speech(t) for t in snapped])), 3)}
print(res["cut_hygiene_silero"])
json.dump(res, open(os.path.join(HERE, "results.json"), "w"), indent=1)
