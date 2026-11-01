"""exp02 — Scene segmentation from subtitle text only (no names, no headings).

Ground truth: Friends S1 (24 episodes) scene ids; 21 TRIPOD/MENSA screenplays (dialogue-only).
Methods
  even_oracleK   : K evenly spaced boundaries, K = true #scenes (upper-bound-ish naive baseline)
  even_priorK    : K from a prior of lines/scene estimated on the *other* corpus
  tiling_emb     : TextTiling with MiniLM embeddings (window w), depth-score peaks above mean-0.5std
  tiling_emb_K   : same, top-K peaks with prior K
  tiling+names   : depth + character-name-set change bonus (names mentioned in window)
Metrics: Pk, WindowDiff (k = half mean ref segment), boundary F1 (+-2 lines).
"""
import json, os, re, sys, time
import numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from recaplib import datasets as D
from recaplib.embed import encode

CACHE = "/home/user/work/exp02"; os.makedirs(CACHE, exist_ok=True)


def seg_from_bounds(n, bounds):
    lab, s = [], 0
    b = set(bounds)
    for i in range(n):
        if i in b and i > 0: s += 1
        lab.append(s)
    return lab


def pk_wd(ref, hyp, k=None):
    n = len(ref)
    if k is None:
        nseg = len(set(ref)); k = max(2, int(round(n / nseg / 2)))
    pk = wd = 0; cnt = 0
    for i in range(n - k):
        r = ref[i] != ref[i + k]; h = hyp[i] != hyp[i + k]
        pk += r != h
        rb = sum(ref[j] != ref[j + 1] for j in range(i, i + k)); hb = sum(hyp[j] != hyp[j + 1] for j in range(i, i + k))
        wd += rb != hb; cnt += 1
    return pk / cnt, wd / cnt


def bf1(rb, hb, tol=2):
    rb, hb = sorted(rb), sorted(hb)
    used = set(); tp = 0
    for h in hb:
        m = [r for r in rb if abs(r - h) <= tol and r not in used]
        if m: used.add(min(m, key=lambda r: abs(r - h))); tp += 1
    p = tp / len(hb) if hb else 0; r = tp / len(rb) if rb else 0
    return 2 * p * r / (p + r) if p + r else 0


def depth_scores(E, w=4):
    n = len(E); sims = np.zeros(n)
    for i in range(1, n):
        L = E[max(0, i - w):i].mean(0); R = E[i:i + w].mean(0)
        sims[i] = L @ R / (np.linalg.norm(L) * np.linalg.norm(R) + 1e-9)
    depth = np.zeros(n)
    for i in range(1, n - 1):
        l = sims[i]; j = i
        while j > 1 and sims[j - 1] >= sims[j]: j -= 1
        lp = sims[j]
        j = i
        while j < n - 1 and sims[j + 1] >= sims[j]: j += 1
        rp = sims[j]
        depth[i] = (lp - l) + (rp - l)
    return depth


def peaks(depth, K=None, min_gap=3):
    order = np.argsort(-depth)
    if K is None:
        thr = depth[depth > 0].mean() + 0.5 * depth[depth > 0].std() if (depth > 0).any() else 1e9
        cand = [i for i in order if depth[i] > thr]
    else:
        cand = list(order)
    chosen = []
    for i in cand:
        if all(abs(i - j) >= min_gap for j in chosen):
            chosen.append(int(i))
        if K is not None and len(chosen) >= K: break
    return sorted(chosen)


NAME_RE = re.compile(r"\b([A-Z][a-z]{2,})\b")
STOP = set("The This That What When Where Why How You Your Yeah Okay Well Now Then There They She His Her Him And But Not Yes Hey Come Look Just Oh Let God Sorry Thank Thanks Please Mr Mrs Miss Good Right Great Wait Listen Know Here All".split())


def name_shift(texts, w=6):
    names = [set(n for n in NAME_RE.findall(t) if n not in STOP) for t in texts]
    n = len(texts); s = np.zeros(n)
    for i in range(1, n):
        L = set().union(*names[max(0, i - w):i]); R = set().union(*names[i:i + w])
        if L or R: s[i] = 1 - len(L & R) / len(L | R)
    return s


def docs():
    out = []
    for ep in D.friends_season(1):
        texts = [u["text"] for u in ep["utterances"]]; sc = [u["scene"] for u in ep["utterances"]]
        out.append(("friends", ep["id"], texts, [i for i in range(1, len(sc)) if sc[i] != sc[i - 1]]))
    movies = sorted(os.listdir(D.TRIPOD + "/Screenplays_and_imdb_meta"))
    for m in movies:
        if not D.mensa_alignment(m.replace(" ", "_")): continue
        scenes = D.tripod_scenes(m)
        if not scenes: continue
        texts, b = [], []
        for s in scenes:
            cues = D.to_subtitle_lines(s["dialog"])
            if not cues: continue
            if texts: b.append(len(texts))
            texts += [c["text"] for c in cues]
        out.append(("tripod", m, texts, b))
    return out


def main():
    res = {"friends": {}, "tripod": {}}
    ds = docs()
    lines_per_scene = {c: np.mean([len(t) / (len(b) + 1) for cc, _, t, b in ds if cc == c]) for c in ("friends", "tripod")}
    t0 = time.time()
    for corpus, did, texts, rb in ds:
        cp = os.path.join(CACHE, re.sub(r"\W", "_", did) + ".npy")
        if os.path.exists(cp): E = np.load(cp)
        else: E = encode(texts); np.save(cp, E)
        n = len(texts); ref = seg_from_bounds(n, rb); K = len(rb)
        other = "tripod" if corpus == "friends" else "friends"
        Kp = max(1, int(round(n / lines_per_scene[other])))
        dep = depth_scores(E, 4); ns = name_shift(texts)
        comb = dep / (dep.max() + 1e-9) + 0.35 * ns / (ns.max() + 1e-9)
        hyps = {
            "even_oracleK": [int(round(i * n / (K + 1))) for i in range(1, K + 1)],
            "even_priorK": [int(round(i * n / (Kp + 1))) for i in range(1, Kp + 1)],
            "tiling_emb": peaks(dep),
            "tiling_emb_oracleK": peaks(dep, K),
            "tiling+names": peaks(comb),
            "tiling+names_oracleK": peaks(comb, K),
        }
        for name, hb in hyps.items():
            pk, wd = pk_wd(ref, seg_from_bounds(n, hb))
            res[corpus].setdefault(name, []).append((pk, wd, bf1(rb, hb), len(hb) / max(1, K)))
    summ = {c: {m: {"Pk": round(float(np.mean([x[0] for x in v])), 3), "WD": round(float(np.mean([x[1] for x in v])), 3),
                     "F1@2": round(float(np.mean([x[2] for x in v])), 3), "pred/true": round(float(np.mean([x[3] for x in v])), 2)}
                 for m, v in r.items()} for c, r in res.items()}
    summ["n_docs"] = {c: sum(1 for d in ds if d[0] == c) for c in ("friends", "tripod")}
    summ["lines_per_scene"] = {k: round(float(v), 1) for k, v in lines_per_scene.items()}
    summ["seconds"] = round(time.time() - t0)
    json.dump(summ, open(os.path.join(os.path.dirname(__file__), "results.json"), "w"), indent=1)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
