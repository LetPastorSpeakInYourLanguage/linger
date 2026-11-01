# Working with Claude: the workspace folder is the whole interface

storylens has **no API key and no model calls**. It is a local tool for three parties who share one folder, the
**workspace** (default `~/storylens-workspace`):

| who | does |
|---|---|
| **you** | add media, give instructions, review at the gates (web app, CLI, or by telling Claude) |
| **storylens** (running on your laptop) | the mechanical work: reads subtitles/transcripts, audio and video, aligns, indexes, selects, checks, times and renders |
| **Claude** (the Claude desktop app, working in the workspace folder) | **all the thinking**: answers every task (understanding, lenses, scripts, reviews), and can ask storylens for work |

```
            you ──── web app / CLI ────┐
                                       ▼
   Claude desktop ◀──── tasks/QUEUE.md, TASK.md ────  storylens (serve | watch)
        │        ────── answer.json ──────────────▶        │
        └──────────── requests/new/*.json ────────────────▶│  (start jobs, add titles, decide gates, find)
                       CATALOG.md ◀────────────────────────┘  (what exists)
```

## Setup (once)

1. Install storylens and start it (see [QUICKSTART.md](QUICKSTART.md)):
   ```bash
   storylens serve        # web app on http://127.0.0.1:8765 + the folder watcher
   # or, without the web app:
   storylens watch
   ```
2. In the Claude desktop app, give Claude the workspace folder, e.g. `~/storylens-workspace`. Use a project or
   conversation with folder access (Cowork, or Claude Code in the desktop app).
3. Say: **"Do the storylens queue."** Claude reads `CLAUDE.md` in the folder. That file is written by storylens and
   explains the whole protocol, so you never have to.

## The workspace

```
<workspace>/
  CLAUDE.md            instructions for Claude (managed by storylens; delete its last line to keep your own edits)
  CATALOG.md           everything that exists: titles, episodes, characters/speakers, topics, lenses, recent jobs
  settings.json  instructions.md                     settings · your house style for every job
  tasks/
    QUEUE.md                                          open tasks in order + reviews waiting for you
    0007-cards-my-show-m001-c02/
      TASK.md                                         what to do · input lines · exact answer shape
      answer.json                                     ← Claude writes this
      ANSWER_ERRORS.md                                written by storylens if the answer was invalid
      meta.json  schema.json  answer.rejected-1.json  status, cache key; earlier invalid answers
  requests/new/*.json  requests/done/  requests/failed/      Claude (or you) asking storylens for work
  library/<title>/
    title.json  instructions.md  corrections.jsonl     media list · title notes · your fixes
    evidence/<media>/cues.jsonl media.json speech.json shots.json keyframes/
    understanding/vNNN/{bible.json, beats.jsonl, facts.jsonl, scenes.jsonl, edges.jsonl, speakers.jsonl, characters.json, MANIFEST.json}
    understanding/CURRENT                             the approved version
    views/<lens>/view.json                            built lenses
    index.sqlite                                      search index (derived, rebuildable)
  jobs/<job>/
    job.json  state.json  events.jsonl                request · status · log
    review/<gate>.md  <gate>.metrics.json  <gate>.decision.json
    inbox/*.md                                        instructions sent while the job runs
    artifacts/                                        view.json, selection, script.json, verify.json, edl.json, recap.mp4, report.md
  collections/<id>/                                   cross-source collections and their lenses
  library.sqlite                                      index over every title (derived)
  .cache/answers/<hash>.json                          every accepted answer, by content hash
  .models/                                            voice / VAD models
```

## Tasks: how storylens asks Claude to think

Every thinking step is a folder in `tasks/`. `TASK.md` is self-contained:
- **What to do**: the role and the rules for this pass.
- **Images**, if any: files in the same folder (vision tasks).
- **Input**: numbered subtitle/transcript lines, beats, candidates. Everything needed, nothing more.
- **Answer format**: an example of the exact JSON shape (the full schema is in `schema.json`).

storylens polls for `answer.json` and validates it against the schema:
- **Valid:** the answer is cached, the task is marked done, `QUEUE.md` is updated and the job continues.
- **Invalid:** the file is renamed to `answer.rejected-N.json` and `ANSWER_ERRORS.md` lists what to fix. Claude
  rewrites `answer.json`.

Tasks per job, roughly:

| job | tasks |
|---|---|
| understand a film | one per ~220-line part (6–8), one integration; +1 image task per media with `vision` |
| understand a series | per episode: its parts + one integration; then one series integration |
| understand a podcast/sermon episode | 2–4 |
| lens: main / thread | 0 |
| lens: character / pattern | 1 |
| lens: trait / topic | 1 interpretation + 1 check per ~20–25 candidates |
| recap | 1 script (+1 review if enabled); revisions add one each |

**Never twice.** Answers are cached by the content of the task. Re-running a job, or rerunning an interrupted
one, reuses every answer already given. If storylens was not running while Claude answered, the next start
**harvests** those answers, and a rerun picks them up.

## Requests: how Claude (or you) asks storylens for work

