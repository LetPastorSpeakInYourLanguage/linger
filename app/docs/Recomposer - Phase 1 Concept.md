# Recomposer — Phase 1 Workable Concept

## The idea in one sentence

A local studio app that turns your media library (movies, podcasts, lectures) into a searchable database of subtitle segments, lets you group segments into **Cuts** (atomic, self-sufficient moments), and sequence Cuts from multiple sources into **Recompositions** you can instantly preview — shared with your brother over your home WiFi.

## What we are NOT building yet

Your notes contain ~6 products. To get a working app, everything below is explicitly deferred (see Roadmap):

- Translation, proofreading, TTS, dubbing
- Public community, upvotes, comments, versioning/cloning
- Google Colab / Drive execution, OAuth
- AI suggestions, topic segmentation, vector search, "flow state" switching
- Posterizer, vocal splitting, background-audio synthesis
- Rendered .mp4 export (phase 2 — preview comes first)

---

## Core concepts (the data model)

Four nouns. Everything in the app is one of these.

1. **Media** — an uploaded video/audio file. Stored once on disk, never duplicated.
2. **Segment** — one subtitle line: `{text, start, end, media_id}`. Created by parsing an uploaded `.srt` or by Whisper transcription. Segments are the searchable atoms.
3. **Cut** (your "aggregate") — an ordered sequence of consecutive segments from one Media that communicates one self-sufficient idea ("the confession scene"). Cuts carry a title, tags, and live in folders. **Cuts are the unit of value in the whole system.**
4. **Recomposition** — a titled, ordered sequence of Cuts, possibly from many different Media. Playable end-to-end.

```
Media 1 ──segments──┐
Media 2 ──segments──┼──> Cuts (tagged, foldered) ──> Recomposition (sequence)
Media 3 ──segments──┘
```

Simplifications vs. your notes (deliberate, for phase 1):

- **No canonical/deduplicated sentence repository.** Segments belong to their media. The global unique-sentence table only pays off with translation and cross-sourcing — both deferred. The schema won't block adding it later.
- **Cuts are sequential only.** Non-sequential "pick sentences from here and there" groupings need TTS to be playable — deferred with TTS.
- **No recompositions-inside-recompositions.** A recomposition is a flat list of cuts.

### SQLite schema (8 tables)

```
users           (id, name, color)                  -- pick-your-name login, no passwords
media           (id, title, type, filepath, duration, status, added_by)
segments        (id, media_id, idx, start_s, end_s, text)
cuts            (id, media_id, title, note, folder_id, created_by)
cut_segments    (cut_id, segment_id, position)
tags            (id, name)        + cut_tags (cut_id, tag_id)
folders         (id, name, parent_id)
recompositions  (id, title, created_by)  + recomp_cuts (recomp_id, cut_id, position)
```

`media.status` drives the pipeline: `uploaded → extracting_audio → transcribing → ready` (or `ready` immediately if an `.srt` was provided).

---

## Architecture: one laptop, one process

```
Your laptop (the host)                       Brother's laptop
┌────────────────────────────────┐
│  FastAPI app  (port 8000)      │           Browser →
│  ├─ serves React build (UI)    │ ◄──WiFi── http://192.168.x.x:8000
│  ├─ REST API + static media    │
│  ├─ SQLite (one file)          │
│  └─ background worker thread   │
│      (ffmpeg / faster-whisper) │
│  media_store/{media_id}/       │
└────────────────────────────────┘
```

- **One server, one database, zero sync logic.** Your brother just opens your IP in his browser. You both see the same library, cuts, and recompositions live. "Community sharing" in phase 1 = shared workspace + `created_by` attribution on everything.
- **Login** = pick your name from a list (stored in a cookie). No passwords on a home network.
- **Background jobs** = a plain Python queue + one worker thread inside the FastAPI process. No Redis, no Celery. Job rows in SQLite give you the visible task queue your notes wanted (status, ordering, errors).
- **Startup** = one command (`python run.py`), which prints the LAN URL to share.

### Stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python + FastAPI | Your notes already standardized on it |
| DB | SQLite | Single file, zero admin, fine for 2 users |
| Transcription | faster-whisper (`small` model) | Pip-installable, runs on CPU; WhisperX is a swap-in later if you want word-level timestamps |
| Media ops | ffmpeg | Audio extraction, later export |
| Frontend | React + Vite + shadcn/ui, Tailwind | Matches your v0 prototype direction |
| Preview | Plain HTML5 `<video>`/`<audio>` + HTTP Range requests | See below — no HLS needed in phase 1 |

