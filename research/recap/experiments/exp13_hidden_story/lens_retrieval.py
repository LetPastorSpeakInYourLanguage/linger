"""exp13 — character-lens retrieval: how much of a SECONDARY character's story does the main SUL hold,
versus a dedicated second pass over subtitles?

Gold presence = lines the character speaks (gold speakers) + lines that mention them.
O1 = main SUL (beats whose 'who' lists the character / text mentions them).
O2 = lens retrieval for a second pass: (a) mention-only (name/alias in text) ±2 lines context,
     (b) + speaker-attributed lines (speaker layer; gold speakers = upper bound of exp03-style attribution).
"""
import json, os, re, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from recaplib import datasets as D
HERE = os.path.dirname(os.path.abspath(__file__))
U5 = "/home/user/wt/exp05-understanding-passes/research/recap/experiments/exp05_understanding"
res = {}

# ---------- Panic Room: Lena
meta = json.load(open(f"{U5}/llm_runs/Panic_Room/meta.json")); U = json.load(open(f"{U5}/llm_runs/Panic_Room/understanding.json"))
sys.path.insert(0, U5); sys.argv = [sys.argv[0], "Panic Room"]; import run_film
_, lines, owner, _ = run_film.build()
spk = meta["gold_speakers"]; N = len(lines)
spoken = {i for i in range(N) if spk[i] == "Lena"}
mention = {i for i in range(N) if re.search(r"\bLena\b", lines[i]["text"])}
gold_scenes = {owner[i] for i in spoken | mention}
beats = [b for c in U["cards"] for s in c["scenes"] for b in s["beats"] if "Lena" in b.get("who", []) or "Lena" in b["text"]]
o1_lines = {i for b in beats for i in range(b["lines"][0], b["lines"][1] + 1)}
ctx = lambda S: {j for i in S for j in range(max(0, i - 2), min(N, i + 3))}
o2a = ctx(mention); o2b = ctx(mention | spoken)
def rec(S, G): return round(len(S & G) / len(G), 3)
res["panic_room_lena"] = {"lines_spoken": len(spoken), "lines_mentioning": len(mention), "gold_scenes": len(gold_scenes),
    "O1_main_SUL": {"beats_about_char": len(beats), "spoken_line_recall": rec(o1_lines, spoken), "scene_recall": rec({owner[i] for i in o1_lines}, gold_scenes)},
    "O2a_mentions_ctx": {"lines": len(o2a), "spoken_line_recall": rec(o2a, spoken), "scene_recall": rec({owner[i] for i in o2a}, gold_scenes)},
    "O2b_mentions+speaker": {"lines": len(o2b), "spoken_line_recall": rec(o2b, spoken), "scene_recall": rec({owner[i] for i in o2b}, gold_scenes),
                             "share_of_film": round(len(o2b) / N, 3)}}
json.dump(sorted(o2b), open(os.path.join(HERE, "lena_lens_lines.json"), "w"))

# ---------- Friends S1-S3: Gunther
utts = [(e["id"], u) for s in (1, 2, 3) for e in D.friends_season(s) for u in e["utterances"]]
g_sp = {k for k, (_, u) in enumerate(utts) if any("Gunther" in x for x in u["speakers"])}
g_mn = {k for k, (_, u) in enumerate(utts) if re.search(r"\bGunther\b", u["text"])}
scene_of = [u["scene"] for _, u in utts]
gold_sc = {scene_of[k] for k in g_sp | g_mn}
dg = json.load(open("/home/user/wt/exp07-series-scale/research/recap/experiments/exp07_series/episode_digests.json"))
o1 = [b for d in dg for b in d["beats"] if "Gunther" in b["text"]]
plots_mention = sum(1 for s in (1, 2, 3) for e in D.friends_season(s) for sid, p in e["plots"].items() if "Gunther" in json.dumps(p))
M = len(utts); ctxF = lambda S: {j for i in S for j in range(max(0, i - 2), min(M, i + 3))}
f2a, f2b = ctxF(g_mn), ctxF(g_mn | g_sp)
res["friends_gunther"] = {"utterances_spoken": len(g_sp), "utterances_mentioning": len(g_mn), "gold_scenes": len(gold_sc),
    "episodes": len({scene_of[k][:7] for k in g_sp | g_mn}),
    "O1_series_SUL_digest_beats": len(o1), "O1_scene_recall": round(len({b['scene'] for b in o1} & gold_sc) / len(gold_sc), 3),
    "crowd_scene_plots_mentioning": plots_mention,
    "O2a_mentions_ctx": {"utterances": len(f2a), "scene_recall": round(len({scene_of[k] for k in f2a} & gold_sc) / len(gold_sc), 3)},
    "O2b_mentions+speaker": {"utterances": len(f2b), "scene_recall": 1.0, "share_of_corpus": round(len(f2b) / M, 4)}}
json.dump([{"ep": utts[k][0], "scene": scene_of[k], "speaker": utts[k][1]["speakers"][:1], "text": utts[k][1]["text"]} for k in sorted(f2b)],
          open(os.path.join(HERE, "gunther_lens_lines.json"), "w"), indent=0)
json.dump(res, open(os.path.join(HERE, "lens_results.json"), "w"), indent=1)
print(json.dumps(res, indent=1))
