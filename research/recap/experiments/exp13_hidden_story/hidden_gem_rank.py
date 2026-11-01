"""Can the system *discover* hidden-story candidates by itself? Rank non-main characters of Friends S1-S3 by
  span (episodes they appear in), presence (lines + mentions), and entanglement with the main spine
  (scenes they share with a P0/P1 spine beat from exp07's series pass)."""
import json, math, os, re, sys
from collections import defaultdict
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from recaplib import datasets as D
HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = {"Ross Geller", "Rachel Green", "Monica Geller", "Chandler Bing", "Joey Tribbiani", "Phoebe Buffay"}
sb = json.load(open("/home/user/wt/exp07-series-scale/research/recap/experiments/exp07_series/llm_runs/p2_series.response.json"))
dg = json.load(open("/home/user/wt/exp07-series-scale/research/recap/experiments/exp07_series/episode_digests.json"))
spine_scenes = {b["scene"] for d in dg for b in d["beats"] if b["id"] in {s["id"] for s in sb["spine"]}}
lines, eps, scenes = defaultdict(int), defaultdict(set), defaultdict(set)
for s in (1, 2, 3):
    for e in D.friends_season(s):
        for u in e["utterances"]:
            for sp in u["speakers"]:
                if sp in MAIN or not sp or sp.startswith("#"): continue
                lines[sp] += 1; eps[sp].add(e["id"]); scenes[sp].add(u["scene"])
rows = []
for c in lines:
    if len(eps[c]) < 2: continue
    ent = len(scenes[c] & spine_scenes)
    score = len(eps[c]) * math.log1p(lines[c]) * (1 + ent)
    rows.append({"character": c, "episodes": len(eps[c]), "lines": lines[c], "spine_scenes": ent, "hidden_gem_score": round(score, 1)})
rows.sort(key=lambda r: -r["hidden_gem_score"])
json.dump(rows[:20], open(os.path.join(HERE, "hidden_gem_ranking.json"), "w"), indent=1)
for r in rows[:15]: print(r)
