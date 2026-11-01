# Quick start

## 1. Install the prerequisites (once)

| | Windows | macOS | Linux (Debian/Ubuntu) |
|---|---|---|---|
| Python 3.10+ | `winget install Python.Python.3.12` | `brew install python@3.12` | `sudo apt install python3 python3-venv` |
| ffmpeg (video analysis + rendering) | `winget install Gyan.FFmpeg` | `brew install ffmpeg` | `sudo apt install ffmpeg` |
| git | `winget install Git.Git` | `xcode-select --install` | `sudo apt install git` |

Open a **new** terminal afterwards and check `python --version` and `ffmpeg -version`.

## 2. Install storylens

```bash
git clone <this repository> linger
cd linger/storylens
python -m venv .venv
# Windows (PowerShell):  .venv\Scripts\Activate.ps1      macOS/Linux:  source .venv/bin/activate
pip install -e ".[voice]"            # neural voice (Kokoro) + subtitle re-sync (Silero VAD)
# optional offline system voice fallback:  pip install -e ".[voice,system-voice]"
```

The Kokoro voice model (~350 MB) and the Silero VAD model (~2 MB) download automatically from GitHub the first
time they are needed, into `<workspace>/.models`.

## 3. Check everything works

```bash
storylens demo
```

This creates the workspace `~/storylens-workspace`, adds a short original sample story (with a generated test
video) and a two-episode sample podcast, then runs understanding and several recaps: main story, Victor's story,
"Leo being a good friend", a podcast topic supercut, and a cross-source clips recap. All tasks are answered by
the **built-in offline heuristic**, so the output is crude, but it proves ffmpeg, voices and rendering work.
`storylens demo --claude` runs the same demo with real tasks for Claude.

## 4. Start storylens and connect the Claude desktop app

```bash
storylens serve           # → http://127.0.0.1:8765   (--port to change; -w PATH for another workspace)
```

`serve` runs the web app **and** the folder watcher. If you don't want the web app, use `storylens watch`.

In the **Claude desktop app**, give Claude access to the workspace folder (`~/storylens-workspace`, or the path
shown on the Settings page), then say:

> **Do the storylens queue.**

Claude reads `CLAUDE.md` in that folder (storylens writes it) and from then on knows the whole protocol:
- **Tasks:** `tasks/QUEUE.md` lists what is waiting. Claude answers each `TASK.md` with an `answer.json`.
- **Requests:** Claude can start work itself (add a title, understand, build a lens, make a recap, search
  everything) by writing small JSON files into `requests/new/`.
- **Catalog:** `CATALOG.md` tells Claude what already exists.

Details: [AGENTIC.md](AGENTIC.md). The web app's **Claude tasks** page shows the same queue. It also lets you copy
a task into any Claude chat and paste the answer back.

## 5. Your first title

In the web app (or ask Claude, e.g. *"add D:\Shows\My Show as a series with cast Ana, Luis, Marta and understand
it"*):

1. **Library → Add title.** Give a name, film or series, and optionally the main character names (cast) and a
   folder to scan. The scan pairs `Movie.mkv` with `Movie.srt` / `Movie.en.srt` and detects `S01E02` episode numbers.
   You can also add single files by path or upload a subtitle file. Files are read in place and never modified.
2. **Overview → Understand.** storylens queues one task per part of every episode (about 220 subtitle lines each),
   then an integration task. Ask Claude to do the queue. When the job pauses at **G1**, review the logline,
   characters, turning points and spine. Fix things in **Story** (tiers) or the title instructions, then approve.
3. Explore **Story**, **Characters** and **Fact ledger**: every beat and fact links back to its subtitle lines and
   the video.
4. **Lenses**: build the main story, a character's story, a trait compilation ("being a good friend" + a
   character; tick *deep sweep* for exhaustive), a storyline, a topic, or a speaker's pattern.
5. **Make a recap**: pick a lens, style, duration, voice and review mode, then add instructions.
   - Claude writes the script, then storylens checks every citation and quote.
   - The job pauses at **G2** with the script and each segment's verdict. Edit text inline, approve, or ask for a
     revision with notes.
   - It pauses at **G3** with the rendered video.
   - Results are kept in the job's `artifacts/`.

## Podcasts, talk shows, sermons

1. **Add title** with kind `podcast` / `talkshow` / `sermon` / `lecture`, and put the speaker names in *cast*
   (host, guests, preacher). Point *scan folder* at the episodes. Audio files (`.mp3/.m4a/...`) pair with transcripts
   (`.srt/.vtt`, or `.txt/.md` lines like `[12:34] text`, or Whisper/AssemblyAI `.json`) by file name.
2. **Understand**: segments, points and a **claim ledger** (who said what, topics, stance) for every episode.
3. **Lenses → "What someone said about a topic"** (speaker + topic), then **Make a recap → "Clips only — no
   narrator"**: a supercut of the speakers' own words with lower thirds.
   - **"How a speaker builds ideas (pattern)"** shows the speaker's recurring moves as clips labelled by step.
   - A **main** lens with **Short & direct** and a 4–5 minute duration narrates the gist of a sermon or episode.
