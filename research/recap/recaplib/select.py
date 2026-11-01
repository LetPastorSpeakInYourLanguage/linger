"""Duration-budgeted content selection over prioritized story beats.

A beat = {id, score (0-100 global importance), tier P0..P3, requires [ids], t (story time), forms}
where forms are alternative renderings with (seconds, value_fraction):
  full  : ~2 sentences narration + footage     (value 1.0)
  short : 1 sentence                           (value 0.65)
  micro : a clause folded into a neighbour     (value 0.35)

Algorithms compared in experiments:
  greedy_prefix  : walk a fixed priority order (tier, then score); add beat + dependency closure while it fits.
                   Guarantees NESTEDNESS (a shorter recap is always a subset of a longer one).
  greedy_ratio   : classic value/cost greedy (not nested in general).
  mckp           : multiple-choice knapsack DP over forms with dependency repair — maximises covered
                   importance, can say more things more briefly when time is short ("elastic beats").
  unlimited      : everything with score >= floor, full form.
"""
from __future__ import annotations
import math

TIER_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
FORM_VALUE = {"full": 1.0, "short": 0.65, "micro": 0.35}


def default_forms(words_full: int, wps=2.6, min_visual=2.0):
    wf = max(words_full, 8)
    return {"full": max(wf / wps, min_visual) + 0.6,
            "short": max(wf * 0.45 / wps, min_visual) + 0.4,
            "micro": max(wf * 0.2 / wps, 1.2)}


def priority_order(beats):
    return sorted(beats, key=lambda b: (TIER_RANK.get(b.get("tier", "P3"), 3), -b.get("score", 0), b.get("t", 0)))


def closure(bid, by_id, seen=None):
    seen = set() if seen is None else seen
    if bid in seen or bid not in by_id:
        return seen
    seen.add(bid)
    for r in by_id[bid].get("requires", []):
        closure(r, by_id, seen)
    return seen


def greedy_prefix(beats, budget_s, form="full", strict_prefix=False):
    by_id = {b["id"]: b for b in beats}
    chosen, used = [], 0.0
    for b in priority_order(beats):
        if b["id"] in chosen:
            continue
        add = [x for x in closure(b["id"], by_id) if x not in chosen]
        cost = sum(by_id[x]["forms"][form] for x in add)
        if used + cost <= budget_s:
            chosen += add; used += cost
        elif strict_prefix:
            break
    return {"ids": chosen, "forms": {i: form for i in chosen}, "seconds": used,
            "value": sum(by_id[i]["score"] for i in chosen)}


def greedy_ratio(beats, budget_s, form="full"):
    by_id = {b["id"]: b for b in beats}
    chosen, used = [], 0.0
    for b in sorted(beats, key=lambda b: -b["score"] / b["forms"][form]):
        add = [x for x in closure(b["id"], by_id) if x not in chosen]
        cost = sum(by_id[x]["forms"][form] for x in add)
        if used + cost <= budget_s:
            chosen += add; used += cost
    return {"ids": chosen, "forms": {i: form for i in chosen}, "seconds": used,
            "value": sum(by_id[i]["score"] for i in chosen)}


def mckp(beats, budget_s, step=0.5, tier_bonus=(1.6, 1.25, 1.0, 0.8), overhead=0.0, forced=()):
    """Multiple-choice knapsack: pick at most one form per beat, maximise sum(score*form_value*tier_bonus).
    Dependency repair afterwards: if a chosen beat requires an unchosen one, the required beat is
    forced in at 'micro' form and the lowest-value item is dropped until it fits again."""
    by_id = {b["id"]: b for b in beats}
    order = sorted(beats, key=lambda b: b.get("t", 0))
    W = int(budget_s / step)
    NEG = -1e18
    dp = [0.0] + [NEG] * W
    choice = []
    for b in order:
        tb = tier_bonus[TIER_RANK.get(b.get("tier", "P3"), 3)]
        opts = [(f, int(math.ceil((s + overhead) / step)), b["score"] * FORM_VALUE[f] * tb) for f, s in b["forms"].items()]
        new = dp[:] if b["id"] not in forced else [NEG] * (W + 1)
        ch = [None] * (W + 1)
        for w in range(W + 1):
            for f, c, v in opts:
                if c <= w and dp[w - c] > NEG and dp[w - c] + v > new[w]:
                    new[w] = dp[w - c] + v; ch[w] = (f, c)
        choice.append(ch); dp = new
    w = max(range(W + 1), key=lambda i: dp[i])
    picked = {}
    for b, ch in zip(reversed(order), reversed(choice)):
        if ch[w] is not None:
            f, c = ch[w]; picked[b["id"]] = f; w -= c
    # dependency repair
    changed = True
    while changed:
        changed = False
        for i in list(picked):
            for r in by_id[i].get("requires", []):
                if r in by_id and r not in picked:
                    picked[r] = "micro"; changed = True
        def secs():
            return sum(by_id[i]["forms"][f] + overhead for i, f in picked.items())
        while secs() > budget_s + 1e-6:
            needed = {r for i in picked for r in by_id[i].get("requires", [])}
            cand = [i for i in picked if i not in needed and i not in forced]
            if not cand: break
            drop = min(cand, key=lambda i: by_id[i]["score"] * FORM_VALUE[picked[i]])
            del picked[drop]
    sec = sum(by_id[i]["forms"][f] + overhead for i, f in picked.items())
    return {"ids": list(picked), "forms": picked, "seconds": sec,
            "value": sum(by_id[i]["score"] * FORM_VALUE[f] for i, f in picked.items())}


def unlimited(beats, floor=0):
    ids = [b["id"] for b in beats if b["score"] >= floor]
    by_id = {b["id"]: b for b in beats}
    return {"ids": ids, "forms": {i: "full" for i in ids}, "seconds": sum(by_id[i]["forms"]["full"] for i in ids),
            "value": sum(by_id[i]["score"] for i in ids)}


def coverage(sel, beats):
    """Importance-weighted coverage and tier recall for evaluation."""
    by_id = {b["id"]: b for b in beats}
    tot = sum(b["score"] for b in beats) or 1
    val = sum(by_id[i]["score"] * FORM_VALUE[sel["forms"].get(i, "full")] for i in sel["ids"])
    tiers = {}
    for t in TIER_RANK:
        all_t = [b["id"] for b in beats if b.get("tier") == t]
        if all_t:
            tiers[t] = round(sum(1 for i in all_t if i in sel["ids"]) / len(all_t), 3)
    dep_ok = all(r in sel["ids"] for i in sel["ids"] for r in by_id[i].get("requires", []) if r in by_id)
    return {"weighted_coverage": round(val / tot, 3), "tier_recall": tiers, "deps_satisfied": dep_ok,
            "n": len(sel["ids"]), "seconds": round(sel["seconds"], 1)}


def mckp_nested(beats, budgets, overhead=1.0, **kw):
    """Solve budgets in ascending order; every beat chosen for a shorter recap is FORCED into all longer
    ones (form may be upgraded). Guarantees nestedness: the 1-min recap is a strict subset of the 15-min one,
    so the user's 'duration slider' only ever adds context, never swaps it."""
    out, forced = {}, set()
    for B in sorted(budgets):
        sel = mckp(beats, B, overhead=overhead, forced=frozenset(forced), **kw)
        if not forced.issubset(sel["ids"]):   # infeasible -> keep previous selection, fill greedily
            sel = mckp(beats, B, overhead=overhead, **kw)
        out[B] = sel; forced |= set(sel["ids"])
    return out
