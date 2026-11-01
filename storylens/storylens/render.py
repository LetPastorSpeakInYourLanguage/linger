"""Render a verified script to MP4: EDL planning (footage from cited lines, shot/silence snapping) -> TTS ->
closed-loop duration fit -> ffmpeg pieces -> concat. Language-agnostic: original audio is only ducked under
narration or played as-is in hero clips; the narration language is independent of the film's language."""
from __future__ import annotations
import os, subprocess
from pathlib import Path
from . import ingest, media as M
from .util import read_json, write_json, write_text

W, H, FPS = 1280, 720, 25


def _ff(cmd, cwd=None):
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, encoding="utf-8", errors="replace")
    if p.returncode: raise RuntimeError("ffmpeg failed: " + p.stderr[-1500:])


def _snap_shot(t, shots, direction, max_move=1.2):
    c = [s for s in shots if abs(s - t) <= max_move and ((s >= t) if direction > 0 else (s <= t))]
    return min(c, key=lambda s: abs(s - t)) if c else t


def _snap_silence(t, speech, direction, search=0.8):
    if not speech: return t
    step, prob = speech["step"], speech["prob"]; i = int(t / step); r = int(search / step)
    for d in range(r + 1):
        j = i + d * (1 if direction > 0 else -1)
        if 0 <= j < len(prob) and prob[j] < 0.5: return j * step
    return t


def plan(ws, tid, script, tts, log=print):
    t = ws.title(tid); media = {m["id"]: m for m in t["media"]}
    ctx = {}
    for mid in media:
        try:
            cs = ingest.cues(ws, tid, mid)
            ctx[mid] = {"by": {c.idx: c for c in cs}, "shots": read_json(ws.edir(tid, mid) / "shots.json", []),
                        "speech": read_json(ws.edir(tid, mid) / "speech.json"), "dur": ingest.media_info(ws, tid, mid).get("duration") or (cs[-1].end + 5)}
        except Exception:
            pass
    edl = []
    for k, s in enumerate(script["segments"]):
        mid = s.get("media") if s.get("media") in ctx else next(iter(ctx))
        c = ctx[mid]; a, z = (s.get("lines") or [0, 0])[:2] if s.get("lines") else (0, 0)
        ca = c["by"].get(a) or min(c["by"].values(), key=lambda x: abs(x.idx - a)); cz = c["by"].get(z) or ca
        src = media[mid].get("video")
        if s["type"] == "hero_clip":
            st = _snap_silence(ca.start - 0.15, c["speech"], -1); en = _snap_silence(cz.end + 0.15, c["speech"], +1)
            edl.append({"k": k, "type": "hero", "media": mid, "video": src, "src": [max(0, st), min(c["dur"], en)]})
        elif s["type"] == "title_card":
            edl.append({"k": k, "type": "card", "media": mid, "video": src, "src": [ca.start, ca.start + 2.8], "text": s["text"]})
        else:
            wav, d = tts.say(s["text"])
            need = d + 0.7
            st, en = _snap_shot(ca.start - 0.3, c["shots"], -1), _snap_shot(cz.end + 0.3, c["shots"], +1)
            if en - st < need: en = min(c["dur"], st + need); st = max(0, en - need)
            edl.append({"k": k, "type": "narr", "media": mid, "video": src, "src": [st, st + need], "tts": str(wav), "tts_dur": d, "text": s["text"]})
    return edl


def duration(edl): return sum(p["src"][1] - p["src"][0] for p in edl)


