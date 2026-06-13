"""ffmpeg/ffprobe helpers: probe, remux to seek-friendly mp4 with progress, audio extraction."""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

MEDIA_ROOT = Path(os.environ.get(
    "RECOMPOSER_MEDIA",
    Path(__file__).resolve().parent.parent / "media_store"))
MEDIA_ROOT.mkdir(exist_ok=True)

BROWSER_VIDEO = {"h264"}


def safe_unlink(path: Path):
    """Delete a file, tolerating Windows file-lock quirks (retries, then gives up)."""
    for _ in range(5):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            time.sleep(0.4)
    # leftover temp file is harmless; the OS cleans the temp dir eventually


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def probe(path: Path):
    """Returns (duration_seconds, has_video, video_codec, audio_codec) or None."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=60)
        data = json.loads(out.stdout)
    except Exception:
        return None
    duration = float(data.get("format", {}).get("duration") or 0) or None
    vcodec = acodec = None
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and not vcodec:
            # ignore embedded cover art
            if s.get("disposition", {}).get("attached_pic"):
                continue
            vcodec = s.get("codec_name")
        elif s.get("codec_type") == "audio" and not acodec:
            acodec = s.get("codec_name")
    return duration, vcodec is not None, vcodec, acodec


def duration(path: Path) -> float | None:
    info = probe(path)
    return info[0] if info else None


def media_dir(media_id: int) -> Path:
    d = MEDIA_ROOT / str(media_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


BG_AUDIO_DIR = MEDIA_ROOT / "bg_audio"


def bg_audio_path(filename: str) -> Path:
    return BG_AUDIO_DIR / filename


def _check(check_cancel, proc):
    """Run the job's cancel check; if it raises, take ffmpeg down with us."""
    if check_cancel is None:
        return
    try:
        check_cancel()
    except BaseException:
        proc.kill()
        proc.wait()
        raise


def _run_ffmpeg_with_progress(cmd, duration, on_progress, check_cancel=None):
    """Run ffmpeg with -progress on stdout; call on_progress(percent) as it goes."""
    full = cmd[:1] + ["-nostats", "-loglevel", "error",
                      "-progress", "pipe:1"] + cmd[1:]
    proc = subprocess.Popen(full, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    last = -10
    for line in proc.stdout:
        _check(check_cancel, proc)
        line = line.strip()
        if line.startswith("out_time_ms=") and duration:
            try:
                pct = min(99, int(line.split("=")[1]) / 1_000_000 / duration * 100)
            except ValueError:
                continue
            if pct - last >= 2 and on_progress:
                last = pct
                on_progress(pct)
    proc.wait()
    if proc.returncode != 0:
        err = proc.stderr.read()[-400:] if proc.stderr else ""
        raise RuntimeError(f"ffmpeg failed: {err}")


def prepare_for_streaming(src: Path, media_id: int, *, keep_src: bool = False,
                          on_progress=None, check_cancel=None):
    """Remux (fast) or re-encode (slow, shows progress) into a browser-seekable file.

    keep_src=True when src is the user's own file (local-path import) — never delete it.
    Returns (final_path, media_type, duration, mode) where mode is 'copy'/'remux'/'reencode'.
    """
    dest_dir = media_dir(media_id)
    info = probe(src) if have_ffmpeg() else None

    if info is None:
        # no ffmpeg: trust the extension, copy as-is
        final = dest_dir / ("source" + src.suffix.lower())
        if keep_src:
            shutil.copy2(str(src), final)
        else:
            shutil.move(str(src), final)
        mtype = "video" if src.suffix.lower() in (".mp4", ".webm", ".mov", ".mkv") else "audio"
        return final, mtype, None, "copy"

    duration, has_video, vcodec, acodec = info

    if has_video:
        final = dest_dir / "source.mp4"
        if vcodec in BROWSER_VIDEO and acodec in (None, "aac", "mp3"):
            mode = "remux"  # stream copy: runs at disk speed
            cmd = ["ffmpeg", "-y", "-i", str(src), "-c", "copy",
                   "-movflags", "+faststart", str(final)]
        else:
            mode = "reencode"  # h264 conversion: slow, but only needed once
            cmd = ["ffmpeg", "-y", "-i", str(src),
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                   "-c:a", "aac", "-b:a", "160k",
                   "-movflags", "+faststart", str(final)]
        _run_ffmpeg_with_progress(cmd, duration, on_progress, check_cancel)
        if not keep_src:
            safe_unlink(src)
        return final, "video", duration, mode

    # audio-only
    if acodec == "mp3":
        final = dest_dir / "source.mp3"
        mode = "remux"
        cmd = ["ffmpeg", "-y", "-i", str(src), "-c", "copy", str(final)]
    elif acodec == "aac":
        final = dest_dir / "source.m4a"
        mode = "remux"
        cmd = ["ffmpeg", "-y", "-i", str(src), "-vn", "-c", "copy",
               "-movflags", "+faststart", str(final)]
    else:
        final = dest_dir / "source.m4a"
        mode = "reencode"
        cmd = ["ffmpeg", "-y", "-i", str(src), "-vn", "-c:a", "aac", "-b:a", "160k",
               "-movflags", "+faststart", str(final)]
    _run_ffmpeg_with_progress(cmd, duration, on_progress, check_cancel)
    if not keep_src:
        safe_unlink(src)
    return final, "audio", duration, mode


# ---------------------------------------------------------------- export

EXPORT_DIR = MEDIA_ROOT / "exports"

# uniform clip parameters so the final concat is a lossless stream-copy
EXPORT_W, EXPORT_H, EXPORT_FPS = 1280, 720, 30
EXPORT_PRESETS = {
    "480p": (854, 480, 30, "23"),
    "720p": (1280, 720, 30, "20"),
    "1080p": (1920, 1080, 30, "22"),
}
A_ARGS = ["-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2"]


def _video_settings(quality: str):
    w, h, fps, crf = EXPORT_PRESETS.get(quality, EXPORT_PRESETS["720p"])
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
          f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}")
    v_args = ["-c:v", "libx264", "-preset", "veryfast", "-crf", crf,
              "-pix_fmt", "yuv420p"]
    return w, h, fps, vf, v_args


