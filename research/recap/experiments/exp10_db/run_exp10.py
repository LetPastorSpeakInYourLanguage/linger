"""exp10 — The Story Understanding Layer as a database (foundation for linger).

A) Build SQLite SUL DBs for Tears of Steel and Panic Room from exp05 outputs; run the queries a recap
   builder / linger feature would run (spine beats with timestamps, setup->payoff edges, top moments).
B) Retrieval benchmark on FriendsQA season 1 (2,990 questions -> which of 326 scenes holds the answer):
   does an understanding layer (speaker attribution, scene summaries) beat raw subtitle search?
   Index variants: raw subtitles (dense / BM25), subtitles+speaker names, scene summaries, hybrid RRF.
"""
import json, os, re, sqlite3, sys, time
import numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from recaplib import datasets as D, subs, store
from recaplib.embed import encode
from rank_bm25 import BM25Okapi
HERE = os.path.dirname(os.path.abspath(__file__)); W = "/home/user/work/exp10"; os.makedirs(W, exist_ok=True)
U5 = "/home/user/wt/exp05-understanding-passes/research/recap/experiments/exp05_understanding"
res = {}

# ---------- A) SUL databases
db_path = os.path.join(W, "sul.sqlite")
if os.path.exists(db_path): os.remove(db_path)
db = store.connect(db_path)
tos_cues = subs.load(f"{D.DATA}/xiaotangii_tears-of-steel-dialogue-dataset/data/tears_of_steel.srt")
store.ingest_understanding(db, "tears_of_steel", "tos", tos_cues, json.load(open(f"{U5}/tos_understanding.json")), name="Tears of Steel")
sys.argv = [sys.argv[0], "Panic Room"]
sys.path.insert(0, U5); import run_film
_, lines, _, _ = run_film.build()
store.ingest_understanding(db, "panic_room", "panic_room", subs.from_lines(lines), json.load(open(f"{U5}/llm_runs/Panic_Room/understanding.json")), name="Panic Room")
Q = {
 "spine_beats_with_time": "SELECT media_id, printf('%.1f-%.1f', t0, t1), tier, short FROM beat WHERE tier='P0' ORDER BY media_id, t0",
 "setup_payoff_edges": "SELECT a.short, '->', b.short FROM beat_edge e JOIN beat a ON a.id=e.src JOIN beat b ON b.id=e.dst WHERE e.kind='pays_off'",
 "strongest_moments": "SELECT media_id, printf('%.1f-%.1f', t0, t1), emotion, what FROM moment WHERE intensity>=3 ORDER BY media_id, t0",
 "turning_points": "SELECT t.media_id, t.tp, b.short FROM turning_point t JOIN beat b ON b.id=t.beat_id",
 "fts_search_heart": "SELECT owner_kind, owner_id, snippet(fts, 2, '[', ']', '..', 8) FROM fts WHERE fts MATCH 'heart OR love' LIMIT 5",
}
res["sul"] = {"tables": {t: db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("title", "media", "cue", "character", "scene", "beat", "beat_edge", "moment", "turning_point", "embedding")},
              "db_kb": round(os.path.getsize(db_path) / 1024), "queries": {k: db.execute(v).fetchall()[:8] for k, v in Q.items()}}
ids, V = store.load_vecs(db, "beat")
qv = encode(["the moment the hero apologizes to the woman he abandoned"])[0]
res["sul"]["semantic_query_example"] = [ids[i] for i in np.argsort(-(V @ qv))[:3]]
print(json.dumps(res["sul"]["tables"]), res["sul"]["semantic_query_example"])

# ---------- B) FriendsQA retrieval
eps = D.friends_season(1)
scenes, sc_utts, sc_spk, sc_plot = [], {}, {}, {}
for e in eps:
    for u in e["utterances"]:
        if u["scene"] not in sc_utts: scenes.append(u["scene"]); sc_utts[u["scene"]] = []; sc_spk[u["scene"]] = []
        sc_utts[u["scene"]].append(u["text"]); sc_spk[u["scene"]].append(f"{(u['speakers'] or ['?'])[0]}: {u['text']}")
    for sid, ps in e["plots"].items():
        sc_plot[sid] = " ".join(p if isinstance(p, str) else " ".join(p) for p in (ps if isinstance(ps, list) else [ps]))
qa = [q for e in eps for q in e["qa"] if q["scene"] in sc_utts]
sidx = {s: i for i, s in enumerate(scenes)}
gold = np.array([sidx[q["scene"]] for q in qa])
t0 = time.time()
def cached(name, texts):
    p = os.path.join(W, name + ".npy")
    if os.path.exists(p): return np.load(p)
    E = encode(texts); np.save(p, E); return E
QE = cached("questions", [q["question"] for q in qa])
flat_u = [(s, t) for s in scenes for t in sc_utts[s]]; flat_s = [(s, t) for s in scenes for t in sc_spk[s]]
EU = cached("utts", [t for _, t in flat_u]); ES = cached("utts_spk", [t for _, t in flat_s])
EP = cached("plots", [sc_plot.get(s, "") for s in scenes])
def maxpool(E, flat):
    owner = np.array([sidx[s] for s, _ in flat]); S = QE @ E.T
    out = np.full((len(qa), len(scenes)), -1.0)
    for j in range(len(scenes)):
        m = owner == j
        if m.any(): top = np.sort(S[:, m], 1)[:, -3:]; out[:, j] = top.mean(1)
    return out
tok = lambda s: re.findall(r"\w+", s.lower())
def bm25(docs):
    bm = BM25Okapi([tok(d) for d in docs]); return np.array([bm.get_scores(tok(q["question"])) for q in qa])
scores = {
    "dense_raw_subs": maxpool(EU, flat_u),
    "bm25_raw_subs": bm25([" ".join(sc_utts[s]) for s in scenes]),
    "dense_subs+speakers": maxpool(ES, flat_s),
    "bm25_subs+speakers": bm25([" ".join(sc_spk[s]) for s in scenes]),
    "dense_scene_summary": QE @ EP.T,
}
has_plot = np.array([s in sc_plot for s in scenes])
scores["dense_scene_summary"][:, ~has_plot] = -1
def rrf(*names, k=60):
    out = np.zeros_like(scores[names[0]])
    for n in names:
        r = np.argsort(np.argsort(-scores[n], 1), 1); out += 1.0 / (k + r + 1)
    return out
scores["hybrid_raw (bm25+dense)"] = rrf("bm25_raw_subs", "dense_raw_subs")
scores["hybrid_SUL (bm25+dense spk + summary)"] = rrf("bm25_subs+speakers", "dense_subs+speakers", "dense_scene_summary")
def recall(S, mask, k):
    r = (S[mask] > S[mask, gold[mask]][:, None]).sum(1); return round(float((r < k).mean()), 3)
masks = {"all_questions": np.ones(len(qa), bool), "questions_whose_scene_has_summary": has_plot[gold]}
res["friendsqa"] = {"questions": len(qa), "scenes": len(scenes), "scenes_with_summary": int(has_plot.sum()), "seconds": round(time.time() - t0)}
for mn, m in masks.items():
    res["friendsqa"][mn] = {name: {f"R@{k}": recall(S, m, k) for k in (1, 5, 10)} for name, S in scores.items()}
print(json.dumps(res["friendsqa"], indent=1))
json.dump(res, open(os.path.join(HERE, "results.json"), "w"), indent=1, default=str)
