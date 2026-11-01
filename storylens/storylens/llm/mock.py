"""Offline mock LLM: deterministic heuristics that return schema-valid answers for every pass.
Quality is intentionally basic — it exists so the whole app (UI, jobs, gates, lenses, render) runs and is testable
without an API key. Use llm_backend = anthropic (or folder + an agent) for real understanding."""
from __future__ import annotations
import re
from collections import Counter

STOP = set("The This That What When Where Why How You Your Yeah Okay Well Now Then There They She His Her Him And But Not Yes Hey "
           "Come Look Just Oh Let God Sorry Thank Thanks Please Good Right Great Wait Listen Know Here All Don Can Did Does Who It We I "
           "Is Are Was No So If In On At To Of For With My Me Our Its Mr Mrs Miss".split())
ACT_WORDS = [("sorry", "apologizes"), ("thank", "thanks"), ("help", "helps"), ("love", "confesses"), ("promise", "decides"),
             ("lie", "lies"), ("kill", "threatens"), ("gift", "gifts"), ("here, take", "gifts"), ("don't worry", "comforts"),
             ("you'll be okay", "comforts"), ("leave", "leaves"), ("found", "discovers"), ("secret", "reveals"), ("plan", "plans"),
             ("no!", "refuses"), ("stop", "defends"), ("haha", "jokes"), ("joke", "jokes")]
TRAIT_MAP = {"friend": ["helps", "comforts", "defends", "gifts", "encourages", "protects", "sacrifices"],
             "kind": ["helps", "comforts", "gifts", "thanks", "forgives"], "help": ["helps", "rescues", "protects"],
             "lie": ["lies", "deceives"], "betray": ["betrays", "lies"], "brave": ["defends", "protects", "rescues", "sacrifices"],
             "funny": ["jokes", "teases"], "love": ["confesses", "kisses", "flirts"], "angry": ["argues", "threatens", "attacks"]}


TOPIC_WORDS = ["meaning", "life", "purpose", "responsibility", "suffering", "marriage", "wife", "husband", "women", "love", "money", "death",
               "faith", "god", "grace", "truth", "debt", "friend", "family", "work", "fear", "hope", "freedom", "power"]


def _topics(text):
    low = text.lower()
    return [w for w in TOPIC_WORDS if re.search(r"\b" + w, low)][:4]


def _names(texts):
    c = Counter(w for t in texts for w in re.findall(r"\b([A-Z][a-z]{2,})\b", t) if w not in STOP)
    return [w for w, n in c.most_common(12) if n >= 2]