4. **Explore** (top menu): search *everything you have understood* (films, series, podcasts, sermons) at the level of
   title / episode / point / claim / line. Create **collections** and build cross-source lenses and recaps.

No transcript? Make subtitles first. linger's main app can transcribe with WhisperX, or use any Whisper tool and
export `.srt` or `.json`.

## CLI cheatsheet

```bash
storylens add "My Show" --kind series --folder "D:\Shows\My Show\Season 1" --cast "Ana,Luis,Marta"
storylens understand my-show                         # interactive gate in the terminal (or approve in the UI)
storylens lens my-show "character:Marta"
storylens lens my-show "trait:Luis/being a good friend" --deep
storylens recap my-show --lens main --style recap_channel --duration 600
storylens recap my-show --lens "character:Marta" --style character --duration 180 --autopilot
storylens jobs | storylens tasks | storylens approve <job> G2_script | storylens send <job> "less snark"
storylens search my-show "wedding"
storylens add "Grace Church" --kind sermon --folder "D:\Sermons" --cast "Pastor Ruth Adeyemi"
storylens lens grace-church "topic:Pastor Ruth Adeyemi/women and marriage"
storylens recap grace-church --lens "topic:Pastor Ruth Adeyemi/women and marriage" --style clips --duration 300
storylens find "meaning of life" --level title                  # which sources discuss it (all titles)
storylens find "meaning of life" --level claim --speaker Peterson
storylens collection create "Philosophy" --titles within-reason,long-table
storylens lens x "topic:Alex O'Connor/the meaning of life" --collection philosophy
storylens recap x --collection philosophy --lens "topic:/free will" --style clips --duration 600
storylens recap grace-church --lens "pattern:Pastor Ruth Adeyemi" --style clips --duration 240
storylens recap grace-church --lens main --style short_direct --duration 270 --review   # the gist, < 5 min
storylens request '{"do": "find", "query": "forgiveness", "level": "claim"}'           # anything Claude can request
storylens watch                                       # run requests/new/*.json without the web app
storylens --offline recap my-show ...                 # answer tasks with the offline heuristic (testing only)
```

CLI commands that need thinking wait until Claude has answered their tasks. They print where the queue is every
30 s.

Review modes:
- `gates` (default): a human approves G1/G2/G3.
- `--autopilot`: gates pass automatically when their metrics hold (no unsupported claims, no outside-knowledge
  leakage, duration within tolerance), otherwise a human decides.
- `--yes` / `auto`: approve everything, with warnings logged.

## Settings (`<workspace>/settings.json`, or the Settings page)

| key | default | meaning |
|---|---|---|
| `autonomy` | `gates` | `gates` / `autopilot` / `auto` |
| `chunk_lines` | `220` | subtitle lines per understanding task: bigger means fewer, longer tasks for Claude |
| `vision` | `off` | `gaps`: one image task per media describing dialogue-free stretches (action, title cards) |
| `review` | `false` | an extra Claude review task for every script (the automatic checks always run) |
| `tts`, `voice` | `auto`, `am_michael` | `kokoro` / `system` / `none` (captions) |
| `answerer` | `claude` | `mock` = the offline heuristic (demo/tests); also `--offline` or `STORYLENS_ANSWERER=mock` |

## How much work is it for Claude?

Understanding is the big, one-time step per title, and it is kept per version.

| media | tasks |
|---|---|
| feature film | ~6–8 understanding tasks + 1 integration |
| 22-minute episode | ~2–3 tasks |
| one-hour sermon or podcast | ~2–4 tasks |

- **Input size:** each understanding task holds ~220 subtitle lines (≈ 4–6k words), and Claude's answer is
  usually a little longer than its input. The research measured ~1.6× the subtitle tokens in and ~20% out
  (research/recap/README.md, exp07).
- **Recaps** reuse the understanding: one script task, plus a review task if you ask for one.
- **Every answer is cached by content.** Re-running a job never asks the same question twice.

## Troubleshooting

| symptom | fix |
|---|---|
| "no subtitle file and no embedded text subtitles" | add an English `.srt/.vtt/.ass`. Image-based subtitles (PGS/VobSub) and burned-in subtitles need OCR; see METHODOLOGY.md § Ingest |
| ffmpeg not found | install it (step 1) and open a new terminal; the Settings page shows ✓/✗ |
| recap has captions instead of a voice | voice engine unavailable: `pip install -e ".[voice]"` (Kokoro) or `".[system-voice]"` |
| subtitles drift from the picture | install `.[voice]` (Silero VAD). Ingest re-syncs offset and 25↔23.976 fps stretch automatically; re-run Understand with *reingest* |
| job shows "interrupted" | storylens restarted mid-job: click **Run again** on the job page (or a `rerun` request). Every answer Claude already gave is reused, including answers written while storylens was stopped |
| job "waiting for Claude" | open the workspace in the Claude desktop app and say "do the storylens queue"; or answer on the **Claude tasks** page |
| Claude's answer keeps being rejected | open the task's `ANSWER_ERRORS.md` (also shown on its page in the web app): it lists the exact JSON problems |
| a request file did nothing | is storylens running (`serve` or `watch`)? Look in `requests/failed/` for the error |
