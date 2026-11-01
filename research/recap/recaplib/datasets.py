"""Loaders for research datasets (all text, downloaded from GitHub):
  Friends (emorynlp/character-mining): 10 seasons, scenes, speakers, some human scene plot summaries, QA.
  TRIPOD (ppapalampidi/TRIPOD): 99 screenplays + Wikipedia synopses with turning points; test set has
          gold turning-point SCENE indices.
  MENSA (saxenarohit/select_summ): gold alignments of Wikipedia summary sentences -> salient scenes.
Screenplays/transcripts are converted to *subtitle-like* input (dialogue only, no speaker names,
no scene headings, no action lines) to mimic what we get from an .srt file.
"""
from __future__ import annotations
import ast, csv, glob, json, os, re
from . import DATA

FRIENDS = os.path.join(DATA, "emorynlp_character-mining/json")
TRIPOD = os.path.join(DATA, "ppapalampidi_TRIPOD")
MENSA = os.path.join(DATA, "saxenarohit_select_summ/unz/alignment")


def friends_season(n: int):
    d = json.load(open(os.path.join(FRIENDS, f"friends_season_{n:02d}.json")))
    eps = []
    for ep in d["episodes"]:
        utts, plots, qas = [], {}, []
        for sc in ep["scenes"]:
            if sc.get("plots"):
                plots[sc["scene_id"]] = sc["plots"]
            for u in sc["utterances"]:
                sp = u["speakers"]
                if isinstance(sp, str):
                    try: sp = ast.literal_eval(sp)
                    except Exception: sp = [sp]
                if not u["transcript"].strip():
                    continue
                utts.append({"id": u["utterance_id"], "scene": sc["scene_id"], "speakers": sp, "text": u["transcript"]})
            for q in (sc.get("span_qa") or []):
                qas.append({"scene": sc["scene_id"], **q})
        eps.append({"id": ep["episode_id"], "utterances": utts, "plots": plots, "qa": qas})
    return eps


SPEAKER_LINE = re.compile(r"^[A-Z][A-Z0-9 .'\-&]{1,30}(\s*\(.*\))?$")
TRANSITION = re.compile(r"(CUT TO|FADE|DISSOLVE|SMASH|MATCH CUT|INTERCUT|CONTINUED|THE END|BACK TO|TITLE|SUPER)", re.I)
HEADING = re.compile(r"\b(INT\.|EXT\.|INT/EXT\.|EXT\./INT\.|INT\./EXT\.)")


def tripod_scenes(movie: str):
    """Segment like TRIPOD's official script, then split each scene into dialogue/action."""
    path = os.path.join(TRIPOD, "Screenplays_and_imdb_meta", movie, f"{movie}_script.txt")
    scenes, cur, flag = [], None, False
    for line in open(path, errors="ignore"):
        toks = re.sub(" +", " ", line).split()
        if any(t in toks for t in ("INT.", "EXT.", "INT/EXT.", "EXT./INT.", "INT./EXT.")):
            flag = True
            if cur is not None: scenes.append(cur)
            cur = [line.rstrip("\n")]
        elif flag:
            cur.append(line.rstrip("\n"))
    if cur is not None: scenes.append(cur)
    out = []
    for i, lines in enumerate(scenes):
        dialog, action, speaker, buf = [], [], None, []
        def flush():
            nonlocal buf, speaker
            if speaker and buf:
                txt = re.sub(r"\([^)]*\)", " ", " ".join(buf))
                txt = re.sub(r"\s+", " ", txt).strip()
                if txt: dialog.append((speaker, txt))
            buf, speaker = [], None
        for ln in lines[1:]:
            s = ln.strip()
            if not s:
                flush(); continue
            if SPEAKER_LINE.match(s) and not TRANSITION.search(s) and not HEADING.search(s) and len(s.split()) <= 5:
                flush(); speaker = re.sub(r"\s*\(.*\)", "", s).strip().title(); continue
            if speaker is not None:
                buf.append(s)
            else:
                action.append(s)
        flush()
        out.append({"idx": i, "heading": lines[0].strip(), "dialog": dialog, "action": " ".join(action)})
    return out


def tripod_tp_test():
    rows = {}
    with open(os.path.join(TRIPOD, "Synopses_and_annotations", "TRIPOD_screenplays_test.csv")) as f:
        for r in csv.DictReader(f):
            rows[r["movie_name"]] = [ast.literal_eval(r[f"tp{i}"]) if r.get(f"tp{i}") else [] for i in range(1, 6)]
    return rows


def mensa_alignment(movie_underscored: str):
    for split in ("test", "val"):
        p = os.path.join(MENSA, split, movie_underscored + ".json")
        if os.path.exists(p):
            d = json.load(open(p))
            sal = sorted(int(k.replace("scene", "")) for k, v in d["scene"].items() if v is not None)
            return {"num_scenes": d["num_scenes"], "salient": sal, "summary_map": d["summary"]}
    return None


def to_subtitle_lines(dialog, max_chars=84):
    """Split dialogue turns into subtitle-sized cues (<=2 lines x 42 chars), dropping speaker names."""
    cues = []
    for sp, txt in dialog:
        sents = re.split(r"(?<=[.!?])\s+", txt)
        buf = ""
        for s in sents:
            if buf and len(buf) + 1 + len(s) > max_chars:
                cues.append({"text": buf, "speaker": sp}); buf = s
            else:
                buf = (buf + " " + s).strip()
        if buf: cues.append({"text": buf, "speaker": sp})
    return cues
