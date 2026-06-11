# Recomposer (Phase 1)

Local studio for turning movies, podcasts and lectures into searchable subtitle segments, grouping them into **Cuts**, and sequencing cuts from multiple sources into playable **Recompositions** — shared with your brother over your home WiFi.

## Requirements (on your laptop)

- Python 3.10+
- ffmpeg on your PATH (`ffmpeg -version` should work) — https://ffmpeg.org/download.html
- Optional, for auto-transcribing media that has no subtitles:
  `pip install faster-whisper` (first transcription downloads the model, ~500 MB)

## Run it

```
cd app
pip install -r requirements.txt
python run.py
```

It prints two URLs:

```
You:          http://localhost:8000
Your brother: http://192.168.x.x:8000   (same WiFi)
```

Your brother opens the second URL in his browser. You both work on the same library, cuts and recompositions in real time. If his browser can't reach it, allow Python/port 8000 through your OS firewall.

The frontend is pre-built (`frontend/dist`), so nothing else is needed. If you ever change frontend code: `cd frontend && npm install && npm run build`.

## How to use it

1. **Library** → *Add media*. Attach a `.srt`/`.vtt` if you have one; otherwise the file is queued for Whisper transcription (status shows on the card). Files are remuxed once on upload to be instantly seekable.
2. Open a ready media → the **cut maker**: the transcript is flowing text. Click a line to play it, shift-click to extend a contiguous selection, *Play selection* to check it, then **Save as Cut** (`s`) with a title, tags and folder.
3. **Cuts** tab → search every cut by title or spoken text (full-text), filter by folder/tag, preview any cut, multi-select → *Add to recomposition*.
4. **Studio** tab → open a recomposition: search cuts on the left, add them, drag to reorder, **Play all** — playback jumps across the source files automatically.

## Where things live

- `recomposer.db` — the whole database (one SQLite file). Back it up by copying it.
- `media_store/<id>/` — one folder per media file.
- Delete rights: only the person who added a media file can delete it; everything else is shared.

## Project layout

```
app/
  run.py                 start here
  backend/
    main.py              API + streaming + serves the frontend
    db.py                SQLite schema (FTS5 search index included)
    jobs.py              background worker (transcription queue)
    media_ops.py         ffmpeg probe/remux/extract
    srt_parser.py        .srt/.vtt parsing
  frontend/              React + Vite + Tailwind (dist/ is the build)
  media_store/           your media (created on first upload)
```

## What's next (per the concept doc)

Phase 2: export a recomposition to a real `.mp4`/`.wav` (ffmpeg concat), crossfade smoothing at joins, background-audio layer, YouTube import. Phase 3: translation + dubbing. Phase 4: community beyond the LAN.
