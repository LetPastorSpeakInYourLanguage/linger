# Agentic use: the workspace is the API

Everything storylens does is a file in the **workspace** (default `~/storylens-workspace`). That makes the app
usable by a person in the browser, by the CLI, and by AI agents such as Claude Code, all at the same time and on
the same files.

```
<workspace>/
  settings.json  instructions.md  AGENTS.md          global settings, global instructions, rules for agents
  library/<title>/
    title.json  instructions.md  corrections.jsonl    media list, title notes, human overrides
    evidence/<media>/cues.jsonl media.json speech.json shots.json keyframes/
    understanding/vNNN/{cards.json, scenes|beats|facts|edges|speakers|visual .jsonl, characters.json, bible.json, MANIFEST.json}
    understanding/CURRENT                             the approved version
    views/<lens>/view.json                            cached lenses
    index.sqlite                                      derived search index (rebuildable)
  jobs/<job>/
    job.json  state.json  events.jsonl                request, status, append-only log
    steps/NNNN-<task>/prompt.md schema.json [hint.json] response.json meta.json   one folder per LLM call
    review/<gate>.md <gate>.metrics.json <gate>.decision.json                     human/autopilot gates
    inbox/*.md                                        instructions sent while the job runs
    artifacts/                                        view, selection, details, script, verify, edl, recap.mp4, report
  collections/<id>/collection.json  views/*.json        cross-source collections and their lenses
  library.sqlite                                      derived index over every title (rebuildable)
  .cache/llm/<hash>.json                              content-addressed answers (never pay twice)
  .models/                                            downloaded voice/VAD models
```

## Three ways to answer an LLM step

Every LLM call goes through the same runner. It writes `prompt.md` (system + user), `schema.json` (the exact JSON
shape) and `meta.json` (model, effort, cache key, tokens). The answer is `response.json`.

| backend | who writes `response.json` |
|---|---|
| `anthropic` | the app, via the Anthropic SDK (structured outputs → schema-valid JSON) |
| `folder` | **an agent or a human.** The step gets a `WAITING` file, the job shows "waiting for an agent", and storylens polls until `response.json` appears |
| `mock` | the offline heuristic (tests and demos) |

### With Claude Code (no API key in the app)

```bash
storylens -w ~/storylens-workspace --llm folder understand my-film     # or start it from the web UI
# in another terminal:
cd ~/storylens-workspace
claude "Answer the pending storylens steps. Follow AGENTS.md."
```

Claude Code reads `AGENTS.md`, finds `jobs/*/steps/*/WAITING`, and for each step reads `prompt.md` and
`schema.json`, then writes `response.json`. The job continues by itself. You can also paste an answer in the web
UI under **Agent steps**.

## Review gates

| gate | when | what you see | autopilot passes when |
|---|---|---|---|
| `G1_understanding` | after understanding | logline, characters, turning points, spine, coverage, unknown-speaker rate | coverage ≥ 70% |
| `G2_script` | after script + verification | each segment with the verifier's verdict and fixes; editable | 0 unsupported, 0 leakage, duration within 25% |
| `G3_render` | after rendering | the video, its duration vs target, the voice engine | duration within 10% |

Decide in the UI, with `storylens approve <job> <gate> [--revise "notes"] [--reject]`, or by writing
`review/<gate>.decision.json`:

```json
{"decision": "revise", "notes": "Less snark at the end; mention Ines saved them.", "edits": {"3": "New text for segment 3"}}
```

`revise` with notes re-runs the script with your notes appended to its instructions, up to 2 times. `edits`
replace segment texts directly.

**Autonomy** (`settings.autonomy`, or per job):
- `gates`: always ask.
- `autopilot`: auto-approve when the metrics above hold, otherwise ask.
- `auto`: always approve, logging a `gate_warning` event when a metric fails.

## Instructions, in layers (later wins)

1. `<workspace>/instructions.md`: house style for everything.
2. `library/<title>/instructions.md`: title notes ("the twins are played by one actor").
3. The job's `instructions` field: set when you start a recap.
4. `jobs/<job>/inbox/*.md`: messages sent while the job runs (`storylens send <job> "…"` or the job page).
   These are merged into the prompts of all *later* steps.

## Corrections

Fix the understanding without re-running it. Append to `library/<title>/corrections.jsonl`, or use the UI's
tier selector:

```json
{"target": "m001-c03-b2", "field": "tier", "value": "P0", "reason": "this is the inciting incident"}
{"target": "m001-c05-f7", "field": "actor", "value": "Ines"}
{"target": "m001-c02-b9", "field": "delete", "value": true}
```

Corrections apply on every load: lenses, recaps and the search index all see them, and they survive
re-understanding.

## Running steps elsewhere

Because steps are self-contained folders, you can farm them out to other machines, to a batch job, or to a
different model by copying the folder and copying `response.json` back. The cache key in `meta.json` lets
identical prompts reuse answers across jobs and title versions.
