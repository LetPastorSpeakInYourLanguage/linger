"""ffmpeg/ffprobe helpers: probe, remux to seek-friendly mp4, audio extraction."""
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
BROWSER_AUDIO = {"aac", "mp3", "opus", "vorbis", "flac"}


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


def prepare_for_streaming(src: Path, media_id: int):
    """Remux/transcode the upload into a browser-seekable file.

    Returns (final_path, media_type, duration) — final file lives in media_dir.
    """
    info = probe(src) if have_ffmpeg() else None
    dest_dir = media_dir(media_id)

    if info is None:
        # no ffmpeg: trust the extension, copy as-is
        final = dest_dir / ("source" + src.suffix.lower())
        shutil.move(str(src), final)
        mtype = "video" if src.suffix.lower() in (".mp4", ".webm", ".mov", ".mkv") else "audio"
        return final, mtype, None

    duration, has_video, vcodec, acodec = info

    if has_video:
        final = dest_dir / "source.mp4"
        if vcodec in BROWSER_VIDEO and acodec in (None, "aac", "mp3"):
            cmd = ["ffmpeg", "-y", "-i", str(src), "-c", "copy",
                   "-movflags", "+faststart", str(final)]
        else:  # re-encode anything browser-hostile (hevc, vp9-in-mkv with weird audio, ...)
            cmd = ["ffmpeg", "-y", "-i", str(src),
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                   "-c:a", "aac", "-b:a", "160k",
                   "-movflags", "+faststart", str(final)]
        subprocess.run(cmd, capture_output=True, timeout=7200, check=True)
        safe_unlink(src)
        return final, "video", duration

    # audio-only
    final = dest_dir / "source.m4a"
    if acodec == "aac" and src.suffix.lower() in (".m4a", ".mp4", ".aac"):
        cmd = ["ffmpeg", "-y", "-i", str(src), "-c", "copy",
               "-movflags", "+faststart", str(final)]
    elif acodec == "mp3":
        final = dest_dir / "source.mp3"
        cmd = ["ffmpeg", "-y", "-i", str(src), "-c", "copy", str(final)]
    else:
        cmd = ["ffmpeg", "-y", "-i", str(src), "-c:a", "aac", "-b:a", "160k",
               "-movflags", "+faststart", str(final)]
    subprocess.run(cmd, capture_output=True, timeout=7200, check=True)
    safe_unlink(src)
    return final, "audio", duration


def extract_wav_for_transcription(media_id: int, source: Path) -> Path:
    """16 kHz mono wav — what whisper wants."""
    wav = media_dir(media_id) / "transcribe.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(source), "-ar", "16000", "-ac", "1",
         "-c:a", "pcm_s16le", str(wav)],
        capture_output=True, timeout=7200, check=True)
    return wav
