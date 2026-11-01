# 02 — Agentic, folder-based integration (with human review & instructions)

*Design for rebuilding linger around agents that work through the filesystem. Research-derived: every
choice below traces back to an experiment result (exp01–exp13). This is a design, not the app.*

## 1. Principles

1. **The filesystem is the API.** Every request, plan, prompt, response, review and artifact is a file. It can
   be inspected, diffed, edited by a human, resumed after a crash, and run by *any* agent runtime: the Claude Agent
   SDK, Claude Code headless, a plain Messages-API loop, or a human. The replay protocol used in these experiments
   (`*.prompt.md → *.response.json`) is already the degenerate case of this.
2. **Understanding is a durable asset; recaps are cheap views of it.** Understand once per title (expensive,
   cached), then generate unlimited recaps, character stories, Q&A and recompositions on top of it (exp06/07/10/13).
3. **Evidence or it didn't happen.** Every claim cites subtitle line ids or keyframes. This makes verification,
   cutting and retrieval mechanical (exp05, exp09, exp12).
4. **Independent verification.** Writer and verifier never share a context. In exp12 the same model wrote and judged
   its own narrations; the protocol fixes that structurally.
5. **Humans steer at gates, not by babysitting.** Gates sit where a human adds the most value for the least time
   (plan, understanding, script, cut). Autopilot passes a gate only when its metrics clear thresholds.
6. **Deterministic tools for non-language work** (ingest, VAD, shots, selection, render), and **LLM agents for
   meaning** (cards, integration, lens, scripts, verification).

## 2. Workspace layout

```
workspace/
  instructions.md                      # global house style & policies (human)        ─┐ merged into every
  library/<title>/                                                                       │ system prompt,
    title.yaml                         # metadata, cast list, languages, spoiler policy  │ later = higher
    instructions.md                    # title-level notes ("the twins are one role")   ─┘ precedence
    media/  subs/{original,resynced}/  # inputs (read-only for agents)
    analysis/                          # P0 deterministic: shots.json vad.npy faces.jsonl keyframes/ hardsub.json
    understanding/
      v004/                            # immutable versions; CURRENT -> v004
        cards/c01.json …               # P1 scene cards (+ character ledger, O3)
        visual/*.json                  # P1v vision patches for dialogue gaps (exp05c)
        bible.json                     # P2: logline, characters, threads, TPs, global tiers
        beats.jsonl edges.jsonl moments.jsonl ledger.jsonl
        characters/<name>.json         # O2 lens dossiers (created on demand, cached)
        MANIFEST.json                  # inputs' hashes, model, prompts' hashes, costs
      corrections.jsonl                # human overrides (wins over any model output)
    sul.sqlite                         # derived index (rebuildable from files; never the source of truth)
  jobs/<job-id>/
    job.yaml                           # the request
    plan.md                            # agent-written plan + cost estimate (human may edit at G0)
    state.json                         # state machine + DAG of steps
    steps/<step-id>/
      prompt.md  context/  response.json  verify.json  meta.json   # meta: model, tokens, cache_key, duration
    review/<gate>.md                   # what to check, diff vs last version, checklist, metrics
    review/<gate>.decision.yaml        # human (or autopilot) decision
    inbox/  outbox/                    # mid-run messages: human → agent, agent → human questions
    artifacts/                         # script.json edl.json voice/*.wav recap.mp4 report.md
    events.jsonl                       # append-only log of everything that happened
```

## 3. Job types (one schema, many outputs)

```yaml
# jobs/2026-11-01-ps-recap/job.yaml
kind: recap                  # recap | character_story | previously_on | qa | understand | recomposition
titles: [panic_room]
understanding: CURRENT       # or a pinned version, e.g. v004
params:
  style: recap_channel       # dramatic_comedic | short_direct | fan_silent | detailed_full | recap_channel | custom
  duration: 8m               # or "unlimited"; nested selection guarantees 1m ⊂ 3m ⊂ 8m (exp06)
  focus: main                # main | character:Lena | thread:T3 | arc:A1 | theme:"guilt"
  spoilers: full             # full | up_to:S02E10 | no_ending
  voice: am_michael
  language_out: en           # narration language; dubbing reuses linger's TTS/translation stack
autonomy: gates              # gates | autopilot | step  (how often humans are asked)
instructions: |
  Make the villain sympathetic. Don't mention the ex-husband's new girlfriend.
```

