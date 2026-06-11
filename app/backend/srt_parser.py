"""Parse .srt / .vtt subtitle files into (start_s, end_s, text) tuples."""
import re

_TIME_RE = re.compile(r"(\d+):(\d{2}):(\d{2})[.,](\d{1,3})")
_SHORT_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})[.,](\d{1,3})")


def _to_seconds(ts: str):
    m = _TIME_RE.search(ts)
    if m:
        h, mi, s, ms = m.groups()
        return int(h) * 3600 + int(mi) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000
    m = _SHORT_TIME_RE.search(ts)
    if m:
        mi, s, ms = m.groups()
        return int(mi) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000
    return None


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)          # strip markup tags
    text = re.sub(r"\{[^}]+\}", "", text)        # strip ASS style blocks
    return " ".join(text.split()).strip()


def parse_subtitles(raw: str):
    """Returns list of dicts: {start_s, end_s, text}. Handles SRT and WebVTT."""
    raw = raw.replace("\r\n", "\n").replace("﻿", "")
    segments = []
    for block in re.split(r"\n\s*\n", raw):
        lines = [l for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        # find the timing line
        timing_idx = None
        for i, line in enumerate(lines):
            if "-->" in line:
                timing_idx = i
                break
        if timing_idx is None:
            continue
        parts = lines[timing_idx].split("-->")
        if len(parts) != 2:
            continue
        start = _to_seconds(parts[0])
        end = _to_seconds(parts[1])
        if start is None or end is None:
            continue
        text = _clean(" ".join(lines[timing_idx + 1:]))
        if text:
            segments.append({"start_s": start, "end_s": end, "text": text})
    segments.sort(key=lambda s: s["start_s"])
    return segments
