"""Background job queue: jobs persisted in SQLite, claimed by a worker loop.

Jobs are claimed with a lease (worker_id + lease_until) via an optimistic
UPDATE, so any number of workers — the in-process thread today, remote
executors later — can share one queue safely. A job whose lease expires
(crashed worker) becomes claimable again. Handlers register with @handler
and receive a JobContext for progress reporting + cooperative cancellation.

Job kinds:
  download    {"url", "then_transcribe", "whisper"?}              — yt-dlp fetch
  prepare     {"src", "keep_src", "then_transcribe", "whisper"?}  — ffmpeg remux/re-encode
  transcribe  {"model"?, "language"?, "device"?, "compute"?}      — whisperx / faster-whisper
  separate    {"cut_id", "padding_s"?}                            — vocals/accompaniment stems
  translate_track {"track_id", "target_lang", ...}                — subtitle track translation
  translate_recomposition {"recomp_id", "lang_code", ...}         — cut translations
  export      {"recomp_id"}                                       — render recomposition
Jobs chain: download → prepare → (transcribe if no subtitles were provided);
the optional "whisper" dict ({"model": ...}) rides along the chain.
"""
import json
import os
import shutil
import socket
import threading
import traceback
from pathlib import Path

from . import gender as gender_mod
from . import media_ops, translation_ops
from .db import get_db
from .engines import separation, tts

_wake = threading.Event()
_started = False

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
LEASE_SECONDS = 180          # a running job must report/heartbeat within this
POLL_SECONDS = 3.0           # fallback poll when the wake event is missed

HANDLERS: dict = {}


class JobCancelled(Exception):
    """Raised inside a handler when the user requested cancellation."""


def handler(kind: str):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn
    return deco


def log(msg: str):
    print(f"  [recomposer] {msg}", flush=True)


def wake():
    _wake.set()


def enqueue(kind: str, media_id: int | None = None, payload: dict | None = None, *,
            priority: int = 0, target_kind: str | None = None,
            target_id: int | None = None, max_attempts: int = 2) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO jobs (kind, media_id, payload, priority, target_kind, target_id, max_attempts) "
        "VALUES (?,?,?,?,?,?,?)",
        (kind, media_id, json.dumps(payload or {}), priority, target_kind,
         target_id, max_attempts))
    db.commit()
    wake()
    return cur.lastrowid


class JobContext:
    """Handed to every handler: progress reporting (which also keeps the
    lease alive) and cooperative cancellation."""

    def __init__(self, job):
        self.job_id = job["id"]
        self.media_id = job["media_id"]
        self.kind = job["kind"]

    def report(self, detail: str = "", progress: float | None = None):
        db = get_db()
        if progress is None:
            db.execute(
                "UPDATE jobs SET detail=?, updated_at=datetime('now'), "
                "lease_until=datetime('now', ?) WHERE id=?",
                (detail, f"+{LEASE_SECONDS} seconds", self.job_id))
        else:
            db.execute(
                "UPDATE jobs SET detail=?, progress=?, updated_at=datetime('now'), "
                "lease_until=datetime('now', ?) WHERE id=?",
                (detail, round(min(100.0, progress), 1),
                 f"+{LEASE_SECONDS} seconds", self.job_id))
        db.commit()

    def heartbeat(self):
        db = get_db()
        db.execute("UPDATE jobs SET lease_until=datetime('now', ?) WHERE id=?",
                   (f"+{LEASE_SECONDS} seconds", self.job_id))
        db.commit()

    def cancelled(self) -> bool:
        row = get_db().execute("SELECT cancel_requested FROM jobs WHERE id=?",
                               (self.job_id,)).fetchone()
        return bool(row and row["cancel_requested"])

    def check_cancel(self):
        if self.cancelled():
            raise JobCancelled()


def _set_media(media_id: int, status: str, detail: str = ""):
    db = get_db()
    db.execute("UPDATE media SET status=?, status_detail=? WHERE id=?",
               (status, detail, media_id))
    db.commit()


def _media_title(media_id: int) -> str:
    row = get_db().execute("SELECT title FROM media WHERE id=?", (media_id,)).fetchone()
    return row["title"] if row else f"media {media_id}"


def _find_source(media_id: int) -> Path | None:
    d = media_ops.media_dir(media_id)
    for f in d.iterdir():
        if f.stem == "source":
            return f
    return None


