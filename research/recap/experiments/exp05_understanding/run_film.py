"""exp05b — multi-pass LLM understanding of a FULL feature film from subtitle-like dialogue only.

Film: Panic Room (TRIPOD test + MENSA): gold turning-point scenes AND gold salient scenes.
Input = dialogue only, no speaker names, no headings, no action lines; synthetic cue timings
(words/2.7s + 0.4s gap, no scene gaps -> no leakage of scene boundaries).
Contamination control: all character names are replaced by unrelated names before the LLM sees them.
Evaluation: map every beat (via cited line ids) to its gold screenplay scene, score scenes by
max(global_importance), compare to gold TP scenes and MENSA salient scenes, and to exp04-style baselines.
"""
import json, os, random, re, sys
import numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from recaplib import datasets as D, subs, pipeline
from recaplib.llm import LLM, PendingLLM
HERE = os.path.dirname(os.path.abspath(__file__))
MOVIE = sys.argv[1] if len(sys.argv) > 1 else "Panic Room"
FAKE = ["Nora", "Quentin", "Ida", "Bram", "Opal", "Felix", "Greta", "Hollis", "Vera", "Milo", "Tess", "Otto", "June", "Rufus", "Lena", "Cyril"]


def build():
    scenes = D.tripod_scenes(MOVIE)
    speakers = {}
    for s in scenes:
        for sp, _ in s["dialog"]:
            for tok in re.findall(r"[A-Z][a-z]+", sp.title()):
                speakers[tok] = speakers.get(tok, 0) + 1
    common = {"Man", "Woman", "Voice", "Cop", "Officer", "Guy", "Girl", "Boy", "Kid", "Driver", "Doctor", "Nurse", "Guard", "Old", "Young", "Mrs", "Mr", "The"}
    names = [n for n, c in sorted(speakers.items(), key=lambda x: -x[1]) if n not in common and c >= 3]
    rnd = random.Random(7); fake = FAKE[:]; rnd.shuffle(fake)
    scramble = {n: fake[i % len(fake)] for i, n in enumerate(names)}
    pat = re.compile(r"\b(" + "|".join(map(re.escape, scramble)) + r")\b") if scramble else None
    lines, owner, t = [], [], 5.0
    for s in scenes:
        for c in D.to_subtitle_lines(s["dialog"]):
            txt = pat.sub(lambda m: scramble[m.group(1)], c["text"]) if pat else c["text"]
            dur = max(1.2, len(txt.split()) / 2.7)
            lines.append({"start": t, "end": t + dur, "text": txt, "gold_speaker": scramble.get(c["speaker"].split()[0].title(), c["speaker"])})
            owner.append(s["idx"]); t += dur + 0.4
    return scenes, lines, owner, scramble


if __name__ == "__main__":
    scenes, lines, owner, scramble = build()
    cues = subs.from_lines(lines)
    run = os.path.join(HERE, "llm_runs", re.sub(r"\W", "_", MOVIE))
    os.makedirs(run, exist_ok=True)
    json.dump({"scramble": scramble, "owner": owner, "gold_speakers": [l["gold_speaker"] for l in lines]}, open(os.path.join(run, "meta.json"), "w"))
    llm = LLM(run)
    try:
        cards, roster, story = pipeline.run_p1(cues, llm, "an unknown feature film (names changed)", max_lines=160)
        bible = pipeline.run_p2(cards, llm, "an unknown feature film (names changed)")
        beats = pipeline.build_beats(cards, bible, cues)
        json.dump({"cards": cards, "bible": bible, "beats": beats, "calls": llm.calls}, open(os.path.join(run, "understanding.json"), "w"), indent=1)
        print("done", len(beats))
    except PendingLLM as e:
        print("PENDING", e)