def _run_ffmpeg(cmd, check_cancel=None, timeout=3600):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True)
    waited = 0.0
    while True:
        try:
            _, err = proc.communicate(timeout=0.5)
            break
        except subprocess.TimeoutExpired:
            waited += 0.5
            if waited > timeout:
                proc.kill()
                proc.communicate()
                raise RuntimeError("ffmpeg timed out")
            _check(check_cancel, proc)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {(err or '')[-400:]}")


def _clip_cmd(src: Path, start: float, dur: float, out: Path,
              has_video: bool, src_is_video: bool, src_has_audio: bool,
              audio_src: Path | None = None, quality: str = "720p"):
    """One uniformly-encoded clip. Edge cases get synthetic streams:
    audio-only source in a video export → black video; mute video → silence."""
    export_w, export_h, export_fps, video_filter, v_args = _video_settings(quality)
    if audio_src is not None and not audio_src.exists():
        raise RuntimeError(f"audio source missing: {audio_src}")
    if audio_src is not None:
        if not has_video:
            return ["ffmpeg", "-y", "-t", f"{dur:.3f}", "-i", str(audio_src),
                    "-vn", "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(out)]
        if not src_is_video:
            return ["ffmpeg", "-y",
                    "-t", f"{dur:.3f}", "-i", str(audio_src),
                    "-f", "lavfi", "-i",
                    f"color=c=black:s={export_w}x{export_h}:r={export_fps}",
                    "-map", "1:v", "-map", "0:a", "-shortest",
                    *v_args, *A_ARGS, str(out)]
        return ["ffmpeg", "-y",
                "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(src),
                "-t", f"{dur:.3f}", "-i", str(audio_src),
                "-map", "0:v:0", "-map", "1:a:0", "-shortest",
                "-vf", video_filter, *v_args, *A_ARGS, str(out)]

    base = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(src)]
    if not has_video:  # pure-audio export → wav clips
        return base + ["-vn", "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(out)]
    if not src_is_video:
        return base + ["-f", "lavfi", "-i",
                       f"color=c=black:s={export_w}x{export_h}:r={export_fps}",
                       "-map", "1:v", "-map", "0:a", "-shortest",
                       *v_args, *A_ARGS, str(out)]
    if not src_has_audio:
        return base + ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                       "-map", "0:v", "-map", "1:a", "-shortest",
                       "-vf", video_filter, *v_args, *A_ARGS, str(out)]
    return base + ["-map", "0:v:0", "-map", "0:a:0", "-vf", video_filter,
                   *v_args, *A_ARGS, str(out)]


