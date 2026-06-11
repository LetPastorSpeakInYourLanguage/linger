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


def media_dir(media_id: int) -> Path:
    d = MEDIA_ROOT / str(media_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run_ffmpeg_with_progress(cmd, duration, on_progress):
    """Run ffmpeg with -progress on stdout; call on_progress(percent) as it goes."""
    full = cmd[:1] + ["-nostats", "-loglevel", "error",
                      "-progress", "pipe:1"] + cmd[1:]
    proc = subprocess.Popen(full, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    last = -10
    for line in proc.stdout:
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
                          on_progress=None):
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
        _run_ffmpeg_with_progress(cmd, duration, on_progress)
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
    _run_ffmpeg_with_progress(cmd, duration, on_progress)
    if not keep_src:
        safe_unlink(src)
    return final, "audio", duration, mode


def extract_wav_for_transcription(media_id: int, source: Path) -> Path:
    """16 kHz mono wav — what whisper wants."""
    wav = media_dir(media_id) / "transcribe.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(source), "-ar", "16000", "-ac", "1",
         "-c:a", "pcm_s16le", str(wav)],
        capture_output=True, timeout=7200, check=True)
    return wav
