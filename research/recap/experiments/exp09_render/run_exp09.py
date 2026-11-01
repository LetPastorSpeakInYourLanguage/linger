"""exp09 — Four recap styles for Tears of Steel, end to end: select -> script (LLM) -> verify -> TTS -> render.

Styles (see recaplib.prompts.STYLE_CARDS): dramatic_comedic (2 min), short_direct (1 min),
fan_silent (~1.5 min, original-audio highlights + title cards), detailed_full (unlimited).
"""
import json, os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from recaplib import subs, select as S, prompts as P, render, video
from recaplib.llm import LLM, PendingLLM
HERE = os.path.dirname(os.path.abspath(__file__)); W = "/home/user/work/exp09"
SRC = "/home/user/data_untrusted/xiaotangii_tears-of-steel-dialogue-dataset/data/tears_raw.mp4"
SRT = "/home/user/data_untrusted/xiaotangii_tears-of-steel-dialogue-dataset/data/tears_of_steel.srt"
U = json.load(open("/home/user/wt/exp05-understanding-passes/research/recap/experiments/exp05_understanding/tos_understanding.json"))
cues = subs.load(SRT); beats = U["beats"]; by = {b["id"]: b for b in beats}
STYLES = {
    "short_direct": {"budget": 60, "hero": 0, "voice": "af_heart", "speed": 1.05},
    "dramatic_comedic": {"budget": 120, "hero": 25, "voice": "am_michael", "speed": 1.08},
    "fan_silent": {"budget": 90, "hero": 80, "voice": None, "speed": 1.0},
    "detailed_full": {"budget": None, "hero": 20, "voice": "bm_george", "speed": 1.0},
}
WPS = 2.6
sel_nested = S.mckp_nested(beats, [60, 90, 120], overhead=1.5)


def moments_text():
    rows = []
    for s in U["cards"][0]["scenes"]:
        for m in s.get("moments", []): rows.append(f"L{m['lines'][0]}-L{m['lines'][1]} | {m['what']} | {m['emotion']}/{m['intensity']}")
        for q in s.get("quotes", []): rows.append(f"L{q['line']}-L{q['line']} | quote: {cues[q['line']].text} | {q['why']}")
    return "\n".join(rows)


def main(render_now=True):
    llm = LLM(os.path.join(HERE, "llm_runs"))
    report = {}
    for style, cfg in STYLES.items():
        if cfg["budget"] is None:
            ids = [b["id"] for b in beats]; desc = "no time limit — cover every beat"; max_words = 900
        else:
            ids = sel_nested[cfg["budget"]]["ids"]; desc = f"{cfg['budget']} seconds total"
            max_words = int((cfg["budget"] - cfg["hero"]) * WPS)
        chosen = sorted(ids, key=lambda i: by[i]["t"])
        beat_txt = "\n".join(f"{i} | {by[i]['tier']} | L{by[i]['lines'][0]}-L{by[i]['lines'][1]} | {by[i]['text']}" for i in chosen)
        prompt = P.SCRIPT_USER.format(style_name=style, style_card=P.STYLE_CARDS[style], budget_desc=desc, wps=WPS, max_words=max_words,
                                      hero_seconds=cfg["hero"], logline=U["bible"]["logline"], beats=beat_txt, moments=moments_text())
        try:
            script = llm.complete_json(f"script_{style}", P.SCRIPT_SYSTEM, prompt)
        except PendingLLM as e:
            print("PENDING", e); continue
        words = sum(len(s["text"].split()) for s in script["segments"] if s["type"] == "narration")
        cited = {b for s in script["segments"] for b in s.get("beats", [])}
        report[style] = {"beats_selected": len(chosen), "segments": len(script["segments"]), "narration_words": words, "max_words": max_words,
                         "within_word_budget": words <= max_words * 1.05, "beats_cited": len(cited & set(chosen)),
                         "uncited_selected": sorted(set(chosen) - cited), "invented_beat_ids": sorted(cited - set(by))}
        if render_now:
            os.makedirs(W, exist_ok=True)
            tts = render.TTS(cfg["voice"] or "am_michael", cfg["speed"])
            mask, step = video.vad(video.extract_wav(SRC, "/home/user/work/tos/audio16k.wav"), 30, 3)
            shots = json.load(open("/home/user/work/tos/shots.json"))
            edl = render.plan(script["segments"], cues, shots, video.smooth_mask(mask, 5), step, tts, video.duration(SRC))
            report[style]["planned_open_loop_s"] = round(render.edl_duration(edl), 1)
            if cfg["budget"] and "--fit" in sys.argv:
                tier_rank = {"P0": -1, "P1": 1, "P2": 2, "P3": 3}
                def rank(seg):
                    ts = [by[b]["tier"] for b in seg.get("beats", []) if b in by]
                    return min([tier_rank[t] for t in ts] or [4]) if "P0" not in ts else -1
                edl, log = render.fit_to_budget(edl, cfg["budget"], lambda sp: render.TTS(cfg["voice"] or "am_michael", cfg["speed"] * sp),
                                                script["segments"], beat_rank=rank)
                report[style]["fit_log"] = log
            out = render.render(edl, SRC, os.path.join(W, f"tos_recap_{style}{'_fit' if '--fit' in sys.argv else ''}.mp4"), os.path.join(W, f"parts_{style}"))
            report[style]["duration_s"] = round(video.duration(out), 1)
            report[style]["target_s"] = cfg["budget"]
            json.dump(edl, open(os.path.join(HERE, f"edl_{style}.json"), "w"), indent=1)
        print(style, report[style])
    json.dump(report, open(os.path.join(HERE, "results_fit.json" if "--fit" in sys.argv else "results.json"), "w"), indent=1)


if __name__ == "__main__":
    main(render_now="--norender" not in sys.argv)