## 4. The step DAG (what agents actually do)

| Step | Worker | Input → output | Parallel | Gate |
|---|---|---|---|---|
| S0 ingest | tool | media + subs → `subs/resynced`, `analysis/*` (Silero VAD re-sync, shots, faces, keyframes, hardsub/credits detection; VLM-OCR if burned-in) | per file | – |
| S1 cards | **Analyst** agent | chunk of ~160 lines + story-so-far + roster → `cards/cNN.json` (scenes, speakers, beats, humor, quotes, moments, **character ledger**) | per chunk/episode | – |
| S1v vision | **Vision** agent | keyframes of dialogue gaps + scene starts → `visual/*.json` (intertitles, identity/age, setting, action events, credits) | per gap | – |
| S2 integrate | **Editor** agent | all cards + visual → `bible.json`, tiers, edges, TPs, causal roles (`caused_by`, `revealed_by`) | per season, then series | **G1 understanding** |
| S2c lens | **Lens** agent (on demand) | character's speaker-attributed lines + mentions ±2 + ledger → `characters/<name>.json` | per character | (G1) |
| S3 select | tool | beats + duration + focus → nested selection (MCKP, dependency closure, payoff guard) | – | – |
| S4z zoom-in | **Writer** agent | cited lines of selected beats → detail harvest (quotes, numbers, callbacks, corrections) | per beat batch | – |
| S4 script | **Writer** agent | selection + details + style card + instructions → `script.json` | – | – |
| S4v verify | **Verifier** agent (fresh context, ideally a different model) | each segment + its cited lines → supported / partly / unsupported + fixes; leakage check | per segment batch | **G2 script** |
| S5 ground | tool | script → EDL (shots, VAD snapping, AV-intensity hero clips, stills, hardsub blur) | – | – |
| S6 render | tool | EDL + TTS → closed-loop duration fit → mp4 | – | **G3 cut** |
| S7 report | tool + **Critic** | metrics (faithfulness, coverage, leakage, flow, duration error) → `report.md` | – | – |

The Understanding steps (S0–S2) run once per title version. Every job afterwards starts at S2c or S3.

## 5. Human review & instructions

**Gates.** An agent writes `review/G2_script.md`, then the human (or autopilot) answers in `review/G2_script.decision.yaml`:

```markdown
# G2 — script review (Panic Room, recap_channel, 8m)        metrics: unsupported 0/27 · partly 6 · leakage 0 · est 8:04
[ ] Seg 14  "Then gas starts pouring into the vents…"   cites L282-304   verifier: supported
[!] Seg 20  "…Milo turns on him…"                       cites L405-462   verifier: PARTLY — shooting not explicit
[ ] Dangling setup check: door sensor (c01-b6) teased, payoff not selected → teaser removed by rule
Diff vs previous draft: +2 quotes, −1 joke (instruction: "less snark")
```
```yaml
decision: revise            # approve | revise | reject
notes: "Seg 20: say he shoots him. Add one more joke in the 911 segment."
edits: {seg_20: "When Rufus heads for the door, Milo shoots him."}
```

**Instructions** come from four layers, merged into the system prompt in this order (later wins): global
`instructions.md` → title `instructions.md` → `job.yaml: instructions` → `inbox/*.md` messages during a run. An inbox
message invalidates only the steps downstream of what it touches. "Less snark" re-runs S4 and later; "Rufus and
Milo are the same person" re-runs S2 and later. Human corrections to understanding go to `corrections.jsonl`
(`{target: beat:c02-b11, field: who, value: [Lena], reason: …}`), apply to every future job, and feed evaluation.

**Autonomy levels.** `step` asks after every step (debugging). `gates` asks at G1/G2/G3. `autopilot` passes a gate
when its thresholds hold: verifier unsupported = 0, leakage = 0, duration error ≤ 5%, no dangling setups,
reference coverage ≥ target if a reference exists. Otherwise it stops and asks.

## 6. Agent runtime contract (how any LLM/agent plugs in)

A worker needs only: `list/claim a step` → `read prompt.md + context/` → `write response.json` → `exit`.
- **Claim:** atomic rename `steps/<id>/READY` → `steps/<id>/CLAIMED.<worker>` (no database needed; survives crashes).
- **Done:** `response.json` validates against the step's JSON schema, and `meta.json` records model, tokens, latency
  and cache_key.
- **Cache:** `cache_key = sha256(prompt.md + context files + model + schema)`. An identical key anywhere in the
  workspace is reused. Understanding is computed once per title version.
