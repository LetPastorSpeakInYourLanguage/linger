"""exp06 — Duration-budgeted selection over the prioritized beat graph.

Inputs: beats from exp05 (Tears of Steel: 18 beats, Panic Room: 47 beats) with global importance,
tiers P0-P3, dependency edges ('requires') and three renderings each (full/short/micro).
Budgets: 30s .. 30min + unlimited. Algorithms: greedy_prefix (nested by construction), greedy_ratio, mckp.
Metrics: importance-weighted coverage, tier recall, turning-point recall, dependency satisfaction,
nestedness (is every beat chosen at budget b also chosen at the next larger budget?), budget use.
"""
import json, os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from recaplib import select as S
HERE = os.path.dirname(os.path.abspath(__file__))
U5 = "/home/user/wt/exp05-understanding-passes/research/recap/experiments/exp05_understanding"
SRC = {"tears_of_steel": f"{U5}/tos_understanding.json", "panic_room": f"{U5}/llm_runs/Panic_Room/understanding.json"}
BUDGETS = [30, 60, 120, 180, 300, 600, 900, 1800]
ALGOS = {"greedy_prefix": S.greedy_prefix, "strict_prefix": lambda b, B: S.greedy_prefix(b, B, strict_prefix=True),
         "greedy_ratio": S.greedy_ratio, "mckp": S.mckp, "mckp_ovh1.5": lambda b, B: S.mckp(b, B, overhead=1.5)}
NESTED_CACHE = {}
def mckp_nested(b, B):
    key = id(b)
    if key not in NESTED_CACHE: NESTED_CACHE[key] = S.mckp_nested(b, BUDGETS, overhead=1.5)
    return NESTED_CACHE[key][B]
ALGOS["mckp_nested_ovh1.5"] = mckp_nested


def main():
    out = {}
    for name, path in SRC.items():
        U = json.load(open(path)); beats = U["beats"]; tps = set(U["bible"]["turning_points"].values())
        total_full = sum(b["forms"]["full"] for b in beats)
        res = {"beats": len(beats), "full_narration_seconds_all_beats": round(total_full), "algos": {}}
        for an, fn in ALGOS.items():
            rows, prev = [], None
            nested = True
            for B in BUDGETS:
                sel = fn(beats, B)
                cov = S.coverage(sel, beats)
                cov["budget"] = B; cov["tp_recall"] = round(len(tps & set(sel["ids"])) / len(tps), 2)
                cov["use"] = round(sel["seconds"] / B, 2)
                cov["forms"] = {f: list(sel["forms"].values()).count(f) for f in ("full", "short", "micro")}
                if prev is not None and not set(prev).issubset(sel["ids"]): nested = False
                prev = sel["ids"]; rows.append(cov)
            res["algos"][an] = {"nested": nested, "rows": rows}
        u = S.unlimited(beats)
        res["unlimited"] = S.coverage(u, beats)
        # example ordered cut list for the 60s / 180s recaps (chronological playback order)
        by = {b["id"]: b for b in beats}
        for B in (60, 180):
            sel = S.mckp_nested(beats, BUDGETS, overhead=1.5)[B]
            res[f"mckp_{B}s_cutlist"] = [f"{by[i]['t']:.0f}s {sel['forms'][i]:5s} {by[i]['tier']} {by[i]['short']}" for i in sorted(sel["ids"], key=lambda i: by[i]["t"])]
        out[name] = res
    json.dump(out, open(os.path.join(HERE, "results.json"), "w"), indent=1)
    for name, r in out.items():
        print(f"\n== {name}: {r['beats']} beats, all-full narration {r['full_narration_seconds_all_beats']}s")
        print("budget  " + "  ".join(f"{a[:22]:>22s}" for a in ALGOS))
        for i, B in enumerate(BUDGETS):
            cells = []
            for a in ALGOS:
                x = r["algos"][a]["rows"][i]
                cells.append(f"{x['weighted_coverage']:.2f}/n{x['n']:2d}/P0 {x['tier_recall'].get('P0',0):.2f}")
            print(f"{B:5d}s  " + "  ".join(f"{c:>22s}" for c in cells))
        print("nested:", {a: r["algos"][a]["nested"] for a in ALGOS}, "deps ok:", {a: all(x["deps_satisfied"] for x in r["algos"][a]["rows"]) for a in ALGOS})
        print("60s cut list:", *r["mckp_60s_cutlist"], sep="\n   ")


if __name__ == "__main__":
    main()
