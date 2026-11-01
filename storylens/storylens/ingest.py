"""T0 evidence: subtitles -> cues.jsonl (with SDH tags, line ids); optional media analysis.

Language-agnostic by design: meaning comes from the English subtitle text; the audio is only used through
voice activity (re-sync, cut points) — never through speech recognition of the spoken language.
"""
from __future__ import annotations
from pathlib import Path
from . import subs as S, media as M
from .util import write_jsonl, write_json, read_json, read_jsonl


def ingest_media(ws, tid, m, log=print, analyze_video=True, resync=True):
    ed = ws.edir(tid, m["id"]); ed.mkdir(parents=True, exist_ok=True)
    info = {"id": m["id"], "label": m.get("label"), "video": m.get("video"), "subs_source": m.get("subs")}
    sub_path = m.get("subs")
    if m.get("video") and M.have_ffmpeg():
        try:
            info.update(M.probe(m["video"]))
        except Exception as e:
            log(f"[{m['id']}] ffprobe failed: {e}")
        if not sub_path:
            out = ed / "extracted.srt"
            if M.extract_soft_subs(m["video"], out):
                sub_path = str(out); info["subs_source"] = "embedded"; log(f"[{m['id']}] extracted embedded subtitles")
    if not sub_path:
        raise RuntimeError(f"{m.get('label')}: no subtitle file and no embedded text subtitles found. "
                           "Add an .srt/.vtt/.ass (English) next to the video. (Burned-in subtitles need OCR — see docs/METHODOLOGY.md.)")
    cues = S.load(sub_path)
    if not cues: raise RuntimeError(f"{sub_path}: no cues parsed")
    from .workspace import profile
    avg_words = sum(len(c.text.split()) for c in cues) / len(cues)
    if profile(ws.title(tid)) == "discourse" or avg_words < 5:
        n0 = len(cues); cues = S.merge_fragments(cues)
        if len(cues) < n0: log(f"[{m['id']}] merged {n0} caption fragments into {len(cues)} cues")
    info["cues"] = len(cues); info["sdh"] = S.sdh_profile(cues)
    # optional: speech activity + re-sync (subtitles from another release are often offset or fps-stretched)
    if m.get("video") and M.have_ffmpeg() and resync and M.silero_available():
        try:
            wav = M.extract_wav(m["video"], ed / "audio16k.wav")
            prob, step = M.speech_probability(wav, Path(ws.root) / ".models")
            scale, off, corr = M.resync(cues, prob, step)
            info["resync"] = {"scale": scale, "offset": off, "corr": round(corr, 3)}
            if corr > 0.15 and (abs(off) > 0.3 or scale != 1.0):
                for c in cues: c.start, c.end = c.start * scale + off, c.end * scale + off
                log(f"[{m['id']}] re-synced subtitles: scale {scale:.5f}, offset {off:+.2f}s (corr {corr:.2f})")
            write_json(ed / "speech.json", {"step": step, "prob": [round(float(p), 2) for p in prob]})
        except Exception as e:
            log(f"[{m['id']}] VAD/re-sync skipped: {e}")
    write_jsonl(ed / "cues.jsonl", S.to_rows(cues))
    if m.get("video") and M.have_ffmpeg() and analyze_video and not (ed / "shots.json").exists():
        log(f"[{m['id']}] detecting shots…")
        try: write_json(ed / "shots.json", M.shots(m["video"]))
        except Exception as e: log(f"[{m['id']}] shot detection skipped: {e}")
    write_json(ed / "media.json", info)
    log(f"[{m['id']}] {len(cues)} cues ingested")
    return info


def cues(ws, tid, mid):
    return S.from_rows(read_jsonl(ws.edir(tid, mid) / "cues.jsonl"))


def media_info(ws, tid, mid):
    return read_json(ws.edir(tid, mid) / "media.json", {})
