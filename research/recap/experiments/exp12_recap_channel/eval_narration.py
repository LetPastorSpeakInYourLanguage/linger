"""exp12 evaluation of recap-channel narrations (automatic part).

grounding   : MiniLM cosine(narration segment, its cited subtitle lines); content-word overlap with cited lines
leakage     : real-world knowledge not present in the (name-scrambled) subtitles — real character/actor names,
              film facts only known from outside (bearer bonds, propane, sledgehammer, $3M/$22M ...)
coverage    : independent reference = Wikipedia synopsis (TRIPOD), names mapped to the scrambled ones;
              a synopsis sentence counts as covered if max cosine to any narration sentence >= 0.55
flow        : length, est. duration, sentence-length stats, punchy-sentence share, transitions, hooks,
              quotes, specifics/100 words, distinct-2, adjacent-sentence coherence
"""
import json, os, re, sys
import numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from recaplib.embed import encode
HERE = os.path.dirname(os.path.abspath(__file__))
U5 = os.path.join(HERE, "../exp05_understanding")
if not os.path.exists(U5): U5 = "/home/user/wt/exp05-understanding-passes/research/recap/experiments/exp05_understanding"
sys.path.insert(0, U5); sys.argv = [sys.argv[0], "Panic Room"]
import run_film
_, LINES, _, _ = run_film.build()
REF = json.load(open(os.path.join(HERE, "reference_synopsis.json")))
LEAK = [r"\bMeg\b", r"\bSarah\b", r"\bBurnham\b", r"\bJunior\b", r"\bRaoul\b", r"\bAltman", r"Foster", r"Whitaker", r"Leto", r"Yoakam",
        r"bearer bond", r"propane", r"sledgehammer", r"\$3 million|three million", r"22 million", r"security company", r"fireproof", r"ignit"]
TRANS = r"^(Then|But|So|Meanwhile|Later|And|Now|Here's|Inside|Upstairs|Downstairs|Out in|On their|That night|When|Some time)"
HOOK = r"(Remember that|Keep that in mind|Big mistake|Here's the irony|changes everything|Except|turns out|irony|tables have turned|bad news|pure chaos)"


def sents(t): return [s for s in re.split(r"(?<=[.!?])\s+", t.strip()) if s]


def mapped(s):
    for a, b in REF["name_map_real_to_scrambled"].items(): s = re.sub(rf"\b{a}\b", b, s)
    return re.sub(r"\s*\([A-Z][a-z]+\)", "", s)


def evaluate(path):
    N = json.load(open(path)); segs = N["segments"]
    text = " ".join(s["text"] for s in segs); words = text.split(); ss = sents(text)
    # grounding
    seg_txt = [s["text"] for s in segs]
    cited = [" ".join(LINES[i]["text"] for i in range(s["lines"][0], s["lines"][1] + 1)) for s in segs]
    E1, E2 = encode(seg_txt), encode(cited)
    cos = (E1 * E2).sum(1)
    stop = set("the a an and or but to of in on at for with is are was be it its this that he she they them his her their you i we what so then just".split())
    def cw(t): return {w for w in re.findall(r"[a-z']+", t.lower()) if w not in stop and len(w) > 2}
    overlap = [len(cw(a) & cw(b)) / max(1, len(cw(a))) for a, b in zip(seg_txt, cited)]
    # leakage
    leaks = {p: len(re.findall(p, text)) for p in LEAK if re.findall(p, text)}
    # coverage vs reference
    ref = [mapped(s) for s in REF["sentences"]]
    ER, ES = encode(ref), encode(ss)
    sim = ER @ ES.T; best = sim.max(1)
    covered = [i for i, b in enumerate(best) if b >= 0.55]
    # flow
    L = np.array([len(s.split()) for s in ss])
    Es = encode(ss); adj = (Es[1:] * Es[:-1]).sum(1)
    toks = [w.lower() for w in re.findall(r"[A-Za-z']+", text)]
    bigr = list(zip(toks, toks[1:]))
    specifics = len(re.findall(r"\b\d+|\bfourteen|thirty|forty-five|five hundred|ten\b", text, re.I)) + text.count("'") // 2 + len(re.findall(r"[A-Z][a-z]+ [A-Z][a-z]+|Titanic|Poe|Flatbush|Glucagon|S\.O\.S", text))
    return {"words": len(words), "est_seconds@2.6wps": round(len(words) / 2.6), "segments": len(segs), "sentences": len(ss),
            "grounding_cos_mean": round(float(cos.mean()), 3), "grounding_cos_min": round(float(cos.min()), 3),
            "content_word_overlap_mean": round(float(np.mean(overlap)), 3),
            "leakage_hits": leaks,
            "ref_coverage@0.55": round(len(covered) / len(ref), 3), "ref_covered_idx": covered,
            "ref_best_sim_mean": round(float(best.mean()), 3),
            "sent_len_mean": round(float(L.mean()), 1), "sent_len_sd": round(float(L.std()), 1), "punchy_share(<=6w)": round(float((L <= 6).mean()), 3),
            "transition_starts": sum(bool(re.match(TRANS, s)) for s in ss), "hooks": len(re.findall(HOOK, text)),
            "quotes_or_dialogue_refs": len(re.findall(r"says|asks|answer|tells|shouts|whispers|calls|yells|swears|:", text)),
            "specifics_per_100w": round(100 * specifics / len(words), 1), "distinct2": round(len(set(bigr)) / max(1, len(bigr)), 3),
            "adjacent_coherence": round(float(adj.mean()), 3)}


if __name__ == "__main__":
    out = {}
    for f in sorted(os.listdir(os.path.join(HERE, "narrations"))):
        if f.endswith(".json") and "harvest" not in f and "verify" not in f:
            out[f] = evaluate(os.path.join(HERE, "narrations", f)); print(f, json.dumps(out[f]))
    json.dump(out, open(os.path.join(HERE, "auto_metrics.json"), "w"), indent=1)
