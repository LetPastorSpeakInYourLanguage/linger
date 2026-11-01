"""exp03 — Who said what, when subtitles carry no speaker names.

A) Friends S1 (24 eps, gold speakers), names stripped. Text-only heuristics:
   majority, alternation (A-B-A-B), vocative ("..., Ross?" -> next speaker is Ross),
   vocative+alternation. Also the LLM pass on a 120-line window (replay protocol).
B) Tears of Steel: fuse audio diarization clusters (language-agnostic voice embeddings, from the
   dataset repo: ECAPA clusters per cue) with LLM-inferred names -> cluster naming by majority vote.
"""
import json, os, re, sys
from collections import Counter
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from recaplib import datasets as D, subs
from recaplib.llm import LLM, PendingLLM
HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = ["Ross Geller", "Rachel Green", "Monica Geller", "Chandler Bing", "Joey Tribbiani", "Phoebe Buffay"]
FIRST = {n.split()[0]: n for n in MAIN}
VOC = re.compile(r"(?:^|[,.!?]\s*)(" + "|".join(FIRST) + r")(?:[,.!?]|$)")


def predict(utts):
    texts = [u["text"] for u in utts]
    maj = MAIN[0]
    out = {"majority": [], "alternation": [], "vocative": [], "vocative+alt": []}
    cnt = Counter()
    for i, t in enumerate(texts):
        out["majority"].append(maj)
        out["alternation"].append(out["alternation"][i - 2] if i >= 2 else maj)
        v = VOC.findall(texts[i - 1]) if i else []
        vp = FIRST[v[-1]] if v else None
        out["vocative"].append(vp or maj)
        prev2 = out["vocative+alt"][i - 2] if i >= 2 else maj
        # vocative in line i-1 addresses the next speaker; vocative in my own line names someone else
        own = [FIRST[x] for x in VOC.findall(t)]
        guess = vp or prev2
        if guess in own and i >= 1: guess = out["vocative+alt"][i - 1] if out["vocative+alt"][i - 1] not in own else maj
        out["vocative+alt"].append(guess)
    return out


def acc(pred, gold):
    ok = [p in g for p, g in zip(pred, gold) if g]
    return round(sum(ok) / len(ok), 3)


def main():
    res = {"friends": {}}
    allp = {}
    for ep in D.friends_season(1):
        utts = [u for u in ep["utterances"]]
        gold = [u["speakers"] for u in utts]
        for k, v in predict(utts).items():
            allp.setdefault(k, []).append((v, gold))
    for k, lst in allp.items():
        tot = sum(len([g for g in gold if g]) for _, gold in lst)
        ok = sum(sum(p in g for p, g in zip(pred, gold) if g) for pred, gold in lst)
        res["friends"][k] = round(ok / tot, 3)
    main_share = Counter(s for ep in D.friends_season(1) for u in ep["utterances"] for s in u["speakers"][:1])
    tot = sum(main_share.values())
    res["friends"]["share_main6"] = round(sum(main_share[n] for n in MAIN) / tot, 3)
    # LLM window
    ep = D.friends_season(1)[2]; win = ep["utterances"][:120]
    llm = LLM(os.path.join(HERE, "llm_runs/friends"))
    lines = "\n".join(f"L{i} {u['text']}" for i, u in enumerate(win))
    sysm = ("You attribute speakers to subtitle lines of a TV episode. Lines have no names. Use conversational structure, "
            "vocatives (a name said in a line usually addresses the NEXT speaker, not the current one), who is mentioned, "
            "personalities and context. Return ONLY JSON.")
    prompt = (f"SHOW CAST: {', '.join(MAIN)}; other speakers: use a short role label (e.g. 'Waitress') or '?'.\n"
              f"LINES:\n{lines}\n\nReturn JSON: {{\"speakers\": {{\"L0\": \"Name\", ...}}, \"scene_breaks\": [line ids where a new scene starts]}}")
    try:
        r = llm.complete_json("speakers_s01e03_0_120", sysm, prompt)
        pred = [r["speakers"].get(f"L{i}", "?") for i in range(len(win))]
        gold = [u["speakers"] for u in win]
        def norm(x): return FIRST.get(x.split()[0], x) if x and x != "?" else x
        ok = [norm(p) in g for p, g in zip(pred, gold) if g]
        base = predict(win)
        res["friends_llm_window"] = {"episode": ep["id"], "lines": len(win), "llm_acc": round(sum(ok) / len(ok), 3),
                                     "vocative+alt_acc_same_window": acc(base["vocative+alt"], gold),
                                     "llm_scene_breaks": r.get("scene_breaks"),
                                     "gold_scene_breaks": [i for i in range(1, len(win)) if win[i]["scene"] != win[i - 1]["scene"]]}
    except PendingLLM as e:
        res["friends_llm_window"] = f"PENDING {e}"
    # ToS fusion: diarization cluster -> LLM names
    dia = [json.loads(l) for l in open(f"{D.DATA}/xiaotangii_tears-of-steel-dialogue-dataset/output/cue_speakers.jsonl")]
    tos = json.load(open("/home/user/wt/exp05-understanding-passes/research/recap/experiments/exp05_understanding/tos_understanding.json"))
    names = {}
    for s in tos["cards"][0]["scenes"]:
        for k, v in s["speakers"].items(): names[int(k[1:])] = v
    cues = subs.load(f"{D.DATA}/xiaotangii_tears-of-steel-dialogue-dataset/data/tears_of_steel.srt")
    by_time = {round(c.start, 1): c.idx for c in cues}
    pairs = []
    for d in dia:
        i = by_time.get(round(d["start"], 1))
        if i is not None and names.get(i) and "?" not in names[i]:
            pairs.append((d["speaker"], names[i].split()[0]))
    clusters = {}
    for c, n in pairs: clusters.setdefault(c, Counter())[n] += 1
    named = {c: cnt.most_common(1)[0] for c, cnt in clusters.items()}
    agree = sum(cnt.most_common(1)[0][1] for cnt in clusters.values()) / max(1, len(pairs))
    unknown_lines = [i for i, v in names.items() if "?" in v]
    filled = 0
    for d in dia:
        i = by_time.get(round(d["start"], 1))
        if i in unknown_lines and d["speaker"] in named: filled += 1
    res["tos_fusion"] = {"diar_clusters": len(set(d["speaker"] for d in dia)), "cues_with_cluster": len(dia),
                         "llm_named_cues": len(pairs), "cluster_name_purity": round(agree, 3),
                         "cluster_names": {c: f"{n} ({k}/{sum(clusters[c].values())})" for c, (n, k) in named.items()},
                         "llm_unknown_cues": len(unknown_lines), "unknown_cues_named_via_voice_cluster": filled}
    json.dump(res, open(os.path.join(HERE, "results.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
