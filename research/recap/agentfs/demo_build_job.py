"""Materialize a real example job from exp12 artifacts: recap_channel recap of Panic Room with a G2 script gate."""
import json, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agentfs as A
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "example_workspace")
E12 = os.path.join(HERE, "../experiments/exp12_recap_channel")
if not os.path.exists(E12): E12 = "/home/user/wt/exp12-recap-channel-narration/research/recap/experiments/exp12_recap_channel"
shutil.rmtree(ROOT, ignore_errors=True)
os.makedirs(os.path.join(ROOT, "library/panic_room"), exist_ok=True)
open(os.path.join(ROOT, "instructions.md"), "w").write("House style: present tense, cite line ids for every claim, never use knowledge from outside the subtitles.\n")
open(os.path.join(ROOT, "library/panic_room/instructions.md"), "w").write("Names in this copy are scrambled; never 'correct' them.\n")
job = A.new_job(ROOT, "2026-11-01-panic-room-recap", {"kind": "recap", "titles": ["panic_room"], "understanding": "CURRENT",
      "params": {"style": "recap_channel", "duration": "6m", "focus": "main", "spoilers": "full"}, "autonomy": "gates",
      "instructions": "Make the reluctant burglar sympathetic."})
open(os.path.join(job, "inbox/001-human.md"), "w").write("Mid-run note: less snark in the ending, please.")
A.add_step(job, "S4z_zoom_in", "Re-read cited lines of selected beats; harvest quotes/numbers/callbacks; flag corrections.", worker="Writer")
A.add_step(job, "S4_script", "Write recap_channel script from selection + details + instructions.", needs=["S4z_zoom_in"], worker="Writer")
A.add_step(job, "S4v_verify", "Fresh context: verify each segment against its cited lines.", needs=["S4_script"], worker="Verifier")
for step, src in (("S4z_zoom_in", "narrations/C_detail_harvest.json"), ("S4_script", "narrations/C_sul_plus_zoom.json"), ("S4v_verify", "manual_judgments.json")):
    s, d = A.claim(job, "demo-worker"); assert s == step, (s, step)
    A.complete(job, step, json.load(open(os.path.join(E12, src))), model="claude (in-session replay)")
J = json.load(open(os.path.join(E12, "manual_judgments.json")))["faithfulness_to_subtitles"]["C"]
metrics = {"unsupported": J["unsupported"], "partly": J["partly"], "leakage": 0, "est_duration_s": 361, "target_s": 360}
A.request_gate(job, "G2_script", "# G2 — script review\n" + "\n".join(f"[!] {i}" for i in J["issues"]), metrics,
               autopilot_rules=[lambda m: m["unsupported"] == 0, lambda m: m["leakage"] == 0, lambda m: abs(m["est_duration_s"] - m["target_s"]) <= 0.05 * m["target_s"]])
print("gate decision:", A.gate_decision(job, "G2_script"))
print("merged instructions:\n", A.instructions(ROOT, "panic_room", job))
for root, _, files in os.walk(ROOT):
    for f in files: print(os.path.relpath(os.path.join(root, f), ROOT))