### Preview: efficient retrieval without HLS

Your notes debated client-side HLS prep and dynamic `.m3u8` generation. **Skip it for phase 1.** Browsers natively seek into large MP4s via HTTP Range requests, and FastAPI serves ranges easily. The player is a thin controller:

```
for each cut in recomposition:
    set <video>.src to that cut's media URL (if changed)
    seek to cut.start, play, pause at cut.end, advance
```

Seeks on a LAN are near-instant. The one requirement: on upload, ffmpeg remuxes media to seek-friendly MP4 (`-movflags +faststart`, re-encode only if codec is browser-hostile). One-time cost, then every preview is free. HLS becomes worth it only if/when this is ever served over the internet.

Searchable subtitle text is just SQLite FTS5 full-text index over `segments.text` — fast fuzzy-ish search with zero extra infrastructure.

---

## The four screens

**1. Library** — grid of media with status badges (transcribing… / ready). "Add Media" accepts video/audio + optional `.srt`; no `.srt` queues a transcription job. Shows the job queue.

**2. Media view (Cut maker)** — player on top, transcript below rendered as flowing text (your note: "should feel like a transcript, not cards"). Hover highlights a segment with a start–end tooltip; click sets an anchor, shift/drag-click extends a contiguous selection; selection plays back instantly; "Save as Cut" names it, tags it, files it into a folder. Clicking any segment seeks the player.

**3. Cut browser** — folder tree + tag filter + FTS search across all cut titles and their segment text, from all media. Each result plays inline. Multi-select → "Add to Recomposition" (modal picks which one).

**4. Recomposition studio** — left: searchable cut browser (same component). Right: the sequence as a vertical playlist — drag to reorder, remove, click to play from any cut. Top: full preview play-through. This is the simple, fixed-layout version; the Adobe-style dockable-panel system is a later enhancement, on purpose — dynamic layout engines are a project of their own and phase 1 must ship.

---

## Roadmap

**Phase 0 — Skeleton (the walking app)**
FastAPI + SQLite + React shell, name-login, upload media with `.srt`, parse segments, Library + Media view with seek-on-click. *Milestone: you can watch your media and click around the transcript over WiFi from two laptops.*

**Phase 1 — The core loop (this document)**
Transcription jobs (faster-whisper), FTS search, Cuts with tags/folders, Cut browser, Recomposition studio with sequenced preview. *Milestone: you build a real romance-scenes recomposition from 3 movies and your brother watches it from his laptop.*

**Phase 2 — Make it real media**
FFmpeg export job: recomposition → single `.mp4`/`.wav` (concat of cut ranges). Then audio smoothing at joins (silence-point trimming + crossfade), optional bg-audio layer with length-matching. YouTube import via yt-dlp.

**Phase 3 — Language**
Canonical sentence table, machine translation loading, the Proofreader (TanStack table) and in-context Cut translation, TTS fallback. This is where the central sentence/aggregate repo from your notes gets built — on top of a proven core.

**Phase 4 — Community beyond the LAN**
Accounts, sharing/cloning/versioning, votes and comments, contributions and analytics. Only now do deployment questions matter.

### Phase 1 build order (what we attack one by one)

1. Project scaffold, SQLite schema, name-login
2. Upload endpoint + ffmpeg remux + `.srt` parser → segments
3. Library screen + media streaming with Range support
4. Media view: transcript rendering, hover/select, seek-on-click
5. Transcription job queue + faster-whisper worker + status UI
6. Cuts: create from selection, tags, folders
7. FTS5 search + Cut browser
8. Recompositions: CRUD, drag ordering, sequenced preview player
9. Polish pass: keyboard shortcuts for the cut maker, attribution display, error states

Each step leaves the app runnable; nothing depends on a later step.

---

## Open items (decide as we hit them, none block starting)

- Whisper model size vs. your laptop's specs (start `small`, adjust)
- Whether brother can delete media or only the creator (suggest: creator-only delete, everything else shared)
- Re-encode policy for exotic codecs (mkv/hevc) — detect and re-encode on upload vs. reject
