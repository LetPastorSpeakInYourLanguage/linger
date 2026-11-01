"""exp15 — Trait/theme compilations: "all the times Joey was a good friend" (Friends S1-S3).

Pipeline: speaker layer -> scenes where Joey speaks -> rank by 3 retrievers -> LLM judge (in-session) on the pooled
top-K -> precision@K per retriever + pooled relative recall -> ordered compilation with clip anchors.
Retrievers: R1 dense(query, Joey's own lines, max-pool), R2 dense(query, scene summary), R3 dense(query, whole scene dialogue).
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from recaplib import datasets as D
from recaplib.embed import encode
HERE = os.path.dirname(os.path.abspath(__file__))
QUERY = ["Joey helps a friend", "Joey supports and comforts his friend", "Joey sacrifices something for a friend",
         "Joey defends his friend", "Joey is loyal and kind to his friends"]
scenes = {}
for s in (1, 2, 3):
    for e in D.friends_season(s):
        for u in e["utterances"]:
            sc = scenes.setdefault(u["scene"], {"scene": u["scene"], "joey": [], "all": [], "plot": ""})
            sc["all"].append(f"{(u['speakers'] or ['?'])[0].split()[0]}: {u['text']}")
            if "Joey Tribbiani" in u["speakers"]: sc["joey"].append(u["text"])
        for sid, p in e["plots"].items():
            if sid in scenes: scenes[sid]["plot"] = " ".join(p if isinstance(p, list) else [p])
cand = [v for v in scenes.values() if v["joey"]]
Q = encode(QUERY).mean(0); Q /= np.linalg.norm(Q)
def r1(c): E = encode(c["joey"]); return float(np.sort(E @ Q)[-3:].mean())
def r2(c): return float(encode([c["plot"]])[0] @ Q) if c["plot"] else -1.0
def r3(c): return float(encode([" ".join(c["all"])[:2000]])[0] @ Q)
for c in cand: c["r1"], c["r2"], c["r3"] = r1(c), r2(c), r3(c)
K = 20; pool = {}
for k in ("r1", "r2", "r3"):
    for c in sorted(cand, key=lambda c: -c[k])[:K]: pool.setdefault(c["scene"], c)
json.dump({"n_scenes_total": len(scenes), "n_joey_scenes": len(cand), "with_summary": sum(1 for c in cand if c["plot"]),
           "rank": {k: [c["scene"] for c in sorted(cand, key=lambda c: -c[k])[:K]] for k in ("r1", "r2", "r3")},
           "pool": sorted(pool)}, open(os.path.join(HERE, "candidates.json"), "w"), indent=1)
print(len(scenes), len(cand), len(pool))
for sid in sorted(pool):
    c = pool[sid]
    print(f"## {sid} | plot: {c['plot'][:180]}")
    print("   " + " / ".join(x[:110] for x in c["all"][:10]))