class MockBackend:
    name = "mock"

    def __init__(self, settings): self.s = settings

    def complete(self, call):
        t, h = call.task, call.hint or {}
        for prefix, fn in (("vision", self.vision), ("cards", self.cards), ("integrate", self.integrate), ("causal", self.causal),
                           ("lens-character", self.character), ("lens-trait-map", self.trait_map), ("lens-trait-check", self.trait_check),
                           ("lens-topic-map", self.topic_map), ("lens-topic-check", self.topic_check),
                           ("zoom", self.zoom), ("script", self.script), ("verify", self.verify)):
            if t.startswith(prefix): return fn(h), {"input_tokens": len(call.prompt) // 4, "output_tokens": 0}
        raise ValueError(f"mock: unknown task {t}")

    def vision(self, h):
        return {"events": [{"text": "a wordless stretch: the action continues on screen", "kind": "action", "who": []}],
                "onscreen_text": "", "setting": "", "is_credits": False}

    def cards(self, h):
        cues, cid = h["cues"], h["chunk_id"]
        names = _names([c["text"] for c in cues] + [c.get("speaker_label") or "" for c in cues])
        groups, cur = [], [cues[0]]
        for a, b in zip(cues, cues[1:]):
            if b["start"] - a["end"] > 4.0 or len(cur) >= 14: groups.append(cur); cur = [b]
            else: cur.append(b)
        groups.append(cur)
        scenes, bn, fn = [], 0, 0
        for k, g in enumerate(groups):
            spk = [{"line": c["idx"], "name": c.get("speaker_label") or "?"} for c in g]
            chars = sorted({s["name"] for s in spk if s["name"] != "?"} | {n for n in names if any(n in c["text"] for c in g)})
            longest = max(g, key=lambda c: len(c["text"]))
            beats, facts = [], []
            bn += 1; bid = f"{cid}-b{bn}"
            who = chars[:3]
            beats.append({"id": bid, "text": f"{' and '.join(who) or 'Someone'}: \"{longest['text'][:90]}\"", "lines": [g[0]["idx"], g[-1]["idx"]],
                          "kind": "plot", "local_importance": min(5, 2 + len(g) // 5), "emotion": "tense" if "!" in longest["text"] else "neutral",
                          "intensity": min(3, sum(c["text"].count("!") for c in g)), "who": who})
            for c in g:
                low = c["text"].lower(); actor = c.get("speaker_label") or "?"
                for w, act in ACT_WORDS:
                    if w in low:
                        fn += 1
                        target = next((n for n in names if n in c["text"] and n != actor), "")
                        facts.append({"id": f"{cid}-f{fn}", "kind": "act", "actor": actor, "act_type": act, "target": target, "cost": 1,
                                      "field": "", "value": "", "text": f"{actor} {act} {target}: \"{c['text'][:80]}\"".replace("  ", " "),
                                      "lines": [c["idx"], c["idx"]], "intensity": 1 + ("!" in c["text"]), "beat_id": bid,
                                      "topics": _topics(c["text"]), "stance": ""})
                        break
                if c.get("sdh", {}).get("humor"):
                    fn += 1
                    facts.append({"id": f"{cid}-f{fn}", "kind": "joke", "actor": actor, "act_type": "jokes", "target": "", "cost": 0, "field": "",
                                  "value": c["text"], "text": f"laughter: \"{c['text'][:80]}\"", "lines": [c["idx"], c["idx"]], "intensity": 1, "beat_id": bid,
                                  "topics": [], "stance": ""})
            fn += 1
            facts.append({"id": f"{cid}-f{fn}", "kind": "moment", "actor": who[0] if who else "", "act_type": "", "target": "", "cost": 0,
                          "field": "", "value": "", "text": longest["text"][:100], "lines": [longest["idx"], longest["idx"]],
                          "intensity": min(3, 1 + longest["text"].count("!")), "beat_id": bid, "topics": _topics(longest["text"]), "stance": ""})
            for c in g:   # discourse-style claims: every substantial line becomes a claim with naive topics
                if len(c["text"].split()) >= 9:
                    fn += 1
                    facts.append({"id": f"{cid}-f{fn}", "kind": "claim", "actor": c.get("speaker_label") or "?", "act_type": "asserts", "target": "",
                                  "cost": 0, "field": "", "value": c["text"][:120], "text": c["text"][:140], "lines": [c["idx"], c["idx"]],
                                  "intensity": 1, "beat_id": bid, "topics": _topics(c["text"]), "stance": ""})
            scenes.append({"id": f"{cid}-s{k + 1}", "lines": [g[0]["idx"], g[-1]["idx"]], "setting": "", "characters": chars, "speakers": spk,
                           "summary": " ".join(c["text"] for c in g)[:240], "beats": beats, "facts": facts})
        return {"roster_updates": [{"name": n, "aliases": [], "who": "character"} for n in names],
                "scenes": scenes, "story_so_far": " ".join(s["summary"][:60] for s in scenes)[-600:]}

    def integrate(self, h):
        beats = h["beats"]; n = len(beats)
        order = sorted(beats, key=lambda b: -(b["local_importance"] * 18 + b["intensity"] * 3))
        tier = {}
        for i, b in enumerate(order):
            q = i / max(1, n); tier[b["id"]] = "P0" if q < 0.1 else "P1" if q < 0.35 else "P2" if q < 0.7 else "P3"
        tps = [("TP1_opportunity", .1), ("TP2_change_of_plans", .25), ("TP3_point_of_no_return", .5), ("TP4_major_setback", .75), ("TP5_climax", .95)]
        return {"logline": beats[0]["text"] if beats else "", "genre_tone": "unknown (mock)",
                "characters": [{"name": r["name"], "aliases": r.get("aliases", []), "role": "protagonist" if i == 0 else "supporting",
                                "arc": "", "importance": max(10, 90 - 10 * i)} for i, r in enumerate(h.get("roster", [])[:15])],
                "threads": [{"id": "T1", "title": "Main story", "summary": "", "importance": 100, "beats": [b["id"] for b in beats]}],
                "turning_points": [{"tp": k, "beat_id": beats[min(n - 1, int(q * n))]["id"]} for k, q in tps] if beats else [],
                "beats": [{"id": b["id"], "global_importance": min(100, b["local_importance"] * 18 + b["intensity"] * 3), "tier": tier[b["id"]],
                           "requires": [], "pays_off": [], "thread": "T1", "short": b["text"][:60], "spoiler_level": 1} for b in beats],
                "themes": []}

    def causal(self, h):
        return {"links": [{"beat_id": b["id"], "caused_by": b["who"][:1], "revealed_by": [], "witnessed_by": b["who"][1:], "evidence_facts": []} for b in h["beats"]]}

    def character(self, h):
        items = h["items"]
        return {"summary": f"The story of {h['name']} (mock).", "arc": "", "hidden_gems": [],
                "items": [{"ref": i["ref"], "salience": min(100, 40 + 20 * (i.get("intensity") or 0)), "tier": "P1" if (i.get("intensity") or 0) >= 2 else "P2",
                           "role": i.get("role", ""), "why": ""} for i in items]}

    def trait_map(self, h):
        q = h["query"].lower(); acts = sorted({a for k, v in TRAIT_MAP.items() if k in q for a in v})
        return {"description": f"moments matching: {h['query']}", "act_types": acts or ["helps", "comforts", "defends"],
                "keywords": [w for w in re.findall(r"[a-z]{4,}", q)][:8], "actor_required": bool(h.get("actor"))}

    def trait_check(self, h):
        return {"checks": [{"ref": i["ref"], "match": i.get("act_type", "") not in ("", "jokes") or i["type"] == "beat", "strength": 2, "why": "mock"} for i in h["items"]]}

    def topic_map(self, h):
        words = [w for w in re.findall(r"[a-z]{4,}", h["query"].lower()) if w not in ("what", "said", "says", "about", "does", "think")]
        return {"description": f"statements about {h['query']}", "topics": words[:3], "keywords": words[:10], "speakers": [h["speaker"]] if h.get("speaker") else []}

    def topic_check(self, h):
        out = []
        for i in h["items"]:
            words = set(re.findall(r"[a-z]{4,}", h["query"].lower()))
            rel = bool(words & set(re.findall(r"[a-z]{4,}", (i.get("text", "") + " " + " ".join(i.get("topics", []))).lower())))
            out.append({"ref": i["ref"], "relevant": rel, "speaker": i.get("actor") or h.get("speaker") or "?", "speaker_confident": False,
                        "claim": i.get("text", "")[:140], "stance": "", "strength": 2 if rel else 0, "first_line": i["lines"][0], "last_line": i["lines"][1]})
        return {"checks": out}

    def zoom(self, h):
        return {"details": [{"ref": i["ref"], "detail": i["text"][:80], "line": i["lines"][0]} for i in h["items"]], "corrections": []}

    def script(self, h):
        segs, style = [], h["style"]
        for i, it in enumerate(h["items"]):
            if style not in ("fan_silent", "clips"):
                segs.append({"type": "narration", "text": f"{'Then' if i else 'It begins when'} {it['text'].rstrip('.')}.", "refs": [it["ref"]],
                             "media": it["media"], "lines": list(it["lines"]), "mood": "neutral"})
            if style in ("fan_silent", "compilation", "clips") or (it["tier"] == "P0" and style not in ("short_direct",)):
                segs.append({"type": "hero_clip", "text": "", "refs": [it["ref"]], "media": it["media"],
                             "lines": [it["lines"][0], min(it["lines"][1], it["lines"][0] + 2)], "mood": "neutral"})
        return {"title": f"Recap ({style}, mock)", "segments": segs}

    def verify(self, h):
        return {"checks": [{"index": i, "verdict": "supported", "issue": "", "fix": ""} for i, s in enumerate(h["segments"]) if s["type"] != "hero_clip"],
                "leakage": []}
