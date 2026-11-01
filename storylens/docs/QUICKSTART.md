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

## 3. Check everything works (no key needed)

```bash
storylens demo
```

This creates a workspace in `~/storylens-workspace`, adds a short original sample story with a generated test
video, and runs understanding plus three recaps (main story, Victor's story, "Leo being a good friend") with the
**offline mock LLM**. The output is basic, but it proves ffmpeg, voices and rendering work.

## 4. Connect Claude

```bash
# macOS/Linux
export ANTHROPIC_API_KEY=sk-ant-...
# Windows (persists for new terminals)
setx ANTHROPIC_API_KEY sk-ant-...
```

`storylens serve` then uses Claude automatically (`llm_backend: auto`). With no key, the backend is `folder`: steps
wait for an agent or for you (see [AGENTIC.md](AGENTIC.md)).

## 5. Run the app

```bash
storylens serve           # → http://127.0.0.1:8765   (use --port to change; -w PATH for another workspace)
```

1. **Library → Add title.** Give a name, film or series, and optionally the main character names (cast) and a
   folder to scan. The scan pairs `Movie.mkv` with `Movie.srt` / `Movie.en.srt` and detects `S01E02` episode numbers.
   You can also add single files by path or upload a subtitle file. Files are read in place and never modified.
2. **Overview → Understand.** This reads the subtitles chunk by chunk and writes scene cards plus the fact ledger,
   integrates the story, and links causes. When it pauses at **G1**, review the logline, characters, turning points
   and spine. Fix things in **Story** (tiers) or the title instructions, then approve.
3. Explore **Story**, **Characters** and **Fact ledger**: every beat and fact links back to its subtitle lines and
   the video.
4. **Lenses**: build the main story, a character's story, a trait compilation ("being a good friend" + a
   character; tick *deep sweep* for exhaustive), or a storyline.
5. **Make a recap**: pick a lens, style, duration, voice and review mode, then add instructions.
   - The job pauses at **G2** with the script and the verifier's verdict per segment. Edit text inline, approve,
     or ask for a revision with notes.
   - It pauses at **G3** with the rendered video.
   - Results are kept in the job's `artifacts/`.

## Podcasts, talk shows, sermons

1. **Add title** with kind `podcast` / `talkshow` / `sermon` / `lecture`, and put the speaker names in *cast*
   (host, guests, preacher). Point *scan folder* at the episodes. Audio files (`.mp3/.m4a/...`) pair with transcripts
   (`.srt/.vtt`, or `.txt/.md` lines like `[12:34] text`, or Whisper/AssemblyAI `.json`) by file name.
2. **Understand**: segments, points and a **claim ledger** (who said what, topics, stance) for every episode.
3. **Lenses → "What someone said about a topic"** (speaker + topic), then **Make a recap → "Clips only — no
   narrator"**: a supercut of the speakers' own words with lower thirds.
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
storylens jobs | storylens pending | storylens approve <job> G2_script | storylens send <job> "less snark"
storylens search my-show "wedding"
storylens add "Grace Church" --kind sermon --folder "D:\Sermons" --cast "Pastor Ruth Adeyemi"
storylens lens grace-church "topic:Pastor Ruth Adeyemi/women and marriage"
storylens recap grace-church --lens "topic:Pastor Ruth Adeyemi/women and marriage" --style clips --duration 300
storylens find "meaning of life" --level title                  # which sources discuss it (all titles)
storylens find "meaning of life" --level claim --speaker Peterson
storylens collection create "Philosophy" --titles within-reason,long-table
storylens lens x "topic:Alex O'Connor/the meaning of life" --collection philosophy
storylens recap x --collection philosophy --lens "topic:/free will" --style clips --duration 600
```

Review modes:
- `gates` (default): a human approves G1/G2/G3.
- `--autopilot`: gates pass automatically when their metrics hold (no unsupported claims, no outside-knowledge
  leakage, duration within tolerance), otherwise a human decides.
- `--yes` / `auto`: approve everything, with warnings logged.

## Settings (`<workspace>/settings.json`, or the Settings page)

| key | default | meaning |
|---|---|---|
| `llm_backend` | `auto` | `anthropic` if a key is present, else `folder`; or `mock` |
| `model` | `claude-opus-5-5` | integration, scripts, verification |
| `bulk_model` | `claude-opus-5-5` | per-chunk extraction, lens checks (e.g. `claude-sonnet-5-5` to lower cost) |
| `effort` | per pass | `low`…`max` per pass (`cards`, `integrate`, `causal`, `view`, `script`, `verify`, `zoom`) |
| `fallbacks` | `true` | server-side refusal fallback |
| `chunk_lines` | `160` | subtitle lines per understanding chunk |
| `max_parallel` | `4` | parallel LLM calls (episodes, lens checks, verification) |
| `autonomy` | `gates` | `gates` / `autopilot` / `auto` |
| `tts`, `voice` | `auto`, `am_michael` | `kokoro` / `system` / `none` (captions) |

## Cost & time expectations

Understanding is the expensive, one-time step, and it is cached per title version. Measured in the research
(research/recap/README.md, exp07):
- **P1 extraction:** about 1.6× the subtitle tokens as input, plus ~20% as output. That is ~20–30k input tokens for
  a feature film and ~300k for three seasons of a sitcom.
- **Recaps:** much cheaper, because they reuse the understanding.

Every LLM call's token usage is recorded in the job's `steps/*/meta.json` and summarized in `MANIFEST.json`.
Identical prompts are never paid for twice (content-hash cache in `<workspace>/.cache/llm`).

## Troubleshooting

| symptom | fix |
|---|---|
| "no subtitle file and no embedded text subtitles" | add an English `.srt/.vtt/.ass`. Image-based subtitles (PGS/VobSub) and burned-in subtitles need OCR; see METHODOLOGY.md § Ingest |
| ffmpeg not found | install it (step 1) and open a new terminal; the Settings page shows ✓/✗ |
| recap has captions instead of a voice | voice engine unavailable: `pip install -e ".[voice]"` (Kokoro) or `".[system-voice]"` |
| subtitles drift from the picture | install `.[voice]` (Silero VAD). Ingest re-syncs offset and 25↔23.976 fps stretch automatically; re-run Understand with *reingest* |
| job shows "interrupted" | the server restarted mid-job: start it again; finished LLM steps are reused from the cache |
| a step "waiting for an agent" | the backend is `folder`: set `ANTHROPIC_API_KEY`, or answer in **Agent steps** / with Claude Code |