def cut_stem_cache(cut_id: int, padding_s: float = 3.0) -> dict:
    """Return the cached stem window for a cut, with existence flags."""
    db = get_db()
    row = db.execute("""
        SELECT c.id AS cut_id, c.media_id, m.filename, m.duration,
               MIN(s.start_s) AS start_s, MAX(s.end_s) AS end_s
        FROM cuts c
        JOIN media m ON m.id = c.media_id
        JOIN cut_segments cs ON cs.cut_id = c.id
        JOIN segments s ON s.id = cs.segment_id
        WHERE c.id=?
        GROUP BY c.id, c.media_id, m.filename, m.duration""", (cut_id,)).fetchone()
    if not row or row["start_s"] is None or row["end_s"] is None:
        raise RuntimeError("cut not found or has no segments")
    start = max(0.0, float(row["start_s"]) - padding_s)
    end = float(row["end_s"]) + padding_s
    if row["duration"] is not None:
        end = min(float(row["duration"]), end)
    start_ms = int(round(start * 1000))
    end_ms = int(round(end * 1000))
    d = media_ops.media_dir(row["media_id"]) / "stems" / f"{start_ms}-{end_ms}"
    return {
        "cut_id": cut_id,
        "media_id": row["media_id"],
        "filename": row["filename"],
        "start_s": start,
        "end_s": end,
        "segment_start_s": float(row["start_s"]),
        "segment_end_s": float(row["end_s"]),
        "padding_s": padding_s,
        "dir": d,
        "vocals": d / "vocals.wav",
        "accompaniment": d / "accompaniment.wav",
        "exists": (d / "vocals.wav").exists() and (d / "accompaniment.wav").exists(),
    }


def _ensure_cut_stems(ctx: JobContext, cut_id: int, padding_s: float = 3.0) -> dict:
    cache = cut_stem_cache(cut_id, padding_s)
    if cache["exists"]:
        return cache
    if not media_ops.have_ffmpeg():
        raise RuntimeError("ffmpeg is required for source separation")
    src = media_ops.media_dir(cache["media_id"]) / cache["filename"]
    if not src.exists():
        raise RuntimeError(f"source file missing for media {cache['media_id']}")

    cache_dir = cache["dir"]
    cache_dir.mkdir(parents=True, exist_ok=True)
    input_wav = cache_dir / "input.wav"

    ctx.report("extracting cut audio window", progress=10)
    media_ops.extract_audio_window(src, cache["start_s"], cache["end_s"],
                                   input_wav, check_cancel=ctx.check_cancel)

    ctx.report("separating vocals/accompaniment", progress=25)
    result = separation.get_separation_engine().separate_vocals(
        input_wav, cache_dir, check_cancel=ctx.check_cancel)
    if not result.vocals.exists() or not result.accompaniment.exists():
        raise RuntimeError("separation engine did not produce both stems")

    manifest = {
        "cut_id": cut_id,
        "media_id": cache["media_id"],
        "start_s": cache["start_s"],
        "end_s": cache["end_s"],
        "segment_start_s": cache["segment_start_s"],
        "segment_end_s": cache["segment_end_s"],
        "padding_s": padding_s,
        "engine": separation.get_separation_engine().name,
        "vocals": result.vocals.name,
        "accompaniment": result.accompaniment.name,
    }
    (cache_dir / "manifest.json").write_text(json.dumps(manifest, indent=2),
                                             encoding="utf-8")
    media_ops.safe_unlink(input_wav)
    return cut_stem_cache(cut_id, padding_s)


def _restore_media_after_stop(media_id: int):
    """After a cancel: the media is fine if it's already playable, otherwise
    it never got a streamable file and is effectively dead."""
    db = get_db()
    row = db.execute("SELECT filename FROM media WHERE id=?", (media_id,)).fetchone()
    if row is None:
        return
    if row["filename"]:
        _set_media(media_id, "ready", "")
    else:
        _set_media(media_id, "error", "cancelled before the file was ready")


# ------------------------------------------------------------- separate

@handler("separate")
def _run_separate(ctx: JobContext, payload: dict):
    """Windowed Demucs separation for one cut, cached by media/time range."""
    cut_id = int(payload["cut_id"])
    padding_s = float(payload.get("padding_s", 3.0))
    cache = _ensure_cut_stems(ctx, cut_id, padding_s)
    if cache["exists"]:
        ctx.report("cached stems ready", progress=100)
        return


# ---------------------------------------------------------------- dub