def fit(edl, target, tts, script, tol=0.05, log=print):
    """Closed loop: cap hero clips -> re-time voice (0.9-1.2x) -> pad footage -> drop least important segments."""
    if not target: return edl
    hero = [p for p in edl if p["type"] == "hero"]; narr = [p for p in edl if p["type"] == "narr"]
    tot = duration(edl)
    if tot > target * (1 + tol) and hero:
        excess, ht = tot - target, sum(p["src"][1] - p["src"][0] for p in hero)
        for p in hero:
            d = p["src"][1] - p["src"][0]; cut = min(d - 3.0, excess * d / ht)
            if cut > 0: p["src"][1] -= cut
        log(f"fit: hero clips capped {ht:.0f}s -> {sum(p['src'][1] - p['src'][0] for p in hero):.0f}s")
    tot = duration(edl)
    if narr and abs(tot - target) > target * tol:
        n_tot = sum(p["tts_dur"] for p in narr); other = tot - sum(p["src"][1] - p["src"][0] for p in narr)
        speed = min(1.2, max(0.9, n_tot / max(1.0, target - other - 0.7 * len(narr))))
        v = tts.with_speed(getattr(tts, "speed", 1.0) * speed)
        for p in narr:
            wav, d = v.say(p["text"]); p["tts"], p["tts_dur"] = str(wav), d; p["src"] = [p["src"][0], p["src"][0] + d + 0.7]
        log(f"fit: narration re-timed ×{speed:.2f}")
        tot = duration(edl)
        if tot < target * (1 - tol):
            extra = (target - tot) / len(narr)
            for p in narr: p["src"][1] += extra
            log(f"fit: footage padded +{extra:.1f}s per narration segment")
    return edl


def render(ws, tid, edl, out_path, work, hardsub_band=None, log=print):
    if not M.have_ffmpeg(): raise RuntimeError("ffmpeg not found on PATH — install it to render video (the script is still saved).")
    work = Path(work); work.mkdir(parents=True, exist_ok=True); parts = []
    vf = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps={FPS},format=yuv420p,setsar=1"
    if hardsub_band:
        y0, y1 = hardsub_band
        vf += f",split[a][b];[b]crop=iw:ih*{y1 - y0:.3f}:0:ih*{y0:.3f},boxblur=14:2[bb];[a][bb]overlay=0:H*{y0:.3f}"
    enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]
    for i, p in enumerate(edl):
        st, en = p["src"]; dur = max(0.6, en - st); out = work / f"p{i:03d}.mp4"
        fade = f"afade=t=in:d=0.12,afade=t=out:st={max(0, dur - 0.2):.2f}:d=0.2"
        src = ["-ss", f"{st:.3f}", "-t", f"{dur:.3f}", "-i", p["video"]] if p.get("video") else ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", f"color=c=black:s={W}x{H}:r={FPS}", "-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        if p["type"] == "hero":
            _ff(["ffmpeg", "-y", "-v", "error", *src, "-vf", vf, "-af", f"aresample=48000,{fade}", *enc, str(out)])
        elif p["type"] == "card":
            ass = work / f"card{i:03d}.ass"
            write_text(ass, "[Script Info]\nScriptType: v4.00+\nPlayResX: 1280\nPlayResY: 720\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Alignment, BorderStyle, Outline, Shadow, MarginV\n"
                       "Style: Default,Arial,64,&H00FFFFFF,&H00000000,&H80000000,-1,5,1,3,1,0\n\n[Events]\nFormat: Layer, Start, End, Style, Text\n"
                       f"Dialogue: 0,0:00:00.00,0:00:{dur:05.2f},Default,{p['text'].replace(chr(10), ' ')}\n")
            _ff(["ffmpeg", "-y", "-v", "error", *src, "-vf", vf + f",eq=brightness=-0.25:saturation=0.6,boxblur=6,subtitles={ass.name}",
                 "-af", "aresample=48000,volume=0.25", *enc, out.name], cwd=work)
        else:
            pad = max(0.0, (dur - p["tts_dur"]) / 2); ms = int(pad * 1000)
            a_in = "[0:a]" if p.get("video") else "[1:a]"; t_idx = 1 if p.get("video") else 2
            _ff(["ffmpeg", "-y", "-v", "error", *src, "-i", p["tts"], "-filter_complex",
                 f"[0:v]{vf}[v];{a_in}aresample=48000,volume=0.12,aformat=channel_layouts=stereo[bg];"
                 f"[{t_idx}:a]aresample=48000,adelay={ms}|{ms},volume=1.6,aformat=channel_layouts=stereo[vo];"
                 f"[bg][vo]amix=inputs=2:duration=first:normalize=0,{fade}[a]",
                 "-map", "[v]", "-map", "[a]", *enc, str(out)])
        parts.append(out); log(f"rendered piece {i + 1}/{len(edl)}")
    lst = work / "list.txt"; write_text(lst, "".join(f"file '{p.name}'\n" for p in parts))
    _ff(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "list.txt", "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5",
         "-c:a", "aac", "-b:a", "160k", str(Path(out_path).resolve())], cwd=work)
    return out_path