- **Tools available to agentic workers** (CLI, so humans can run them too): `recap ingest`, `recap analyze`,
  `recap lines L120-L180`, `recap search "who told Rachel"`, `recap keyframes 00:42:10-00:43:00`,
  `recap select --duration 8m --focus character:Lena`, `recap render`, `recap eval`. An agent with a shell, such as
  Claude Code or Agent-SDK agents, can therefore *investigate*: re-read lines, look at frames, check a hypothesis.
  It doesn't have to be fed one giant prompt.
- **Isolation:** the Verifier and Critic run in fresh contexts without the writer's reasoning, so they are independent
  by construction.
- **Concurrency:** S1/S1v/S2c fan out per chunk/episode/character. Our measured token profile (exp07): P1 is ~90% of
  all tokens and embarrassingly parallel.

## 7. Understanding-layer v2 (what the experiments say the files must contain)

| Addition | Why (experiment) |
|---|---|
| `speaker`, `speaker_conf`, `voice_cluster` per cue | character stories are impossible without it (exp13: name mentions find 3% of a character's lines) |
| per-scene **character ledger** for *every* character present: `wants · does · learns · feels · relationship_delta · secret · caused_beats · revealed_info` | makes side characters and villains queryable and discoverable (exp13 O3; ~+25% P1 output) |
| beat fields `caused_by`, `revealed_by`, `witnessed_by` | "Gunther told Rachel" is a causal role that co-occurrence cannot see (exp13 §3) |
| `edges` with `requires / pays_off / callback` + a **payoff guard** in selection | no teased-but-unpaid setups (exp12 flow flaw) |
| `visual/*` notes for dialogue gaps, intertitles, credits, identity/age | 16–34% of plot is dialogue-free (exp05, exp12) |
| detail store from zoom-in passes (quotes, numbers, callbacks) cached per beat | recap-channel specificity (+60% specifics, 3× quotes, caught a contradiction; exp12) |
| `version` / `source_cut` flags | a draft script vs the final film differ; evaluation must know (exp12 "D") |
| derived indexes: FTS over speaker-attributed lines and vectors over beats/summaries/dossiers | retrieval R@5 0.48 → 0.61 (exp10) |

## 8. Rebuild proposal for linger (optimal shape)

```
┌──────────────────────── UI (React, today's app evolves) ────────────────────────┐
│ Library · Understanding explorer (beats/threads/characters, edit tiers, corrections) │
│ Jobs & gates (review cards, diffs, approve/revise) · Studio (recompositions)         │
└───────────────▲──────────────────────────────────────────────▲──────────────────┘
                │ reads/writes files (+ watches events.jsonl)    │
┌───────────────┴──────────── Workspace (files = source of truth) ┴─────────────────┐
│ library/<title>/understanding/vNNN   jobs/<id>/…   instructions.md                 │
└───────▲──────────────────────────▲──────────────────────────────▲─────────────────┘
        │                          │                              │
  Deterministic engines (CLI)   Agent workers (any runtime)    Index (sqlite: FTS + vectors,
  ingest/analyze/select/        Analyst · Vision · Editor ·    derived, rebuildable)
  ground/render/eval            Lens · Writer · Verifier · Critic
```
Mapping of today's modules: `jobs.py` becomes the step DAG and scheduler over `jobs/`. `llm.py` becomes one worker
backend. `segmentation.py` and `themes.py` are replaced by S1/S2. `search.py` and `vectors.py` become the derived
index. `compose.py`, `media_ops.py` and `overlay_ops.py` become `render`. Translation and dubbing become
`language_out`. Bulk folder ingest (already requested in `adds.md`) becomes `library/` scanning.

## 9. Cost & latency envelope (from our measurements)

- Film (≈ 9–12k dialogue words): P1 ≈ 1.6× subtitle tokens in + ~18% out; P2 ≈ 10–15k in. Recap jobs afterwards:
  zoom-in ≈ 40% of the film's lines, plus script and verify ≈ 2× script tokens.
- Series S1–S3 (184k words): P1 ≈ 310k in / 56k out, parallel per episode; series P2 ≈ 17k in (exp07).
- Character lens: 1% (side character) to 50% (lead) of P1 input, cached per character.
- Deterministic analysis on CPU: proxy + shots + VAD + 1 fps faces for a 12-minute film ≈ 3–4 min.
