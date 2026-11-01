"""exp05b evaluation: LLM understanding (subtitle-only, names scrambled) vs gold TP + MENSA salient scenes."""
import json, os, re, sys
import numpy as np
from sklearn.metrics import roc_auc_score, average_precision_score
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from recaplib import datasets as D
HERE = os.path.dirname(os.path.abspath(__file__))
MOVIE = sys.argv[1] if len(sys.argv) > 1 else "Panic Room"
run = os.path.join(HERE, "llm_runs", re.sub(r"\W", "_", MOVIE))
U = json.load(open(os.path.join(run, "understanding.json"))); meta = json.load(open(os.path.join(run, "meta.json")))
owner = meta["owner"]; scenes = D.tripod_scenes(MOVIE); N = len(scenes)
glob = np.zeros(N); local = np.zeros(N); covered = np.zeros(N)
loc = {b["id"]: b["local_importance"] for c in U["cards"] for s in c["scenes"] for b in s["beats"]}
beat_scene = {}
for b in U["beats"]:
    a, z = b["lines"]
    idxs = sorted(set(owner[i] for i in range(a, z + 1) if i < len(owner)))
    beat_scene[b["id"]] = idxs
    for s in idxs:
        glob[s] = max(glob[s], b["score"]); local[s] = max(local[s], loc[b["id"]] * 20); covered[s] = 1
res = {"movie": MOVIE, "scenes": N, "scenes_with_dialogue": int(len(set(owner))), "beats": len(U["beats"]),
       "scenes_covered_by_beats": int(covered.sum())}
al = D.mensa_alignment(MOVIE.replace(" ", "_")); shift = al["num_scenes"] - N
y = np.zeros(N)
for s in al["salient"]:
    if 0 <= s - shift < N: y[s - shift] = 1
pos = np.linspace(0, 1, N); prior = -(pos - 0.5) ** 2
k = int(y.sum())
def pak(score): return float(y[np.argsort(-score, kind="stable")[:k]].mean())
res["mensa"] = {"salient": k, "AUC_llm_global": round(roc_auc_score(y, glob), 3), "AUC_llm_local": round(roc_auc_score(y, local), 3),
                "AUC_position_prior": round(roc_auc_score(y, prior), 3), "AUC_dialogue_length": round(roc_auc_score(y, [len(s["dialog"]) for s in scenes]), 3),
                "P@k_llm_global": round(pak(glob + 1e-3 * np.array([len(s['dialog']) for s in scenes])), 3), "AP_llm_global": round(average_precision_score(y, glob), 3)}
# P0/P1 tiers as a binary 'would appear in a 5-10 min recap' prediction
tier = {b["id"]: b["tier"] for b in U["beats"]}
pred = np.zeros(N)
for bid, ss in beat_scene.items():
    if tier[bid] in ("P0", "P1"):
        for s in ss: pred[s] = 1
tp_ = (pred * y).sum(); res["mensa"]["P0P1_precision"] = round(float(tp_ / max(1, pred.sum())), 3); res["mensa"]["P0P1_recall"] = round(float(tp_ / y.sum()), 3)
gold = D.tripod_tp_test().get(MOVIE)
if gold:
    names = ["TP1_opportunity", "TP2_change_of_plans", "TP3_point_of_no_return", "TP4_major_setback", "TP5_climax"]
    hits, prior_hits, dists = [], [], []
    for i, n in enumerate(names):
        bid = U["bible"]["turning_points"].get(n)
        ss = beat_scene.get(bid, [])
        d = min(abs(s - g) for s in ss for g in gold[i]) if ss and gold[i] else 99
        dists.append(d); hits.append(d <= 2)
        c = int(round([0.1, 0.25, 0.5, 0.75, 0.95][i] * (N - 1)))
        prior_hits.append(min(abs(c - g) for g in gold[i]) <= 2)
    res["tripod_tp"] = {"gold": gold, "llm_scene_distance": dists, "llm_hit@2": float(np.mean(hits)), "position_prior_hit@2": float(np.mean(prior_hits))}
print(json.dumps(res, indent=1))
json.dump(res, open(os.path.join(HERE, f"eval_{re.sub(r'\W', '_', MOVIE)}.json"), "w"), indent=1)
# ---- ceiling analysis: what subtitles cannot see
has = np.array([1 if s["dialog"] else 0 for s in scenes])
res["ceiling"] = {"salient_scenes_without_dialogue": int(((has == 0) & (y == 1)).sum()), "salient_total": int(y.sum()),
                  "AUC_llm_global_dialogue_scenes_only": round(roc_auc_score(y[has == 1], glob[has == 1]), 3),
                  "AUC_dialogue_length_dialogue_scenes_only": round(roc_auc_score(y[has == 1], np.array([len(s['dialog']) for s in scenes])[has == 1]), 3)}
if gold:
    res["ceiling"]["tp_scenes_without_dialogue"] = [[g for g in gs if not has[g]] for gs in gold]
print(json.dumps(res["ceiling"], indent=1))
json.dump(res, open(os.path.join(HERE, f"eval_{re.sub(r'\W', '_', MOVIE)}.json"), "w"), indent=1)
