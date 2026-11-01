import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from recaplib import subs, select as S


def test_sdh_parsing():
    c = subs.parse_text(0, 0, 1, "- [laughs] JOHN: Get down!\n- (gunshot) No!")
    assert c.text == "Get down! No!" and c.speaker_label == "John" and c.turns == 2
    assert c.sdh == {"humor": 1, "violence": 1}
    m = subs.parse_text(1, 0, 1, "<i>♪ Hold me closer ♪</i>")
    assert m.music and m.italic and m.sdh.get("music")


def test_utterance_merge():
    cs = [subs.parse_text(0, 0, 1, "you have your robotics, and I"), subs.parse_text(1, 1.2, 2, "...just want space."),
          subs.parse_text(2, 5, 6, "Whatever.")]
    assert subs.merge_utterances(cs) == [[0, 1], [2]]


def _beats():
    bs = []
    for i in range(30):
        tier = ["P0", "P1", "P2", "P3"][i % 4]
        bs.append({"id": f"b{i}", "t": i, "score": 100 - i * 2, "tier": tier, "requires": [f"b{i-4}"] if i >= 4 and i % 4 == 0 else [],
                   "forms": S.default_forms(12 + i % 5)})
    return bs


def test_nested_mckp_is_nested_and_respects_budget_and_deps():
    bs = _beats(); budgets = [30, 60, 120, 300]
    out = S.mckp_nested(bs, budgets, overhead=1.5)
    by = {b["id"]: b for b in bs}
    prev = set()
    for B in budgets:
        sel = out[B]
        assert prev.issubset(sel["ids"])
        assert sel["seconds"] <= B + 1e-6
        assert all(r in sel["ids"] for i in sel["ids"] for r in by[i]["requires"])
        prev = set(sel["ids"])


def test_greedy_closure_includes_dependencies():
    bs = _beats(); sel = S.greedy_prefix(bs, 60)
    by = {b["id"]: b for b in bs}
    assert all(r in sel["ids"] for i in sel["ids"] for r in by[i]["requires"])
