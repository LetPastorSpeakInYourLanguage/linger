"""exp16 prep — discourse corpora -> ~45 s retrieval windows; 3 retrievers per topic query; pooled top-10 for judging.
Sermons: 7 sermons by one pastor (speaker-labelled, no timestamps -> times estimated at 2.5 words/s).
Podcast: 8 Joe Rogan Experience episodes with Jordan Peterson (YouTube auto-captions: no punctuation, no speakers)."""
import glob, json, os, re, sys
import numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from recaplib.embed import encode
from rank_bm25 import BM25Okapi
W = "/home/user/work/exp16"; HERE = os.path.dirname(os.path.abspath(__file__))
QUERIES = {"sermons": ("Pastor Andrew VanderMaas", "what the pastor says about women, wives, husbands and marriage"),
           "jre": ("Jordan Peterson", "what Jordan Peterson says about the meaning of life, purpose and responsibility")}


def sermon_windows():
    out = []
    for s in json.load(open(f"{W}/sermons.json")):
        if s["preacher"] != "Pastor Andrew VanderMaas": continue
        text = " ".join(x["text"] for x in s["segments"] if "sermon" in x["part"].lower())
        sents = re.split(r"(?<=[.!?])\s+", text.strip()); t = 0.0; buf, t0 = [], 0.0
        for se in sents:
            buf.append(se); t += len(se.split()) / 2.5
            if sum(len(b.split()) for b in buf) >= 110:
                out.append({"src": s["title"], "t0": round(t0, 1), "t1": round(t, 1), "text": " ".join(buf)}); buf, t0 = [], t
        if buf: out.append({"src": s["title"], "t0": round(t0, 1), "t1": round(t, 1), "text": " ".join(buf)})
    return out


def jre_windows():
    out = []
    for f in sorted(glob.glob("/home/user/data_untrusted/disc/RohitWaghire_Joe-Rogan-Experience-Transcripts/Transcripts/*Jordan Peterson*.md")):
        ep = re.search(r"#(\d+)", f).group(1); rows = []
        for l in open(f, encoding="utf-8"):
            m = re.match(r"\[(?:(\d+):)?(\d+):(\d+)\]\s*(.*)", l.strip())
            if m: rows.append(((int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))), m.group(4)))
        i = 0
        while i < len(rows):
            j = i; 
            while j < len(rows) and rows[j][0] - rows[i][0] < 45: j += 1
            out.append({"src": f"JRE #{ep}", "t0": rows[i][0], "t1": rows[min(j, len(rows) - 1)][0], "text": " ".join(r[1] for r in rows[i:j]),
                        "gaps": [rows[k + 1][0] - rows[k][0] for k in range(i, min(j, len(rows) - 1))]})
            i = j
    return out


tok = lambda s: re.findall(r"\w+", s.lower())
res = {}
for name, wins in (("sermons", sermon_windows()), ("jre", jre_windows())):
    who, q = QUERIES[name]
    E = encode([w["text"] for w in wins]); qv = encode([q])[0]
    dense = E @ qv
    bm = np.array(BM25Okapi([tok(w["text"]) for w in wins]).get_scores(tok(q)))
    rr = lambda s: np.argsort(np.argsort(-s))
    hybrid = 1 / (60 + rr(dense)) + 1 / (60 + rr(bm))
    ranks = {k: [int(i) for i in np.argsort(-v)[:10]] for k, v in (("bm25", bm), ("dense", dense), ("hybrid", hybrid))}
    pool = sorted(set(sum(ranks.values(), [])))
    res[name] = {"windows": len(wins), "words": sum(len(w["text"].split()) for w in wins), "query": q, "ranks": ranks, "pool": pool}
    json.dump(wins, open(f"{W}/{name}_windows.json", "w"))
    print(f"\n##### {name}: {len(wins)} windows, {res[name]['words']} words, pool {len(pool)}  Q: {q}")
    for i in pool: print(f"[{name}:{i}] {wins[i]['src']} @{int(wins[i]['t0'])//60}:{int(wins[i]['t0'])%60:02d} :: {wins[i]['text'][:620]}")
json.dump(res, open(os.path.join(HERE, "retrieval_pools.json"), "w"), indent=1)