def _dub_dir(dub_id: int) -> Path:
    d = media_ops.MEDIA_ROOT / "dubs" / str(dub_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _infer_segment_genders(ctx: JobContext, segs: list[dict], cache: dict,
                           cut_start: float):
    """Fill in each segment's speaker gender (for male/female voice choice) by
    measuring pitch on that segment's slice of the vocals stem. Only segments
    with no gender yet are touched, and results persist so a user can override
    them later (gender_source stays 'auto')."""
    todo = [s for s in segs if not s.get("gender")]
    if not todo:
        return
    db = get_db()
    vocals = cache.get("vocals")
    work = cache["dir"] / "_gender"
    work.mkdir(parents=True, exist_ok=True)
    for s in todo:
        ctx.check_cancel()
        guess = None
        if vocals and Path(vocals).exists():
            offset = max(0.0, float(s["start_s"]) - float(cache["start_s"]))
            dur = max(0.2, float(s["end_s"]) - float(s["start_s"]))
            slice_wav = work / f"seg_{s['id']}.wav"
            try:
                media_ops._run_ffmpeg([
                    "ffmpeg", "-y", "-ss", f"{offset:.3f}", "-t", f"{dur:.3f}",
                    "-i", str(vocals), "-ar", "22050", "-ac", "1",
                    "-c:a", "pcm_s16le", str(slice_wav),
                ], check_cancel=ctx.check_cancel, timeout=600)
                guess = gender_mod.estimate_gender(slice_wav)
            except Exception as e:
                log(f"gender inference failed for segment {s['id']}: {e}")
            finally:
                media_ops.safe_unlink(slice_wav)
        if guess:
            s["gender"] = guess
            db.execute(
                "UPDATE segments SET gender=?, gender_source='auto' "
                "WHERE id=? AND gender IS NULL", (guess, s["id"]))
    db.commit()
    shutil.rmtree(work, ignore_errors=True)


def _boundary_payload(boundary, segment_id: int, segment_offset_ms: int) -> dict:
    return {
        "segment_id": segment_id,
        "text": getattr(boundary, "text", ""),
        "offset_ms": segment_offset_ms + int(getattr(boundary, "offset_ms", 0) or 0),
        "duration_ms": int(getattr(boundary, "duration_ms", 0) or 0),
    }


@handler("dub")
def _run_dub(ctx: JobContext, payload: dict):
    """Generate translated speech and mix it over the cut's accompaniment stem."""
    dub_id = int(payload["dub_id"])
    db = get_db()
    db.execute("UPDATE dubs SET status='running', detail='starting', "
               "updated_at=datetime('now') WHERE id=?", (dub_id,))
    db.commit()
    try:
        row = db.execute("""
            SELECT d.*, ct.cut_id, ct.lang_code, l.tts_engine, l.tts_voice,
                   l.tts_voice_female, l.tts_voice_male
            FROM dubs d
            JOIN cut_translations ct ON ct.id=d.translation_id
            JOIN languages l ON l.code=ct.lang_code
            WHERE d.id=?""", (dub_id,)).fetchone()
        if not row:
            raise RuntimeError("dub not found")
        cut_id = int(row["cut_id"])
        default_voice = row["voice"] or row["tts_voice"]
        female_voice = row["tts_voice_female"] or default_voice
        male_voice = row["tts_voice_male"] or default_voice
        if not default_voice:
            raise RuntimeError(f"language {row['lang_code']} has no TTS voice configured")

        def voice_for(gender):
            if gender == "F":
                return female_voice
            if gender == "M":
                return male_voice
            return default_voice

        segs = db.execute("""
            SELECT s.id, s.start_s, s.end_s, s.gender, ts.text
            FROM cut_segments cs
            JOIN segments s ON s.id=cs.segment_id
            JOIN translation_segments ts
              ON ts.segment_id=s.id AND ts.translation_id=?
            WHERE cs.cut_id=?
            ORDER BY cs.position""", (row["translation_id"], cut_id)).fetchall()
        if not segs:
            raise RuntimeError("translation has no segments")
        segs = [dict(s) for s in segs]

        cut_start = min(float(s["start_s"]) for s in segs)
        cut_end = max(float(s["end_s"]) for s in segs)
        cut_duration = max(0.05, cut_end - cut_start)

        ctx.report("preparing accompaniment stem", progress=10)
        cache = _ensure_cut_stems(ctx, cut_id, 3.0)
        _infer_segment_genders(ctx, segs, cache, cut_start)
        work = _dub_dir(dub_id)
        base = work / "accompaniment_cut.wav"
        stem_offset = max(0.0, cut_start - cache["start_s"])
        media_ops._run_ffmpeg([
            "ffmpeg", "-y", "-ss", f"{stem_offset:.3f}", "-t", f"{cut_duration:.3f}",
            "-i", str(cache["accompaniment"]),
            "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(base),
        ], check_cancel=ctx.check_cancel, timeout=7200)

        boundaries = []
        speech_files = []
        engine = tts.get_tts_engine()
        for i, seg in enumerate(segs):
            text = (seg["text"] or "").strip()
            if not text:
                continue
            pct = 35 + (i / max(1, len(segs))) * 40
            seg_voice = voice_for(seg.get("gender"))
            ctx.report(f"synthesizing segment {i + 1}/{len(segs)} ({seg_voice})",
                       progress=pct)
            raw = work / f"tts_{i:03d}.mp3"
            result = engine.synthesize(text, seg_voice, raw)
            for b in result.word_boundaries:
                boundaries.append(_boundary_payload(
                    b, int(seg["id"]), int(round((float(seg["start_s"]) - cut_start) * 1000))))

            target = max(0.05, float(seg["end_s"]) - float(seg["start_s"]))
            raw_duration = media_ops.duration(result.audio_path) or target
            atempo = max(0.66, min(1.5, raw_duration / target))
            stretched = work / f"speech_{i:03d}.wav"
            media_ops._run_ffmpeg([
                "ffmpeg", "-y", "-i", str(result.audio_path),
                "-af", f"atempo={atempo:.4f}",
                "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(stretched),
            ], check_cancel=ctx.check_cancel, timeout=7200)
            speech_files.append({
                "path": stretched,
                "delay_ms": int(round((float(seg["start_s"]) - cut_start) * 1000)),
            })

        final = work / f"dub_{dub_id}.m4a"
        ctx.report("mixing dub with accompaniment", progress=85)
        if speech_files:
            cmd = ["ffmpeg", "-y", "-i", str(base)]
            for s in speech_files:
                cmd += ["-i", str(s["path"])]
            filters = []
            for i, s in enumerate(speech_files, start=1):
                filters.append(f"[{i}:a]adelay={s['delay_ms']}|{s['delay_ms']}[a{i}]")
            mix_inputs = "[0:a]" + "".join(f"[a{i}]" for i in range(1, len(speech_files) + 1))
            filters.append(
                f"{mix_inputs}amix=inputs={len(speech_files) + 1}:duration=first:"
                f"dropout_transition=0:normalize=0,"
                f"atrim=0:{cut_duration:.3f},asetpts=N/SR/TB[aout]")
            cmd += ["-filter_complex", ";".join(filters), "-map", "[aout]",
                    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(final)]
        else:
            cmd = ["ffmpeg", "-y", "-t", f"{cut_duration:.3f}", "-i", str(base),
                   "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(final)]
        media_ops._run_ffmpeg(cmd, check_cancel=ctx.check_cancel, timeout=7200)

        dur = media_ops.duration(final) or cut_duration
        db.execute("""
            UPDATE dubs SET status='done', filename=?, duration_s=?,
                word_boundaries_json=?, detail='ready', updated_at=datetime('now')
            WHERE id=?""",
            (str(final.relative_to(media_ops.MEDIA_ROOT)), dur,
             json.dumps(boundaries), dub_id))
        db.commit()
        ctx.report("dub ready", progress=100)
    except JobCancelled:
        db.execute("UPDATE dubs SET status='cancelled', detail='cancelled by user', "
                   "updated_at=datetime('now') WHERE id=?", (dub_id,))
        db.commit()
        raise
    except Exception as e:
        db.execute("UPDATE dubs SET status='failed', detail=?, "
                   "updated_at=datetime('now') WHERE id=?",
                   (str(e)[:500], dub_id))
        db.commit()
        raise


# ------------------------------------------------------------- download

@handler("download")
def _run_download(ctx: JobContext, payload: dict):
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError("yt-dlp is not installed. Run: pip install yt-dlp")

    media_id = ctx.media_id
    title = _media_title(media_id)
    url = payload["url"]
    dest = media_ops.media_dir(media_id)
    log(f"downloading '{title}': {url}")
    _set_media(media_id, "downloading")

    last = [-10.0]

    def hook(d):
        ctx.check_cancel()  # raising aborts the yt-dlp download
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                pct = d.get("downloaded_bytes", 0) / total * 100
                if pct - last[0] >= 2:
                    last[0] = pct
                    msg = f"downloading {pct:.0f}%"
                    ctx.report(msg, progress=pct)
                    _set_media(media_id, "downloading", msg)
                    log(f"'{title}' {msg}")
        elif d.get("status") == "finished":
            ctx.heartbeat()  # merging can take a while with no hook calls
            log(f"'{title}' download finished, merging…")

    opts = {
        # prefer h264 mp4 so the prepare step is a fast remux, not a re-encode
        "format": "bv*[ext=mp4][vcodec^=avc1]+ba[ext=m4a]/b[ext=mp4]/bestvideo+bestaudio/best",
        "outtmpl": str(dest / "raw.%(ext)s"),
        "progress_hooks": [hook],
        "noplaylist": True,
        "quiet": True, "no_warnings": True,
        "merge_output_format": "mp4",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # if the user didn't give a title, use the video's own
    db = get_db()
    row = db.execute("SELECT title FROM media WHERE id=?", (media_id,)).fetchone()
    if row and row["title"].startswith("Link import") and info.get("title"):
        db.execute("UPDATE media SET title=? WHERE id=?", (info["title"], media_id))
        db.commit()

    raw = next((f for f in dest.iterdir() if f.stem == "raw"), None)
    if raw is None:
        raise RuntimeError("download produced no file")

    enqueue("prepare", media_id, {
        "src": str(raw), "keep_src": False,
        "then_transcribe": payload.get("then_transcribe", True),
        "whisper": payload.get("whisper") or {},
    })


# -------------------------------------------------------------- prepare

@handler("prepare")
def _run_prepare(ctx: JobContext, payload: dict):
    media_id = ctx.media_id
    src = Path(payload["src"])
    if not src.exists():
        raise RuntimeError(f"source file not found: {src}")
    title = _media_title(media_id)
    _set_media(media_id, "preparing")
    log(f"preparing '{title}' ({src.name})")

    def on_progress(pct):
        msg = f"converting {pct:.0f}%"
        ctx.report(msg, progress=pct)
        _set_media(media_id, "preparing", msg)
        log(f"'{title}' {msg}")

    final, mtype, duration, mode = media_ops.prepare_for_streaming(
        src, media_id, keep_src=payload.get("keep_src", False),
        on_progress=on_progress, check_cancel=ctx.check_cancel)

    db = get_db()
    db.execute("UPDATE media SET type=?, filename=?, duration=? WHERE id=?",
               (mtype, final.name, duration, media_id))
    db.commit()
    log(f"'{title}' prepared ({mode}, {mtype})")

    has_segments = db.execute(
        "SELECT 1 FROM segments WHERE media_id=? LIMIT 1", (media_id,)).fetchone()
    if has_segments:
        _set_media(media_id, "ready")
    elif payload.get("then_transcribe"):
        _set_media(media_id, "queued_transcription")
        enqueue("transcribe", media_id, payload.get("whisper") or {})
    else:
        _set_media(media_id, "ready")


# ----------------------------------------------------------- transcribe

def _replace_track(db, media_id: int, track_name: str, lang_code: str = "") -> int:
    """Transcriptions live in their own track; re-running replaces only it."""
    row = db.execute("SELECT id FROM tracks WHERE media_id=? AND name=?",
                     (media_id, track_name)).fetchone()
    if row:
        db.execute("DELETE FROM segments WHERE track_id=?", (row["id"],))
        if lang_code:
            db.execute("UPDATE tracks SET lang_code=? WHERE id=?", (lang_code, row["id"]))
        return row["id"]
    return db.execute("INSERT INTO tracks (media_id, name, lang_code) VALUES (?,?,?)",
                      (media_id, track_name, lang_code)).lastrowid


def _whisper_settings():
    """Env config: RECOMPOSER_WHISPER_MODEL / _DEVICE / _COMPUTE."""
    return (os.environ.get("RECOMPOSER_WHISPER_MODEL", "small"),
            os.environ.get("RECOMPOSER_WHISPER_DEVICE", "auto"),
            os.environ.get("RECOMPOSER_WHISPER_COMPUTE", "auto"))


@handler("transcribe")
def _run_transcription(ctx: JobContext, payload: dict):
    media_id = ctx.media_id
    source = _find_source(media_id)
    if source is None:
        raise RuntimeError("source media file not found")
    title = _media_title(media_id)

    def stage(msg, pct=None):
        ctx.report(msg, progress=pct)
        _set_media(media_id, "transcribing", msg)
        log(f"transcribing '{title}': {msg}")

    # per-job settings win over env defaults
    model_name, device, compute = _whisper_settings()
    model_name = (payload.get("model") or "").strip() or model_name
    device = (payload.get("device") or "").strip() or device
    compute = (payload.get("compute") or "").strip() or compute
    language = (payload.get("language") or "").strip() or None

    stage("extracting audio", 2)
    wav = media_ops.extract_wav_for_transcription(media_id, source,
                                                  check_cancel=ctx.check_cancel)

    engine = None
    try:
        import whisperx  # noqa: F401
        engine = "whisperx"
    except ImportError:
        try:
            from faster_whisper import WhisperModel  # noqa: F401
            engine = "faster-whisper"
        except ImportError:
            raise RuntimeError(
                "no transcription engine installed. Run: pip install whisperx "
                "(recommended, accurate timestamps) or pip install faster-whisper "
                "— or upload a .srt subtitle file instead.")

    try:
        ctx.check_cancel()
        if engine == "whisperx":
            idx = _transcribe_whisperx(ctx, media_id, wav, model_name, device,
                                       compute, language, stage)
        else:
            idx = _transcribe_faster(ctx, media_id, wav, model_name, device,
                                     compute, language, stage)
    finally:
        media_ops.safe_unlink(wav)
    if idx == 0:
        raise RuntimeError("transcription produced no segments")
    _set_media(media_id, "ready")
    log(f"'{title}' transcription done ({engine}): {idx} segments")


def _transcribe_whisperx(ctx, media_id, wav, model_name, device, compute,
                         language, stage):
    """WhisperX: batched whisper + wav2vec2 forced alignment → precise timestamps."""
    import whisperx
    import torch

    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if compute == "auto":
        compute = "float16" if device == "cuda" else "int8"

    stage(f"loading whisperx model '{model_name}' ({device}) — first run downloads it", 5)
    model = whisperx.load_model(model_name, device, compute_type=compute,
                                language=language)
    audio = whisperx.load_audio(str(wav))

    ctx.check_cancel()
    stage("transcribing (whisperx)…", 25)
    result = model.transcribe(audio, batch_size=16 if device == "cuda" else 8)
    segs = result["segments"]

    ctx.check_cancel()
    stage("aligning timestamps (wav2vec2)…", 70)
    try:
        align_model, meta = whisperx.load_align_model(
            language_code=result["language"], device=device)
        segs = whisperx.align(segs, align_model, meta, audio, device,
                              return_char_alignments=False)["segments"]
    except Exception as e:  # no align model for this language etc.
        log(f"alignment unavailable ({e}); keeping whisper timestamps")

    stage("saving segments", 95)
    db = get_db()
    track_id = _replace_track(db, media_id, f"WhisperX ({model_name})",
                              result.get("language") or language or "")
    idx = 0
    for s in segs:
        text = (s.get("text") or "").strip()
        if not text or s.get("start") is None or s.get("end") is None:
            continue
        db.execute(
            "INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text) VALUES (?,?,?,?,?,?)",
            (media_id, track_id, idx, round(float(s["start"]), 3),
             round(float(s["end"]), 3), text))
        idx += 1
    db.commit()
    return idx


def _transcribe_faster(ctx, media_id, wav, model_name, device, compute,
                       language, stage):
    """Fallback engine: faster-whisper with streaming progress."""
    from faster_whisper import WhisperModel

    stage(f"loading whisper model '{model_name}' — first run downloads it", 5)
    model = WhisperModel(model_name, device=device, compute_type=compute)
    segments_iter, info = model.transcribe(str(wav), vad_filter=True,
                                           language=language)
    duration = getattr(info, "duration", None)

    db = get_db()
    track_id = _replace_track(db, media_id, f"Whisper ({model_name})", language or "")
    idx = 0
    last = -10.0
    for seg in segments_iter:
        ctx.check_cancel()
        text = seg.text.strip()
        if not text:
            continue
        db.execute(
            "INSERT INTO segments (media_id, track_id, idx, start_s, end_s, text) VALUES (?,?,?,?,?,?)",
            (media_id, track_id, idx, round(seg.start, 3), round(seg.end, 3), text))
        idx += 1
        if duration:
            pct = min(99, seg.end / duration * 100)
            if pct - last >= 2:
                last = pct
                db.commit()
                stage(f"transcribing {pct:.0f}% ({idx} segments)", pct)
        elif idx % 25 == 0:
            db.commit()
            ctx.report(f"transcribing — {idx} segments")
    db.commit()
    return idx


# -------------------------------------------------------- translation jobs

@handler("translate_track")
def _run_translate_track(ctx: JobContext, payload: dict):
    track_id = int(payload["track_id"])
    target_lang = (payload["target_lang"] or "").strip()
    if not target_lang:
        raise RuntimeError("target language is required")
    db = get_db()
    new_track_id = translation_ops.translate_track_to_new_track(
        db, track_id, target_lang,
        source_language=payload.get("source_language") or "auto",
        name=payload.get("name") or "",
        report=ctx.report)
    db.commit()
    ctx.report(f"created translated track {new_track_id}", progress=100)


@handler("translate_recomposition")
def _run_translate_recomposition(ctx: JobContext, payload: dict):
    recomp_id = int(payload["recomp_id"])
    lang_code = (payload["lang_code"] or "").strip()
    if not lang_code:
        raise RuntimeError("target language is required")
    db = get_db()
    rows = translation_ops.translate_recomposition_cuts(
        db, recomp_id, lang_code,
        source_language=payload.get("source_language") or "auto",
        created_by=payload.get("user_id"),
        overwrite=bool(payload.get("overwrite")),
        report=ctx.report)
    db.commit()
    created = sum(1 for r in rows if r["created"])
    ctx.report(f"ready: {created} new translation(s), {len(rows) - created} reused",
               progress=100)


# --------------------------------------------------------------- export

@handler("export")
def _run_export(ctx: JobContext, payload: dict):
    recomp_id = payload["recomp_id"]
    audio_mode = (payload.get("audio_mode") or "sequence").strip()
    target_lang = (payload.get("target_lang") or "").strip()
    quality = (payload.get("quality") or "720p").strip()
    db = get_db()
    recomp = db.execute("SELECT * FROM recompositions WHERE id=?", (recomp_id,)).fetchone()
    if not recomp:
        raise RuntimeError("recomposition not found")
    rows = db.execute("""
        SELECT c.id AS cut_id, m.id AS media_id, m.filename, m.type,
               rc.audio_mode, rc.dub_id, d.filename AS dub_filename,
               MIN(s.start_s) AS start_s, MAX(s.end_s) AS end_s
        FROM recomp_cuts rc
        JOIN cuts c ON c.id = rc.cut_id
        JOIN media m ON m.id = c.media_id
        LEFT JOIN dubs d ON d.id = rc.dub_id
        JOIN cut_segments cs ON cs.cut_id = c.id
        JOIN segments s ON s.id = cs.segment_id
        WHERE rc.recomp_id=?
        GROUP BY rc.position, c.id, m.id, m.filename, m.type,
                 rc.audio_mode, rc.dub_id, d.filename
        ORDER BY rc.position""", (recomp_id,)).fetchall()
    if not rows:
        raise RuntimeError("this recomposition has no cuts")

    cuts = []
    for r in rows:
        src = media_ops.media_dir(r["media_id"]) / r["filename"]
        if not src.exists():
            raise RuntimeError(f"source file missing for media {r['media_id']}")
        audio_src = None
        if audio_mode == "target_dub":
            if not target_lang:
                raise RuntimeError("target language is required for translated dub export")
            dub = db.execute("""
                SELECT d.*
                FROM dubs d
                JOIN cut_translations ct ON ct.id=d.translation_id
                WHERE ct.cut_id=? AND ct.lang_code=? AND d.status='done'
                      AND d.filename<>''
                ORDER BY d.id DESC LIMIT 1""",
                (r["cut_id"], target_lang)).fetchone()
            if not dub:
                raise RuntimeError(
                    f"no ready {target_lang} dub for cut {r['cut_id']}; "
                    "generate dubs before exporting")
            audio_src = media_ops.MEDIA_ROOT / dub["filename"]
            if not audio_src.exists():
                raise RuntimeError(f"ready dub file missing for cut {r['cut_id']}")
        elif audio_mode == "sequence" and r["audio_mode"] == "dub":
            if not r["dub_filename"]:
                raise RuntimeError(f"selected dub missing for cut {r['cut_id']}")
            audio_src = media_ops.MEDIA_ROOT / r["dub_filename"]
            if not audio_src.exists():
                raise RuntimeError(f"selected dub file missing for cut {r['cut_id']}")
        elif audio_mode not in ("sequence", "original", "target_dub"):
            raise RuntimeError("audio_mode must be sequence, original, or target_dub")
        cuts.append({"src": str(src), "start_s": r["start_s"], "end_s": r["end_s"],
                     "is_video": r["type"] == "video",
                     "audio_src": str(audio_src) if audio_src else None})

    title = recomp["title"]
    log(f"export '{title}': {len(cuts)} cuts ({quality}, {audio_mode})")

    def prog(msg, pct=None):
        ctx.report(msg, progress=pct)
        log(f"export '{title}': {msg}")

    final = media_ops.export_recomposition(recomp_id, title, cuts, on_progress=prog,
                                           check_cancel=ctx.check_cancel,
                                           quality=quality)
    log(f"export '{title}' done → {final}")
    ctx.report(f"done: {final.name}", progress=100)


# ----------------------------------------------------- cancel & retry API

def request_cancel(job_id: int) -> dict:
    """Queued jobs are cancelled instantly; running jobs get cancel_requested
    and stop at their next check_cancel()."""
    db = get_db()
    row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        return {"error": "job not found"}
    if row["status"] in ("done", "failed", "cancelled"):
        return {"error": f"job is already {row['status']}"}
    # atomic, so we can't race the claim loop: only one of us gets the row
    cur = db.execute(
        "UPDATE jobs SET status='cancelled', detail='cancelled by user', "
        "finished_at=datetime('now'), updated_at=datetime('now') "
        "WHERE id=? AND status='queued'", (job_id,))
    db.commit()
    if cur.rowcount:
        if row["media_id"]:
            _restore_media_after_stop(row["media_id"])
        return {"status": "cancelled"}
    db.execute("UPDATE jobs SET cancel_requested=1, updated_at=datetime('now') WHERE id=?",
               (job_id,))
    db.commit()
    return {"status": "cancelling"}


_RETRY_MEDIA_STATUS = {"download": "downloading", "prepare": "preparing",
                       "transcribe": "queued_transcription"}


def retry(job_id: int) -> dict:
    db = get_db()
    row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        return {"error": "job not found"}
    if row["status"] not in ("failed", "cancelled"):
        return {"error": "only failed or cancelled jobs can be retried"}
    db.execute(
        "UPDATE jobs SET status='queued', attempts=0, cancel_requested=0, "
        "worker_id=NULL, lease_until=NULL, finished_at=NULL, progress=NULL, "
        "detail='requeued', updated_at=datetime('now') WHERE id=?", (job_id,))
    db.commit()
    if row["media_id"] and row["kind"] in _RETRY_MEDIA_STATUS:
        _set_media(row["media_id"], _RETRY_MEDIA_STATUS[row["kind"]], "requeued")
    wake()
    return {"status": "queued"}


# --------------------------------------------------------------- worker

def _claim_next():
    """Claim the next runnable job with an optimistic UPDATE. Also adopts
    running jobs whose lease expired (their worker died)."""
    db = get_db()
    for _ in range(10):
        row = db.execute("""
            SELECT id FROM jobs
            WHERE (status='queued' AND cancel_requested=0)
               OR (status='running' AND lease_until IS NOT NULL
                   AND lease_until < datetime('now'))
            ORDER BY priority DESC, id LIMIT 1""").fetchone()
        if row is None:
            return None
        cur = db.execute("""
            UPDATE jobs SET status='running', worker_id=?,
                   lease_until=datetime('now', ?),
                   started_at=COALESCE(started_at, datetime('now')),
                   attempts=attempts+1, updated_at=datetime('now')
            WHERE id=? AND ((status='queued' AND cancel_requested=0)
                OR (status='running' AND lease_until < datetime('now')))""",
            (WORKER_ID, f"+{LEASE_SECONDS} seconds", row["id"]))
        db.commit()
        if cur.rowcount:
            return db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()
    return None


def _finish(job_id: int, status: str, detail: str | None = None):
    db = get_db()
    if detail is None:  # keep the handler's last detail (e.g. "done: file.mp4")
        db.execute("UPDATE jobs SET status=?, finished_at=datetime('now'), "
                   "updated_at=datetime('now') WHERE id=?", (status, job_id))
    else:
        db.execute("UPDATE jobs SET status=?, detail=?, finished_at=datetime('now'), "
                   "updated_at=datetime('now') WHERE id=?", (status, detail, job_id))
    db.commit()


def _execute(job):
    job_id = job["id"]
    payload = json.loads(job["payload"] or "{}")
    ctx = JobContext(job)
    try:
        fn = HANDLERS.get(job["kind"])
        if fn is None:
            raise RuntimeError(f"unknown job kind {job['kind']}")
        ctx.check_cancel()
        fn(ctx, payload)
        db = get_db()
        db.execute("UPDATE jobs SET status='done', progress=100, "
                   "finished_at=datetime('now'), updated_at=datetime('now') WHERE id=?",
                   (job_id,))
        db.commit()
    except JobCancelled:
        log(f"job {job_id} ({job['kind']}) cancelled")
        _finish(job_id, "cancelled", "cancelled by user")
        if job["media_id"]:
            _restore_media_after_stop(job["media_id"])
    except Exception as e:
        traceback.print_exc()
        row = get_db().execute("SELECT attempts, max_attempts FROM jobs WHERE id=?",
                               (job_id,)).fetchone()
        if row and row["attempts"] < row["max_attempts"]:
            log(f"JOB ERROR ({job['kind']}), will retry: {e}")
            db = get_db()
            db.execute(
                "UPDATE jobs SET status='queued', worker_id=NULL, lease_until=NULL, "
                "detail=?, updated_at=datetime('now') WHERE id=?",
                (f"retrying after error: {str(e)[:400]}", job_id))
            db.commit()
            wake()
        else:
            log(f"JOB FAILED ({job['kind']}): {e}")
            _finish(job_id, "failed", str(e)[:500])
            if job["media_id"]:
                _set_media(job["media_id"], "error", str(e)[:500])


def _worker():
    while True:
        job = _claim_next()
        if job is None:
            _wake.wait(timeout=POLL_SECONDS)
            _wake.clear()
            continue
        _execute(job)


def start_worker():
    global _started
    if _started:
        return
    _started = True
    db = get_db()
    # jobs that kept getting interrupted are dead; everything else re-runs
    db.execute("UPDATE jobs SET status='failed', detail='interrupted too many times', "
               "finished_at=datetime('now') WHERE status IN ('queued','running') "
               "AND attempts >= max_attempts + 2")
    db.execute("UPDATE jobs SET status='queued', worker_id=NULL, lease_until=NULL "
               "WHERE status='running'")
    db.commit()
    t = threading.Thread(target=_worker, daemon=True, name="recomposer-worker")
    t.start()
    wake()
