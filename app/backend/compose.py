"""Composition helpers shared by the export pipeline.

`timeline()` turns the cut sequence into per-cut offsets — the single source of
truth for "where does cut N sit on the final clock", reused by background-audio
spans now and .ass overlay timing later (P5).

The background-audio functions implement *dynamic-length* beds: an asset is
fitted to fill the exact duration of a span of cuts by looping, time-stretching,
or trimming. Several layers on adjacent spans = several beds played in order.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import media_ops


@dataclass(frozen=True)
class Segment:
    index: int
    offset_s: float   # start on the final timeline
    dur_s: float


def timeline(cut_durations: list[float]) -> list[Segment]:
    """Per-cut offsets on the final timeline from each cut's duration."""
    out, t = [], 0.0
    for i, d in enumerate(cut_durations):
        d = max(0.05, float(d))
        out.append(Segment(index=i, offset_s=round(t, 3), dur_s=round(d, 3)))
        t += d
    return out


def span_window(segs: list[Segment], from_pos: int, to_pos: int) -> tuple[float, float]:
    """(start_offset, duration) covering cuts from_pos..to_pos inclusive."""
    n = len(segs)
    if n == 0:
        return 0.0, 0.0
    lo = max(0, min(from_pos, n - 1))
    hi = max(lo, min(to_pos, n - 1))
    start = segs[lo].offset_s
    end = segs[hi].offset_s + segs[hi].dur_s
    return round(start, 3), round(max(0.05, end - start), 3)


def _atempo_chain(ratio: float) -> str:
    """ffmpeg atempo only accepts 0.5–2.0 per filter; chain for bigger ratios."""
    ratio = max(0.25, min(4.0, ratio))
    parts = []
    while ratio > 2.0:
        parts.append("atempo=2.0")
        ratio /= 2.0
    while ratio < 0.5:
        parts.append("atempo=0.5")
        ratio /= 0.5
    parts.append(f"atempo={ratio:.6f}")
    return ",".join(parts)


def render_layer(asset_path: Path, target_dur: float, fit: str, gain: float,
                 out: Path, check_cancel=None) -> Path:
    """Produce a stereo WAV of exactly `target_dur` seconds from `asset_path`.

    fit:
      loop    — repeat the asset to fill the span (trim the final repeat)
      stretch — time-stretch the asset to the span length (tempo changes)
      trim    — play once, padded with silence if short / cut if long
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    gain = max(0.0, float(gain))
    vol = f"volume={gain:.3f}"
    common = ["-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(out)]
    if fit == "stretch":
        asset_dur = media_ops.duration(asset_path) or target_dur
        af = f"{_atempo_chain(asset_dur / target_dur)},apad,atrim=0:{target_dur:.3f},{vol}"
        cmd = ["ffmpeg", "-y", "-i", str(asset_path), "-af", af, *common]
    elif fit == "trim":
        af = f"apad,atrim=0:{target_dur:.3f},{vol}"
        cmd = ["ffmpeg", "-y", "-i", str(asset_path), "-af", af, *common]
    else:  # loop (default)
        af = f"atrim=0:{target_dur:.3f},{vol}"
        cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(asset_path),
               "-af", af, *common]
    media_ops._run_ffmpeg(cmd, check_cancel, timeout=7200)
    return out


def apply_background(base_file: Path, has_video: bool, layers: list[dict],
                     out: Path, check_cancel=None) -> Path:
    """Mix fitted background layers onto `base_file`'s audio at their offsets.

    layers: [{"path": fitted_wav, "start_s": float}] — each already gain-applied
    and length-fitted by render_layer. Video is stream-copied (no re-encode);
    only audio is rebuilt."""
    real = [l for l in layers if Path(l["path"]).exists()]
    if not real:
        return base_file
    cmd = ["ffmpeg", "-y", "-i", str(base_file)]
    for l in real:
        cmd += ["-i", str(l["path"])]
    filters = []
    for i, l in enumerate(real, start=1):
        delay = max(0, int(round(float(l["start_s"]) * 1000)))
        filters.append(f"[{i}:a]adelay={delay}|{delay}[b{i}]")
    mix_inputs = "[0:a]" + "".join(f"[b{i}]" for i in range(1, len(real) + 1))
    # normalize=0 keeps the dialogue/dub at full level; bg sits under it by gain
    filters.append(f"{mix_inputs}amix=inputs={len(real) + 1}:duration=first:"
                   f"dropout_transition=0:normalize=0[aout]")
    maps = ["-map", "[aout]"]
    vargs = []
    if has_video:
        maps = ["-map", "0:v:0", "-map", "[aout]"]
        vargs = ["-c:v", "copy"]
    is_wav = out.suffix.lower() == ".wav"
    aargs = (["-c:a", "pcm_s16le"] if is_wav
             else ["-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart"])
    cmd += ["-filter_complex", ";".join(filters), *maps, *vargs, *aargs, str(out)]
    media_ops._run_ffmpeg(cmd, check_cancel, timeout=7200)
    return out
