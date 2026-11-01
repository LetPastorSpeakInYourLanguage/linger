"""Recap renderer: script segments -> timed edit decision list (EDL) -> MP4.

Segment types
  narration  : TTS voice over footage from the cited subtitle lines; original audio ducked (-20 dB)
               so the film's ambience/music stays (language-agnostic: we never need its words).
  hero_clip  : original audio + picture for the cited lines, cut on silences (VAD) — the actors'
               own emotional delivery, in whatever language they speak.
  title_card : short on-screen text over a dimmed still (fan/silent style).
  still      : Ken-Burns push-in on the best still of the beat (used when footage is too short).
Footage choice for narration: the cited line range, snapped to shot boundaries; if the narration is
longer than the range, the window is extended forward/backward inside the same scene; if still too
short, a Ken-Burns still pads the remainder.
"""
from __future__ import annotations
import json, os, subprocess
import numpy as np
from . import video

FONT = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
W, H, FPS = 1280, 536, 24


def _run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-2000:])


class TTS:
    def __init__(self, voice="am_michael", speed=1.0, cache="/home/user/work/tts_cache"):
        from kokoro_onnx import Kokoro
        from . import MODELS
        self.k = Kokoro(os.path.join(MODELS, "kokoro-v1.0.onnx"), os.path.join(MODELS, "voices-v1.0.bin"))
        self.voice, self.speed, self.cache = voice, speed, cache
        os.makedirs(cache, exist_ok=True)

    def say(self, text):
        import hashlib, soundfile as sf
        h = hashlib.sha1(f"{self.voice}|{self.speed}|{text}".encode()).hexdigest()[:16]
        p = os.path.join(self.cache, f"{h}.wav")
        if not os.path.exists(p):
            s, sr = self.k.create(text, voice=self.voice, speed=self.speed, lang="en-us")
            sf.write(p, s, sr)
        import soundfile as sf
        return p, sf.info(p).duration


def _snap_shot(t, shots, direction, max_move=1.2):
    c = [s for s in shots if abs(s - t) <= max_move and ((s >= t) if direction > 0 else (s <= t))]
    return min(c, key=lambda s: abs(s - t)) if c else t


def plan(segments, cues, shots, vad_mask, vad_step, tts: TTS, film_dur, stills=None, pad=0.35):
    """Return an EDL: list of pieces with source ranges and audio instructions."""
    by = {c.idx: c for c in cues}
    edl = []
    for k, s in enumerate(segments):
        a_line, z_line = s.get("visual_lines") or [None, None]
        a = by[a_line].start if a_line in by else 0.0
        z = by[z_line].end if z_line in by else a + 4
        if s["type"] == "hero_clip":
            st = video.snap_to_silence(a - 0.15, vad_mask, vad_step, 0.8, -1)
            en = video.snap_to_silence(z + 0.15, vad_mask, vad_step, 1.0, +1)
            edl.append({"k": k, "type": "hero", "src": [max(0, st), min(film_dur, en)], "audio": "orig", "mood": s.get("mood")})
        elif s["type"] == "title_card":
            edl.append({"k": k, "type": "card", "src": [a, a + 2.8], "text": s["text"], "audio": "orig_low"})
        else:
            wav, d = tts.say(s["text"])
            need = d + 2 * pad
            st, en = _snap_shot(a - 0.3, shots, -1), _snap_shot(z + 0.3, shots, +1)
            if en - st < need:   # extend forward first (what happens next), then backward
                en = min(film_dur, st + need)
                if en - st < need: st = max(0, en - need)
            if en - st > need * 1.6:   # long range: start a little before the cited moment
                st = max(st, a - 0.5); en = st + need
            edl.append({"k": k, "type": "narr", "src": [st, min(en, st + need)], "tts": wav, "tts_dur": d, "audio": "duck", "mood": s.get("mood")})
    return edl


def render(edl, source, out_path, work):
    os.makedirs(work, exist_ok=True)
    parts = []
    vf_base = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps={FPS},format=yuv420p"
    for p in edl:
        st, en = p["src"]; dur = max(0.5, en - st)
        out = os.path.join(work, f"p{p['k']:03d}.mp4")
        fade = f"afade=t=in:d=0.15,afade=t=out:st={max(0, dur - 0.2):.2f}:d=0.2"
        if p["type"] == "hero":
            _run(["ffmpeg", "-y", "-v", "error", "-ss", f"{st:.3f}", "-t", f"{dur:.3f}", "-i", source,
                  "-vf", vf_base + f",fade=t=in:d=0.12,fade=t=out:st={dur - 0.15:.2f}:d=0.15",
                  "-af", f"aresample=48000,{fade},volume=1.0", "-ac", "2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "160k", out])
        elif p["type"] == "card":
            txt = p["text"].replace("'", "’").replace(":", "\\:")
            _run(["ffmpeg", "-y", "-v", "error", "-ss", f"{st:.3f}", "-t", f"{dur:.3f}", "-i", source,
                  "-vf", vf_base + f",eq=brightness=-0.25:saturation=0.6,boxblur=6,drawtext=fontfile={FONT}:text='{txt}':fontcolor=white:fontsize=44:x=(w-text_w)/2:y=(h-text_h)/2,fade=t=in:d=0.3,fade=t=out:st={dur - 0.3:.2f}:d=0.3",
                  "-af", f"aresample=48000,volume=0.25,{fade}", "-ac", "2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "160k", out])
        else:
            pad = (dur - p["tts_dur"]) / 2
            _run(["ffmpeg", "-y", "-v", "error", "-ss", f"{st:.3f}", "-t", f"{dur:.3f}", "-i", source, "-i", p["tts"],
                  "-filter_complex",
                  f"[0:v]{vf_base}[v];[0:a]aresample=48000,volume=0.1,aformat=channel_layouts=stereo[bg];"
                  f"[1:a]aresample=48000,adelay={int(pad * 1000)}|{int(pad * 1000)},volume=1.6,aformat=channel_layouts=stereo[vo];"
                  f"[bg][vo]amix=inputs=2:duration=first:normalize=0,{fade}[a]",
                  "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "160k", out])
        parts.append(out)
    lst = os.path.join(work, "list.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5", "-c:a", "aac", "-b:a", "160k", out_path])
    return out_path
