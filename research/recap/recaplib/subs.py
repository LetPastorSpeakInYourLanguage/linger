"""Subtitle ingestion: parse any SRT/VTT/ASS, extract SDH signals, merge cues into utterances.

Language-agnostic by design: only the *English subtitle text and its timings* are used for
meaning; nothing here depends on the spoken language of the media.

SDH (subtitles for the deaf & hard of hearing) carry free annotations that are gold for
understanding & highlight detection:
  [laughs] (LAUGHTER) [audience laughing]   -> humor / reaction beat
  ♪ ... ♪  [music] [ominous music]          -> music, montage, mood
  [gunshot] [explosion] [screams] (sobbing) -> action / emotional intensity
  JOHN: / [John] / (MAN) prefix             -> speaker label
  - line one\n- line two                     -> two speakers inside one cue
  <i>...</i>                                 -> off-screen / voice-over / phone / narrator
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field, asdict

TAG_RE = re.compile(r"[\[\(]([^\]\)]{1,60})[\]\)]")
SPEAKER_RE = re.compile(r"^\s*(?:-\s*)?([A-Z][A-Z0-9 .'\-]{1,24}|[A-Z][a-z]+(?: [A-Z][a-z]+)?)\s*:\s+")
MUSIC_RE = re.compile(r"[♪♫#]")
HTML_RE = re.compile(r"<[^>]+>|\{\\[^}]*\}")

SDH_LEXICON = {
    "humor": ["laugh", "chuckl", "giggl", "snicker", "laughter", "guffaw"],
    "music": ["music", "song", "singing", "sings", "humming", "hums", "tune", "♪", "melody", "orchestra"],
    "cry": ["sob", "cries", "crying", "weep", "sniffl", "whimper", "tearful"],
    "scream": ["scream", "shriek", "yell", "shout", "gasp", "panting", "groan", "grunt"],
    "violence": ["gunshot", "gunfire", "shot", "explosion", "explod", "punch", "crash", "thud", "slam", "fight", "siren", "blast", "bang"],
    "romance": ["kiss", "moan", "sigh"],
    "tension": ["ominous", "suspense", "tense", "dramatic", "heartbeat", "thunder", "rumbl", "eerie"],
    "phone": ["phone", "ring", "buzz", "beep", "voicemail", "radio", "static"],
}


@dataclass
class Cue:
    idx: int
    start: float
    end: float
    raw: str
    text: str = ""              # dialogue text with SDH tags removed
    tags: list = field(default_factory=list)      # raw SDH tags e.g. ["laughs"]
    sdh: dict = field(default_factory=dict)       # category -> count
    speaker_label: str | None = None             # explicit "JOHN:" label if present
    turns: int = 1                                # dialog dash turns inside cue
    italic: bool = False                          # off-screen / VO hint
    music: bool = False

    def dict(self):
        return asdict(self)


def classify_tag(tag: str) -> list[str]:
    t = tag.lower()
    return [cat for cat, keys in SDH_LEXICON.items() if any(k in t for k in keys)]


def parse_text(idx, start, end, raw) -> Cue:
    c = Cue(idx, start, end, raw)
    c.italic = "<i>" in raw.lower() or "{\\i1}" in raw
    s = HTML_RE.sub("", raw).replace("\\N", "\n")
    c.music = bool(MUSIC_RE.search(s))
    c.tags = [t.strip() for t in TAG_RE.findall(s)]
    s = TAG_RE.sub(" ", s)
    lines = [l.strip() for l in s.split("\n") if l.strip()]
    c.turns = max(1, sum(1 for l in lines if l.startswith("-")))
    out = []
    for l in lines:
        m = SPEAKER_RE.match(l)
        if m and not l.isupper():  # "JOHN: hi" ok; an all-caps shout line is not a label
            c.speaker_label = c.speaker_label or m.group(1).strip().title()
            l = l[m.end():]
        out.append(l.lstrip("- ").strip())
    text = " ".join(x for x in out if x)
    text = MUSIC_RE.sub("", text).strip()
    c.text = re.sub(r"\s+", " ", text)
    for t in c.tags + (["♪"] if c.music else []):
        for cat in classify_tag(t):
            c.sdh[cat] = c.sdh.get(cat, 0) + 1
    return c


def load(path: str, encoding=None) -> list[Cue]:
    import pysubs2
    subs = pysubs2.load(path, encoding=encoding or "utf-8-sig")
    cues = []
    for i, ev in enumerate(e for e in subs if not e.is_comment):
        cues.append(parse_text(i, ev.start / 1000.0, ev.end / 1000.0, ev.text))
    return cues


def from_lines(lines, start_key="start", end_key="end", text_key="text") -> list[Cue]:
    return [parse_text(i, d.get(start_key, i * 3.0), d.get(end_key, i * 3.0 + 2.5), d[text_key]) for i, d in enumerate(lines)]


def merge_utterances(cues: list[Cue], max_gap=0.6) -> list[list[int]]:
    """Group cues split mid-sentence ("...and I" / "...by these claws") into utterances."""
    groups, cur = [], []
    for c in cues:
        if not c.text:
            if cur: groups.append(cur); cur = []
            groups.append([c.idx]); continue
        if cur:
            prev = cues[cur[-1]]
            cont = (prev.text.endswith(("...", ",", "-", "—")) and not prev.text.endswith("--")) or c.text.startswith(("...", "…")) \
                or (prev.text and prev.text[-1].isalpha() and c.text[:1].islower())
            if cont and c.start - prev.end <= max_gap and c.turns == 1:
                cur.append(c.idx); continue
            groups.append(cur)
        cur = [c.idx]
    if cur: groups.append(cur)
    return groups


def to_prompt_lines(cues: list[Cue], speakers: dict | None = None) -> str:
    """Compact, LLM-friendly transcript: one line per cue with id + mm:ss + SDH + text.

    Line ids let the LLM cite evidence ("L123-L130") which we map back to exact time ranges.
    """
    out = []
    for c in cues:
        tags = (" [" + ",".join(c.tags) + "]") if c.tags else ""
        mus = " ♪" if c.music else ""
        sp = ""
        if speakers and c.idx in speakers: sp = f" {speakers[c.idx]}:"
        elif c.speaker_label: sp = f" {c.speaker_label}:"
        vo = " (i)" if c.italic else ""
        m, s = divmod(int(c.start), 60)
        out.append(f"L{c.idx} {m:02d}:{s:02d}{tags}{mus}{vo}{sp} {c.text}".rstrip())
    return "\n".join(out)


def sdh_profile(cues: list[Cue]) -> dict:
    prof = {}
    for c in cues:
        for k, v in c.sdh.items():
            prof[k] = prof.get(k, 0) + v
    prof["has_sdh"] = any(c.tags or c.music for c in cues)
    prof["speaker_labels"] = sum(1 for c in cues if c.speaker_label)
    return prof