def export_recomposition(recomp_id: int, title: str, cuts: list[dict],
                         on_progress=None, check_cancel=None,
                         quality: str = "720p", bg_layers: list[dict] | None = None) -> Path:
    """cuts: [{src, start_s, end_s, is_video}] in playback order.
    Re-encodes every cut to identical parameters, concat-copies them, then (if
    bg_layers) mixes dynamic-length background-audio beds over the result.
    bg_layers: [{asset_path, from_pos, to_pos, gain, fit}].
    on_progress(msg, percent). Returns the final path under media_store/exports/."""
    if not have_ffmpeg():
        raise RuntimeError("ffmpeg is required for export")
    from . import compose  # lazy: compose imports media_ops
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    has_video = any(c["is_video"] for c in cuts)
    ext = "mp4" if has_video else "wav"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe_title = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in title).strip() or "recomposition"
    final = EXPORT_DIR / f"recomp{recomp_id}_{safe_title[:40]}_{stamp}.{ext}"
    tmp = EXPORT_DIR / f"tmp_{recomp_id}_{stamp}"
    tmp.mkdir(parents=True, exist_ok=True)

    try:
        clips = []
        for i, c in enumerate(cuts):
            if on_progress:
                on_progress(f"rendering cut {i + 1}/{len(cuts)}", i / len(cuts) * 85)
            src = Path(c["src"])
            info = probe(src)
            src_has_audio = bool(info and info[3])
            dur = max(0.05, c["end_s"] - c["start_s"])
            out = tmp / f"{i:04d}.{ext}"
            audio_src = Path(c["audio_src"]) if c.get("audio_src") else None
            _run_ffmpeg(_clip_cmd(src, c["start_s"], dur, out,
                                  has_video, c["is_video"], src_has_audio,
                                  audio_src=audio_src, quality=quality),
                        check_cancel)
            clips.append(out)

        if on_progress:
            on_progress("joining clips", 88)
        listfile = tmp / "list.txt"
        listfile.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in clips), encoding="utf-8")
        concat_out = (tmp / f"concat.{ext}") if bg_layers else final
        _run_ffmpeg(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                     "-i", str(listfile), "-c", "copy",
                     *(["-movflags", "+faststart"] if has_video else []),
                     str(concat_out)], check_cancel)

        if bg_layers:
            if on_progress:
                on_progress("adding background audio", 94)
            segs = compose.timeline([max(0.05, c["end_s"] - c["start_s"]) for c in cuts])
            rendered = []
            for k, layer in enumerate(bg_layers):
                start_s, span_dur = compose.span_window(
                    segs, int(layer["from_pos"]), int(layer["to_pos"]))
                fitted = compose.render_layer(
                    Path(layer["asset_path"]), span_dur, layer.get("fit", "loop"),
                    float(layer.get("gain", 1.0)), tmp / f"bg_{k:03d}.wav",
                    trim_start=layer.get("trim_start", 0.0), trim_end=layer.get("trim_end"),
                    loop_start=layer.get("loop_start"), loop_end=layer.get("loop_end"),
                    fade_in=layer.get("fade_in", 0.0), fade_out=layer.get("fade_out", 0.0),
                    check_cancel=check_cancel)
                rendered.append({"path": fitted, "start_s": start_s})
            compose.apply_background(concat_out, has_video, rendered, final,
                                     check_cancel=check_cancel)
        return final
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def extract_wav_for_transcription(media_id: int, source: Path,
                                  check_cancel=None) -> Path:
    """16 kHz mono wav — what whisper wants."""
    wav = media_dir(media_id) / "transcribe.wav"
    _run_ffmpeg(["ffmpeg", "-y", "-i", str(source), "-ar", "16000", "-ac", "1",
                 "-c:a", "pcm_s16le", str(wav)], check_cancel, timeout=7200)
    return wav


def mix_audio(inputs, out: Path, duration: float | None = None,
              check_cancel=None) -> Path:
    """Mix several full-length audio tracks into one (amix, no level scaling).

    Used to compose a dubbed clip's audio from its components — translated
    speech, the separated accompaniment (background), and/or the original
    vocals — depending on the export options. `normalize=0` keeps each track at
    its own level instead of dividing by the input count."""
    paths = [Path(p) for p in inputs if p and Path(p).exists()]
    if not paths:
        raise RuntimeError("no audio inputs to mix")
    out.parent.mkdir(parents=True, exist_ok=True)
    is_wav = out.suffix.lower() == ".wav"
    codec = (["-c:a", "pcm_s16le"] if is_wav
             else ["-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart"])
    cmd = ["ffmpeg", "-y"]
    for p in paths:
        cmd += ["-i", str(p)]
    if len(paths) == 1:
        cmd += (["-t", f"{duration:.3f}"] if duration else [])
        cmd += ["-ar", "44100", "-ac", "2", *codec, str(out)]
    else:
        mix = (f"amix=inputs={len(paths)}:duration=longest:"
               f"dropout_transition=0:normalize=0")
        if duration:
            mix += f",atrim=0:{duration:.3f}"
        labels = "".join(f"[{i}:a]" for i in range(len(paths)))
        cmd += ["-filter_complex", f"{labels}{mix}[a]", "-map", "[a]",
                "-ar", "44100", "-ac", "2", *codec, str(out)]
    _run_ffmpeg(cmd, check_cancel, timeout=7200)
    return out


def extract_audio_window(source: Path, start_s: float, end_s: float, out: Path,
                         check_cancel=None) -> Path:
    """Extract a small stereo WAV window for source separation / later dubbing."""
    if end_s <= start_s:
        raise RuntimeError("audio window end must be after start")
    out.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg([
        "ffmpeg", "-y",
        "-ss", f"{max(0.0, start_s):.3f}",
        "-t", f"{(end_s - start_s):.3f}",
        "-i", str(source),
        "-vn", "-ar", "44100", "-ac", "2",
        "-c:a", "pcm_s16le", str(out),
    ], check_cancel, timeout=7200)
    return out
