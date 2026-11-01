"""exp04 — How far do cheap, non-LLM signals get at finding the scenes that matter?

Labels (gold): MENSA salient scenes (scene mentioned in Wikipedia plot, human aligned; 21 movies)
               TRIPOD turning-point scenes (test set, 15 movies, 5 TPs each)
Input: dialogue-only subtitle-like text per scene (no speaker names, no action lines).
Features: position, length, embedding centrality, novelty, future-callback, name-mention of main
characters (inferred by frequency from the dialogue itself), sentiment intensity, ?/! rate.
Models: single features (AUC) + logistic regression with leave-one-movie-out CV.
TP task: pick 5 scenes; hit if within +-2 scenes of gold TP; compare to the screenwriting position prior.
"""
import json, os, re, sys, time
import numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from recaplib import datasets as D
from recaplib.embed import encode
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.preprocessing import StandardScaler
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

CACHE = "/home/user/work/exp04"; os.makedirs(CACHE, exist_ok=True)
VA = SentimentIntensityAnalyzer()
NAME_RE = re.compile(r"\b([A-Z][a-z]{2,})\b")
STOP = set("The This That What When Where Why How You Your Yeah Okay Well Now Then There They She His Her Him And But Not Yes Hey Come Look Just Oh Let God Sorry Thank Thanks Please Good Right Great Wait Listen Know Here All Don Can Did Does Who Its It's".split())
FEATS = ["pos", "pos2", "log_lines", "centrality", "novelty", "callback", "main_names", "sent_abs", "sent_max", "excl_q", "pagerank"]


def movie_features(m):
    scenes = D.tripod_scenes(m)
    cues, owner = [], []
    for s in scenes:
        for c in D.to_subtitle_lines(s["dialog"]):
            cues.append(c["text"]); owner.append(s["idx"])
    cp = os.path.join(CACHE, re.sub(r"\W", "_", m) + ".npy")
    if os.path.exists(cp): E = np.load(cp)
    else: E = encode(cues); np.save(cp, E)
    owner = np.array(owner); N = len(scenes)
    names = {}
    for t in cues:
        for n in NAME_RE.findall(t):
            if n not in STOP: names[n] = names.get(n, 0) + 1
    main = set(sorted(names, key=lambda k: -names[k])[:6])
    SE = np.zeros((N, E.shape[1])); has = np.zeros(N, bool)
    for i in range(N):
        idx = np.where(owner == i)[0]
        if len(idx): SE[i] = E[idx].mean(0); SE[i] /= np.linalg.norm(SE[i]) + 1e-9; has[i] = True
    mean = SE[has].mean(0); mean /= np.linalg.norm(mean)
    S = SE @ SE.T
    import networkx as nx
    G = nx.Graph()
    for i in np.where(has)[0]:
        for j in np.where(has)[0]:
            if i < j and S[i, j] > 0.3: G.add_edge(int(i), int(j), weight=float(S[i, j]))
    pr = nx.pagerank(G) if G.number_of_edges() else {}
    X = np.zeros((N, len(FEATS)))
    for i in range(N):
        idx = np.where(owner == i)[0]; txt = [cues[k] for k in idx]
        pos = i / max(1, N - 1)
        prev = S[i, :i][has[:i]] if i else np.array([0.0]); fut = S[i, i + 1:][has[i + 1:]] if i < N - 1 else np.array([0.0])
        sent = [abs(VA.polarity_scores(t)["compound"]) for t in txt] or [0]
        X[i] = [pos, (pos - 0.5) ** 2, np.log1p(len(txt)), float(SE[i] @ mean) if has[i] else 0,
                1 - (prev.max() if len(prev) else 0) if has[i] else 0, (fut.max() if len(fut) else 0) if has[i] else 0,
                sum(1 for t in txt for n in NAME_RE.findall(t) if n in main), np.mean(sent), np.max(sent),
                sum(t.count("!") + t.count("?") for t in txt) / max(1, len(txt)), pr.get(i, 0) * N]
    return X, N


def main():
    t0 = time.time(); res = {}
    movies = sorted(os.listdir(D.TRIPOD + "/Screenplays_and_imdb_meta"))
    # ---- MENSA saliency
    data = []
    for m in movies:
        al = D.mensa_alignment(m.replace(" ", "_"))
        if not al: continue
        X, N = movie_features(m)
        shift = al["num_scenes"] - N
        if shift not in (0, 1): continue
        y = np.zeros(N)
        for s in al["salient"]:
            if 0 <= s - shift < N: y[s - shift] = 1
        data.append((m, X, y))
    single = {}
    for j, f in enumerate(FEATS):
        aucs = [roc_auc_score(y, X[:, j]) for _, X, y in data if 0 < y.sum() < len(y)]
        single[f] = round(float(np.mean(aucs)), 3)
    aucs, aps, p_at_k, base = [], [], [], []
    for k, (m, X, y) in enumerate(data):
        Xtr = np.vstack([d[1] for i, d in enumerate(data) if i != k]); ytr = np.concatenate([d[2] for i, d in enumerate(data) if i != k])
        sc = StandardScaler().fit(Xtr); clf = LogisticRegression(max_iter=2000, C=0.5).fit(sc.transform(Xtr), ytr)
        p = clf.predict_proba(sc.transform(X))[:, 1]
        aucs.append(roc_auc_score(y, p)); aps.append(average_precision_score(y, p)); base.append(y.mean())
        kk = int(y.sum()); p_at_k.append(y[np.argsort(-p)[:kk]].mean())
    clf_all = LogisticRegression(max_iter=2000, C=0.5).fit(StandardScaler().fit_transform(np.vstack([d[1] for d in data])), np.concatenate([d[2] for d in data]))
    res["mensa"] = {"movies": len(data), "scenes": int(sum(len(d[2]) for d in data)), "salient_rate": round(float(np.mean(base)), 3),
                    "single_feature_AUC": single, "logreg_LOMO_AUC": round(float(np.mean(aucs)), 3),
                    "logreg_AP": round(float(np.mean(aps)), 3), "logreg_P@k": round(float(np.mean(p_at_k)), 3),
                    "coef": {f: round(float(c), 2) for f, c in zip(FEATS, clf_all.coef_[0])}}
    print(json.dumps(res["mensa"], indent=1))
    # ---- TRIPOD turning points: hit@+-2 scenes
    tp = D.tripod_tp_test(); prior = [0.1, 0.25, 0.5, 0.75, 0.95]
    feats_model = clf_all; scaler = StandardScaler().fit(np.vstack([d[1] for d in data]))
    hits = {"position_prior": [], "salience_in_window": []}
    for m, gold in tp.items():
        X, N = movie_features(m)
        p = feats_model.predict_proba(scaler.transform(X))[:, 1]
        for t, g in enumerate(gold):
            if not g: continue
            c = int(round(prior[t] * (N - 1)))
            hits["position_prior"].append(min(abs(c - x) for x in g) <= 2)
            lo, hi = max(0, c - int(0.08 * N)), min(N, c + int(0.08 * N) + 1)   # search around the prior
            best = lo + int(np.argmax(p[lo:hi]))
            hits["salience_in_window"].append(min(abs(best - x) for x in g) <= 2)
    res["tripod_tp"] = {k: round(float(np.mean(v)), 3) for k, v in hits.items()}
    res["tripod_tp"]["n_tps"] = len(hits["position_prior"])
    res["seconds"] = round(time.time() - t0)
    print(res["tripod_tp"])
    json.dump(res, open(os.path.join(os.path.dirname(__file__), "results.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