Drop a JSON file into `requests/new/`. storylens handles it within a few seconds, then moves it to
`requests/done/<name>.json` (with the job id) or to `requests/failed/<name>.json` (with the error). A file may
hold one request or a list of them.

```json
{"do": "add_title", "name": "Grace Church", "kind": "sermon", "folder": "/Users/me/Sermons", "cast": ["Pastor Ruth Adeyemi"]}
{"do": "understand", "title": "grace-church"}
{"do": "lens", "title": "my-show", "lens": "trait:Joey/being a good friend", "deep": true}
{"do": "recap", "title": "my-show", "lens": "main", "style": "recap_channel", "duration": 900, "instructions": "seasons 1-3 only"}
{"do": "recap", "title": "grace-church", "lens": "topic:Pastor Ruth Adeyemi/women and marriage", "style": "clips", "duration": 300}
{"do": "recap", "title": "grace-church", "lens": "pattern:Pastor Ruth Adeyemi", "style": "clips", "duration": 240}
{"do": "recap", "title": "grace-church", "lens": "main", "style": "short_direct", "duration": 270}
{"do": "recap", "collection": "all", "lens": "topic:/the meaning of life", "style": "clips", "duration": 600}
{"do": "find", "query": "forgiveness", "level": "claim", "speaker": "Ruth"}
{"do": "decide", "job": "<job id>", "gate": "G2_script", "decision": "revise", "notes": "warmer ending"}
{"do": "send", "job": "<job id>", "text": "focus on the brothers"}
{"do": "cancel", "job": "<job id>"}     {"do": "rerun", "job": "<job id>"}
{"do": "scan", "title": "grace-church", "folder": "/Users/me/Sermons/2026"}
{"do": "collection", "name": "Philosophy", "titles": ["within-reason", "long-table"]}
{"do": "catalog"}
```

The same requests run from a terminal: `storylens request '{"do": "find", "query": "forgiveness"}'`. The full
reference is in `storylens/actions.py`.

So a conversation with Claude can be just:
> **You:** Narrate the gist of last Sunday's sermon in under 5 minutes.
>
> **Claude:** writes `{"do": "recap", "title": "grace-church", "lens": "main", "style": "short_direct",
> "duration": 270}`, answers the script task that appears in `QUEUE.md`, then tells you the G2 review is ready and
> summarizes it.
>
> **You:** Approve.
>
> **Claude:** writes the `decide` request. storylens renders, and the video is at `jobs/<job>/artifacts/recap.mp4`.

Claude can also answer many questions **without any job**, by reading `CATALOG.md` and a title's
`understanding/<v>/facts.jsonl` and `beats.jsonl` directly.

## Review gates

| gate | when | what you see | autopilot passes when |
|---|---|---|---|
| `G1_understanding` | after understanding | logline, characters, turning points, spine, coverage, unknown-speaker rate | coverage ≥ 70% |
| `G2_script` | after the script and its checks | each segment with its verdict and fixes; editable | 0 unsupported, 0 leakage, duration within 25% |
| `G3_render` | after rendering | the video, its duration vs target, the voice engine | duration within 10% |

Waiting reviews are listed in `tasks/QUEUE.md`, on the web app's **Claude tasks** page, and on the job page.
There are three ways to decide:
- in the web app;
- with `storylens approve <job> <gate> [--revise "notes"] [--reject]`;
- by telling Claude, who writes a `decide` request.

`CLAUDE.md` tells Claude to decide only when you say so.

```json
{"decision": "revise", "notes": "Less snark at the end; mention Ines saved them.", "edits": {"3": "New text for segment 3"}}
```

`revise` re-runs the script with your notes (up to 2 times). `edits` replace segment texts directly.

**Autonomy** (`settings.autonomy`, or `"autonomy"` per request):
- `gates`: you always decide.
- `autopilot`: approve automatically when the rules above hold; otherwise you decide.
- `auto`: always approve, logging a `gate_warning` when a rule fails.

## Instructions, in layers (later wins)

1. `<workspace>/instructions.md`: house style for everything.
2. `library/<title>/instructions.md`: title notes ("the twins are played by one actor").
3. The job's `instructions`: set when you start a recap, or in a request.
4. `jobs/<job>/inbox/*.md`: messages sent while the job runs (`send` request, `storylens send`, or the job page).
   These are merged into all *later* tasks of that job.

## Corrections

Fix the understanding without re-running it. Append to `library/<title>/corrections.jsonl` (you or Claude), or
use the UI's tier selector:

```json
{"target": "m001-c03-b2", "field": "tier", "value": "P0", "reason": "this is the inciting incident"}
{"target": "m001-c05-f7", "field": "actor", "value": "Ines"}
{"target": "m001-c02-b9", "field": "delete", "value": true}
```

Corrections apply on every load: lenses, recaps and the search index all see them, and they survive
re-understanding.

## No Claude at hand?

- The web app's **Claude tasks** page shows every task with a **Copy task** button and an answer box. Paste the task
  into any Claude chat and paste its JSON reply back.
- `storylens --offline …` and `storylens demo` answer with a built-in heuristic. It is only good enough to test
  that ffmpeg, voices and rendering work.
