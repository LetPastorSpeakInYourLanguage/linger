"""exp07 — Series scale: recap Friends seasons 1-3 (73 episodes, ~184k dialogue words) in 15 minutes.

Hierarchy:  scene cards -> episode digests -> series bible (arcs) -> arc-weighted beat priorities -> budget.
Level-1 scene cards are stood in for by the dataset's crowd-written scene plot sentences (available for
~50% of scenes) so that the series-level LLM pass can be run in-session; in production they come from P1.
Episode digest = up to 6 non-redundant, most central plot sentences (MMR over MiniLM embeddings).
The series pass (replay LLM) assigns arcs + importance; beat score = arc importance x within-episode
centrality, with explicit LLM overrides for spine beats. Then nested MCKP at 1/5/15 min + unlimited.
"""
import json, os, re, sys
import numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from recaplib import datasets as D, select as S
from recaplib.embed import encode
from recaplib.llm import LLM, PendingLLM
HERE = os.path.dirname(os.path.abspath(__file__))


def clean(s): return re.sub(r"\s+([,.'!?])", r"\1", re.sub(r" ' ", "'", s)).strip()


def digests():
    eps = [e for s in (1, 2, 3) for e in D.friends_season(s)]
    out, stats = [], {"dialogue_words": 0, "scenes": 0}
    for e in eps:
        stats["dialogue_words"] += sum(len(u["text"].split()) for u in e["utterances"])
        stats["scenes"] += len(set(u["scene"] for u in e["utterances"]))
        sents = []
        for sc, ps in sorted(e["plots"].items()):
            for p in (ps if isinstance(ps, list) else [ps]):
                p = clean(p)
                if len(p.split()) >= 5: sents.append((sc, p))
        if not sents: out.append({"ep": e["id"], "beats": []}); continue
        E = encode([p for _, p in sents]); cen = E @ E.mean(0)
        chosen = []
        for _ in range(min(6, len(sents))):   # MMR
            best = max((i for i in range(len(sents)) if i not in chosen),
                       key=lambda i: cen[i] - 0.7 * max([float(E[i] @ E[j]) for j in chosen] or [0]))
            if chosen and max(float(E[best] @ E[j]) for j in chosen) > 0.8: break
            chosen.append(best)
        chosen.sort(key=lambda i: sents[i][0])
        cmax = max(cen[i] for i in chosen)
        out.append({"ep": e["id"], "beats": [{"id": f"{e['id']}_b{k}", "scene": sents[i][0], "text": sents[i][1],
                                               "centrality": round(float(cen[i] / cmax), 3)} for k, i in enumerate(chosen)]})
    return out, stats


def main():
    dg, stats = digests()
    json.dump(dg, open(os.path.join(HERE, "episode_digests.json"), "w"), indent=0)
    nb = sum(len(d["beats"]) for d in dg)
    tok_in = int(stats["dialogue_words"] * 1.35 * 1.25)  # words->tokens, + line ids/timestamps overhead
    res = {"episodes": len(dg), "scenes": stats["scenes"], "dialogue_words": stats["dialogue_words"], "digest_beats": nb,
           "token_budget_estimate": {"P1_scene_cards_input": tok_in, "P1_output": int(tok_in * 0.18),
                                     "P1.5_episode_digest_in": int(nb * 40 * 1.35 * 6), "P2_series_in": int(nb * 30 * 1.35),
                                     "note": "P1 dominates (>90%); runs per-episode in parallel; cacheable; one-time per title"}}
    llm = LLM(os.path.join(HERE, "llm_runs"))
    lines = "\n".join(f"{b['id']}: {b['text']}" for d in dg for b in d["beats"])
    sysm = "You are the head story editor of a long-running TV series. Build the series-level understanding from episode digests. Return ONLY JSON."
    prompt = (f"SERIES: a sitcom about six friends in New York, seasons 1-3, {len(dg)} episodes.\nEPISODE DIGEST BEATS (id: text):\n{lines}\n\n"
              "Return JSON: {\"arcs\": [{\"id\": \"A1\", \"title\": str, \"summary\": str, \"importance\": 0-100, \"keywords\": [str]}],\n"
              " \"beat_arc\": {beat_id: arc_id}  // only beats that belong to an arc; others are standalone episode plots\n"
              " \"spine\": [{\"id\": beat_id, \"score\": 0-100, \"tier\": \"P0|P1\", \"requires\": [beat_id]}]  // the beats a 15-minute recap cannot omit\n"
              " \"standalone_importance\": 0-100}")
    try:
        sb = llm.complete_json("p2_series", sysm, prompt)
    except PendingLLM as e:
        print("PENDING", e, res); json.dump(res, open(os.path.join(HERE, "results.json"), "w"), indent=1); return
    arcs = {a["id"]: a for a in sb["arcs"]}; spine = {s["id"]: s for s in sb["spine"]}
    beats = []
    for d in dg:
        for b in d["beats"]:
            arc = sb["beat_arc"].get(b["id"]); ai = arcs[arc]["importance"] if arc else sb["standalone_importance"]
            if b["id"] in spine:
                sc, tier, req = spine[b["id"]]["score"], spine[b["id"]]["tier"], spine[b["id"]].get("requires", [])
            else:
                sc = round(ai * (0.55 + 0.45 * b["centrality"]) * 0.8, 1); req = []
                tier = "P2" if arc else "P3"
            season = int(b["id"][1:3]); ep = int(b["id"][5:7])
            beats.append({"id": b["id"], "text": b["text"], "t": season * 1000 + ep * 30 + int(b["scene"][-2:]), "score": sc, "tier": tier,
                          "requires": req, "arc": arc, "forms": S.default_forms(int(len(b["text"].split()) * 1.3))})
    budgets = [60, 300, 900]
    nested = S.mckp_nested(beats, budgets, overhead=1.5)
    by = {b["id"]: b for b in beats}
    res["selection"] = {}
    for B in budgets + ["unlimited"]:
        sel = nested[B] if B != "unlimited" else S.unlimited(beats)
        cov = S.coverage(sel, beats)
        cov["per_season"] = {s: sum(1 for i in sel["ids"] if i.startswith(f"s0{s}")) for s in (1, 2, 3)}
        cov["per_arc"] = {a: sum(1 for i in sel["ids"] if by[i]["arc"] == a) for a in arcs}
        cov["episodes_touched"] = len(set(i[:7] for i in sel["ids"]))
        res["selection"][str(B)] = cov
    res["arcs"] = {a: {"title": v["title"], "importance": v["importance"], "beats": sum(1 for b in beats if b["arc"] == a)} for a, v in arcs.items()}
    sel15 = nested[900]
    res["recap_15min_outline"] = [f"{i[:7]} [{by[i]['tier']}/{sel15['forms'][i]}] {by[i]['text']}" for i in sorted(sel15["ids"], key=lambda i: by[i]["t"])]
    json.dump(res, open(os.path.join(HERE, "results.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "recap_15min_outline"}, indent=1))


if __name__ == "__main__":
    main()
