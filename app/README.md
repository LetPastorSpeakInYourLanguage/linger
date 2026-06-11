# Recomposer (Phase 1)

Local studio for turning movies, podcasts and lectures into searchable subtitle segments, grouping them into **Cuts**, and sequencing cuts from multiple sources into playable **Recompositions** — shared with your brother over your home WiFi.

## Requirements (on your laptop)

- Python 3.10+
- ffmpeg on your PATH (`ffmpeg -version` should work) — https://ffmpeg.org/download.html
- `pip install -r requirements.txt` now includes **WhisperX** (transcription with
  accurate word-level timestamps via forced alignment; first run downloads models)
  and **yt-dlp** (link imports). If WhisperX won't install, `pip install faster-whisper`
  is a lighter fallback — the app uses whichever it finds (WhisperX preferred).

### Whisper configuration (optional, via environment variables)

| variable | default | values |
|---|---|---|
| `RECOMPOSER_WHISPER_MODEL` | `small` | `tiny`, `base`, `small`, `medium`, `large-v3` — bigger is more accurate but slower |
| `RECOMPOSER_WHISPER_DEVICE` | `auto` | `cpu`, `cuda` (NVIDIA GPU) |
| `RECOMPOSER_WHISPER_COMPUTE` | `auto` | e.g. `int8` (fast CPU), `float16` (GPU) |

Example (PowerShell): `$env:RECOMPOSER_WHISPER_MODEL="medium"; python run.py`

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

1. **Library** → *Add media*. Three ways in:
   - **Upload file** — browser upload with a progress bar. Fine for small files.
   - **From this PC** — paste the file's full path (e.g. `D:\movies\film.mp4`). Fastest: no upload copy, your original is read in place and never modified or deleted.
   - **From link** — paste a YouTube/public video URL (needs `pip install yt-dlp`).

   Attach a `.srt`/`.vtt` if you have one; otherwise the file is queued for Whisper transcription. Every import is converted once in the background into an instantly-seekable file: h264 video is a fast remux (disk speed), anything else is re-encoded with percent progress shown on the media card **and** in the server terminal. Adding media returns immediately — watch the card.

   **Subtitle tracks**: one media can hold several subtitle sets (e.g. an uploaded `.srt` *and* a Whisper transcription, or two languages). Switch tracks with the dropdown in the media view, add more with **＋ subtitle** (upload or host path). Cuts remember their segments and always play from the same source media, whatever track they came from. Whisper writes into its own track (`Whisper (model)`), so re-transcribing never touches your edited subtitles.

   **Subtitle editor** (`✎ edit` in the media view): click any line to fix its text or timing — the **⏱** buttons grab the player's current position, so you can scrub to the right moment and stamp it. Insert lines (＋), delete lines (✕ — warns if cuts use them), and run **regex batch operations** on the whole track: *Preview* highlights matches, *Replace* rewrites text (an empty result deletes the line), *Delete matched* drops every matching line. E.g. pattern `\[.*?\]` removes bracketed sound effects.
2. Open a ready media → the **cut maker**: video + flowing transcript on the left, a resizable tabbed panel on the right.
   - *Selecting lines*: click a line to play it; extend across lines with shift-click, **shift-↓/↑**, or the **⊕ prev / ⊕ next** buttons. *Play selection* to check it, then **Save as Cut** (`s`).
   - *🔍 Search tab*: searches this transcript — **fuzzy by default**, so typos still find the line. Hits are underlined in the transcript; clicking one scrolls to it and seeks the player.
   - *✂ Cuts tab*: every cut made from this media — play it in the main player, show it in the transcript, edit or delete it.
   - Shortcuts: `space` play/pause · `←/→` seek 5s · `shift-↑/↓` extend selection · `s` save cut · `esc` clear.
3. **Cuts** tab → left: all cuts with a filter engine — add any mix of **#tag / 📁 folder / 🎬 media** filters via searchable pickers (chips show what's active, one click removes). The tag/folder/media labels on each cut card are clickable and add that filter. Right (resizable): **transcript search across every media file in the library** — fuzzy, with preview popups and "open media ↗" jumping straight to that line.
4. **Studio** tab → open a recomposition: cut browser on the left (resizable, same filter engine), sequence on the right. Drag to reorder, **Play all** (playback is double-buffered — the next cut's file is preloaded so switching media doesn't flash), **🔁 loop** any cut to immerse. **Right-click a sequence item** to filter the browser by that cut's media, folder or tags. Shortcuts work from anywhere: `space` play/pause · `←/→` seek · `↑/↓` previous/next cut · `L` toggle loop · `esc` closes any popup (playback resumes).
5. **⬇ Export** (in the recomposition editor) renders the whole sequence into one real file — `.mp4` (1280×720, h264+aac) if any cut has video, `.wav` if it's audio-only. Audio-only cuts inside a video export get a black screen; mute video gets silence. Progress shows next to the button and in the terminal; finished files appear as download links and live in `media_store/exports/`.

Track deletion is protected: you can't delete a media's only subtitle track, nor a track that cuts were made from (delete those cuts first).

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
    db.py                SQLite schema (FTS5 exact + trigram fuzzy indexes)
    search.py            search engine: exact FTS5 + trigram fuzzy re-ranking
    jobs.py              background worker (download → prepare → transcribe)
    media_ops.py         ffmpeg probe/remux/re-encode with progress
    srt_parser.py        .srt/.vtt parsing
  frontend/              React + Vite + Tailwind (dist/ is the build)
  media_store/           your media (created on first upload)
```

## What's next (per the concept doc)

Phase 2: export a recomposition to a real `.mp4`/`.wav` (ffmpeg concat), crossfade smoothing at joins, background-audio layer. Phase 3: translation + dubbing. Phase 4: community beyond the LAN. (YouTube import via yt-dlp was pulled forward into Phase 1 — done.)
