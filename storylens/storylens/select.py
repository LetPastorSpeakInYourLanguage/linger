"""Duration-budgeted, NESTED selection over view items (research exp06).

Each item can be told in three forms — full / short / micro — with different durations and value. A multiple-choice
knapsack picks forms to maximise salience under the time budget, dependency closure keeps short recaps coherent,
and solving budgets in ascending order with forced inclusion guarantees nestedness: the 1-minute recap is always a
subset of the 5-minute one (the duration slider only ever adds context)."""
from __future__ import annotations
import math

TIER_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
FORM_VALUE = {"full": 1.0, "short": 0.65, "micro": 0.35}
TIER_BONUS = (1.6, 1.25, 1.0, 0.8)


def forms(text, wps=2.6, min_visual=2.0):
    w = max(8, int(len(text.split()) * 1.6))
    return {"full": max(w / wps, min_visual) + 0.6, "short": max(w * 0.45 / wps, min_visual) + 0.4, "micro": max(w * 0.2 / wps, 1.2)}


def mckp(items, budget, overhead=1.5, step=0.5, forced=frozenset()):
    by = {i["ref"]: i for i in items}
    order = sorted(items, key=lambda i: (i["media"], i["t0"]))
    W = int(budget / step); NEG = -1e18
    dp = [0.0] + [NEG] * W; choice = []
    for it in order:
        tb = TIER_BONUS[TIER_RANK.get(it["tier"], 3)]
        opts = [(f, int(math.ceil((s + overhead) / step)), it["salience"] * FORM_VALUE[f] * tb) for f, s in it["forms"].items()]
        new = dp[:] if it["ref"] not in forced else [NEG] * (W + 1); ch = [None] * (W + 1)
        for w in range(W + 1):
            for f, c, v in opts:
                if c <= w and dp[w - c] > NEG and dp[w - c] + v > new[w]: new[w] = dp[w - c] + v; ch[w] = (f, c)
        choice.append(ch); dp = new
    w = max(range(W + 1), key=lambda i: dp[i]); picked = {}
    for it, ch in zip(reversed(order), reversed(choice)):
        if ch[w] is not None: f, c = ch[w]; picked[it["ref"]] = f; w -= c
    changed = True
    while changed:   # dependency repair
        changed = False
        for r in list(picked):
            for d in by[r].get("requires", []):
                if d in by and d not in picked: picked[d] = "micro"; changed = True
        def secs(): return sum(by[r]["forms"][f] + overhead for r, f in picked.items())
        while secs() > budget + 1e-6:
            needed = {d for r in picked for d in by[r].get("requires", [])}
            cand = [r for r in picked if r not in needed and r not in forced]
            if not cand: break
            del picked[min(cand, key=lambda r: by[r]["salience"] * FORM_VALUE[picked[r]])]
    return picked


def select(items, budget_seconds, wps=2.6, ladder=(60, 180, 300, 600, 900, 1800, 3600)):
    """budget_seconds <= 0 -> unlimited (everything, full form). Returns items with chosen 'form', chronological."""
    for it in items: it["forms"] = forms(it.get("text", ""), wps)
    if not budget_seconds or budget_seconds <= 0:
        return [dict(it, form="full") for it in sorted(items, key=lambda i: (i["media"], i["t0"]))]
    forced, picked = set(), {}
    for B in sorted({b for b in ladder if b < budget_seconds} | {budget_seconds}):
        p = mckp(items, B, forced=frozenset(forced))
        if not forced.issubset(p): p = mckp(items, B)
        picked = p; forced |= set(p)
    by = {i["ref"]: i for i in items}
    return [dict(by[r], form=f) for r, f in sorted(picked.items(), key=lambda kv: (by[kv[0]]["media"], by[kv[0]]["t0"]))]
