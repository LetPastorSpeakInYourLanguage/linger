"""exp05a — full multi-pass understanding of Tears of Steel from its English SRT (replay LLM protocol)."""
import json, os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from recaplib import subs, pipeline
from recaplib.llm import LLM, PendingLLM
HERE = os.path.dirname(os.path.abspath(__file__))
SRT = "/home/user/data_untrusted/xiaotangii_tears-of-steel-dialogue-dataset/data/tears_of_steel.srt"
cues = subs.load(SRT)
llm = LLM(os.path.join(HERE, "llm_runs/tos"))
try:
    cards, roster, story = pipeline.run_p1(cues, llm, "Tears of Steel (short film, 12 min)")
    bible = pipeline.run_p2(cards, llm, "Tears of Steel (short film, 12 min)")
    beats = pipeline.build_beats(cards, bible, cues)
    json.dump({"cards": cards, "bible": bible, "beats": beats, "calls": llm.calls}, open(os.path.join(HERE, "tos_understanding.json"), "w"), indent=1)
    print("done", len(beats), "beats")
except PendingLLM as e:
    print("PENDING", e)
