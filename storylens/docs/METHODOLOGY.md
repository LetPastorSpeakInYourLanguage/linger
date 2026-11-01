# Methodology: capture wide once, project narrow many times

storylens turns English subtitles (plus optional video) into a **persistent, queryable understanding** of a story,
then derives any number of recaps from it. Every design choice below traces back to a measured experiment in
[`research/recap/`](../../research/recap/README.md), cited as (expNN).

```
T0 EVIDENCE    cues + SDH tags · speakers · speech activity · shots · keyframes      immutable per media
T1 FACTS       every act / state / reveal / quote / joke / moment of EVERY character  one pass, append-only
T2 STRUCTURE   beats · tiers P0–P3 · threads · turning points · requires/pays_off ·  derived from T1 (beats only)
               caused_by / revealed_by / witnessed_by · characters
T3 LENSES      main · character:<name> · trait:<actor>/<query> · thread:<id>           on demand, cached
RECAP          nested selection → zoom-in → script (style) → independent verify → G2 → voice → render → fit → G3
```

## Why this structure (and not one big layer, or main + side layers)

- **One merged layer** congests every main-story prompt with side detail, and quality drops with prompt size.
- **A separate side layer** has to re-read the subtitles (doubling the cost of that pass), and its facts are not
  linked to the main story. That is why a main-flow summary never credits the background character who *caused*
  the breakup: in exp13 the main layer held only 12.5% of Gunther's scenes and never attributed the reveal to him.
- **A fact base plus derived views:**
  - **T1 captures everyone once.** The extraction pass costs only ~25% more output (exp13 O3).
  - **T2 is built from beats only**, so the central story stays uncongested.
  - **T3 lenses read just the slice they need**, about 1% of the corpus for a side character (exp13).
  - **Importance lives on the (lens, item) pair, not on the fact.** "The waiter tells Rachel" is P0 in the
    waiter's lens, a *cause* in the main lens, and absent from "Joey being a good friend".

## T0 — Evidence (`ingest.py`, `media.py`)

- **Subtitles** (`.srt/.vtt/.ass`, or an embedded *text* subtitle stream extracted losslessly with ffmpeg; exp01)
  become cues with stable line ids `L###`.
- **SDH tags** are kept as signals: `[laughs]` (humor), `♪` (music), `(gunshot)` (intensity), `NAME:` (speaker),
  `- ` (dialog turn), italics (off-screen / voice-over).
- **Language-agnostic.** Meaning comes only from the English subtitle text. The audio is used only through signals
  that don't depend on language:
  - **Silero VAD** speech probability, which is far cleaner than WebRTC VAD on films: false speech outside
    subtitles drops from 64% to 1.9% (exp11).
  - **Re-sync**: the offset and the 25↔23.976 fps stretch are recovered by correlating subtitle activity with
    speech activity. This was exact in exp11, leaving only the constant ~0.15 s subtitle lead.
  - **Cut points** snap to silences, which cut cuts landing mid-speech from 16% to 5% (exp11).
- **Shots** come from ffmpeg scene detection. **Keyframes** are extracted for the vision pass.
- **Burned-in (hard) subtitles** are pixels. Classical OCR failed on real double-hardsubbed frames, while a vision
  LLM read 12/12 lines exactly (exp01). Prefer sidecar or embedded text subtitles. For hardsub-only media, Whisper
  plus translation is the practical fallback. Renders can blur a burned-in subtitle band (`hardsub_blur`).

## T1 — Facts: scene cards + ledger (P1, `understand.cards_pass`)

The subtitles are split into ~160-line chunks at the largest silences. Each chunk is one LLM call that sees the
chunk, the roster so far, a running *story so far*, and your instructions. This is incremental updating with
structured outputs, chosen over pure hierarchical merging (BooookScore). The call returns:

| output | purpose |
|---|---|
| `scenes` with `speakers` per line | who said what (LLM 62% vs heuristics 17% on Friends; exp03). Characters rarely say each other's names (3% recall by name), so speaker attribution is the prerequisite for character stories (exp13) |
| `beats` (+ `local_importance`, emotion, intensity, who) | the central flow: events that move a plot or relationship |
| `facts` for **every** character present | `kind`: act / state / reveal / quote / joke / moment. Acts use a fixed taxonomy (helps, comforts, defends, protects, rescues, sacrifices, gifts, advises, encourages, thanks, apologizes, forgives, confesses, reveals, discovers, decides, plans, refuses, quits, leaves, returns, jokes, teases, mocks, flirts, kisses, rejects, breaks_up, argues, accuses, lies, deceives, betrays, steals, threatens, attacks, kills, other) with `actor → target`, `cost` 0–3 (what it costs the actor), evidence lines and the beat it belongs to. States use `learns / feels / wants / status / relationship:<other>` |

**Why the ledger is required:**
- **Trait compilations:** semantic search for a trait performs at chance. P@20 was 0.05–0.15 against a 0.10
  base rate, recovering ~13% of instances (exp15), because "being a good friend" is a judgment about behavior.
- **Side stories:** the main flow under-represents secondary characters (12–57% recall, exp13).

**P1v — vision patch** (optional; `vision: auto` with the Anthropic backend). For every dialogue gap ≥ 8 s, three
keyframes go to a multimodal call that returns visible events, on-screen text, setting and credits detection. The
results are inserted into the chunk as `V@mm:ss` lines and kept as `visual` facts.
- **Why:** 34% of a thriller's salient scenes, and 3 of its 5 turning points, contain *no dialogue* (exp05). A
  keyframe pass caught a "40 YEARS LATER" title card, a character's age and the giant robots, all invisible to the
  subtitles (exp05c).

## T2 — Structure (P2 integrate, P2c causal; `understand.integrate_pass`, `causal_pass`)

**P2 sees beats and the roster only, never raw facts.** It returns:
- logline, characters (role, arc, importance),
- threads/arcs,
- five turning points (TRIPOD: opportunity, change of plans, point of no return, major setback, climax),
- for every beat: global importance 0–100 and a tier, `requires` / `pays_off` edges, a ≤12-word short form, and a
  spoiler level.

Tiers: **P0** spine (a 60 s recap needs it), **P1** faithful 5–10 min, **P2** rich detail, **P3** texture.

**Series** are integrated hierarchically. Each episode is integrated first (in parallel), then a series pass ranks
each episode's P0/P1 beats. Other beats keep their episode rank, shifted down one tier (exp07: Friends S1–S3,
73 episodes).

**P2c causal links.** For each P0/P1 beat, the facts of its scene ±1 decide `caused_by`, `revealed_by` and
`witnessed_by`, for any character. Co-occurrence can't see causality (exp13 §3), so this is what makes hidden
influence discoverable.

**G1 review.** You see the logline, characters, turning points, the spine, coverage and the unknown-speaker rate.
Corrections (tier changes, deletions, field fixes) go to `corrections.jsonl` and are applied on every load, so they
survive re-runs and feed every lens.

## T3 — Lenses (`views.py`)

| lens | candidates | ranking |
|---|---|---|
| `main` | all beats | P2 global importance + tiers; `requires` edges kept for coherent short cuts |
| `thread:<id>` | the thread's beats | P2 |
| `character:<name>` | facts where the character (incl. aliases) is actor or target, beats they are in, beats they caused/revealed/witnessed | an LLM **lens pass** ranks items for *their* arc (salience 0–100, tier, role, why) and lists **hidden gems** (what the main plot doesn't credit them for) |
| `trait:<actor>/<query>` | the query is interpreted into act types + keywords → ledger filter + FTS. `deep` also sweeps every scene the actor is in, judged from its lines | an LLM verifies **every** candidate (match + strength 0–3); salience = 25×strength + 8×intensity |

Lenses are cached in `views/<id>/view.json`, keyed by understanding version + corrections + parameters.

## Recap (`select.py`, `script.py`, `recap.py`, `render.py`)

1. **Nested selection** (exp06). Each item can be told in three forms: **full / short / micro**. A
   multiple-choice knapsack maximizes salience × form value × tier bonus under the time budget, with a 1.5 s pacing
   overhead per cut so tight budgets don't become choppy lists. Dependencies are closed. Budgets are solved in
   ascending order with forced inclusion, so **the 1-minute recap is always a subset of the 5-minute one**.
   - At 60 s on a feature film: 13 beats, 91% of P0 and all turning points, against greedy's 46% of P0.
2. **Zoom-in.** The exact subtitle lines behind the selected items are re-read, harvesting quotes, numbers and
   callbacks, and flagging unsupported items. In exp12 this gave +60% specifics and 3× quotes, and caught a
   contradiction the understanding layer had made. It is what makes narration sound like a recap channel.
3. **Script.** A style card and your layered instructions (global → title → job → mid-run messages) produce
   segments `{narration | hero_clip | title_card}`, each citing item refs and a line range in one media.
   Rule: never tease a setup whose payoff isn't included (exp12 flow flaw).
4. **Independent verification.** A separate call sees each segment plus its cited lines and returns supported /
   partly / unsupported, fixes, and outside-knowledge leakage. A writer never grades itself here (in exp12 one
   model did both, which is the caveat this step removes).
5. **G2 review.** Segments with verdicts. Edit inline, approve, or revise with notes (up to 2 rewrites).
   Autopilot requires 0 unsupported, 0 leakage, and estimated duration within 25%.
6. **Voice + render** (exp08/09):
   - Narration footage comes from the cited lines, snapped to shot boundaries.
   - Hero clips play the original audio, cut on silences.
   - Original audio is ducked under narration (−18 dB), which keeps the language-agnostic ambience.
   - Voices: Kokoro neural, the system voice, or captions when no voice engine is available.
   - **Closed-loop duration fit:** after real TTS durations are known, hero clips are capped, the voice is
     re-timed 0.9–1.2×, then footage is padded. The open loop missed targets by up to 81%, the closed loop by ≤ 1.3%
     (exp09).
7. **G3 review** of the final cut.

## Evaluation you can run

- Every job records metrics: verifier verdicts, leakage, duration error, coverage, unknown-speaker rate,
  tokens per step.
- The research harness ([exp12](../../research/recap/experiments/exp12_recap_channel/RESULTS.md)) measures
  faithfulness, coverage of an independent synopsis, leakage, and flow statistics. Use it to compare models,
  effort levels or prompt changes.

## Known limits

- **Dialogue-free action** needs the vision pass. Without it, ~16% of synopsis events are unreachable (exp12).
- **Speaker attribution** is the weakest automatic layer (62% text-only). Adding voice clusters (diarization)
  named 25 of 27 unknown lines in exp03. This is the next engine to add.
- **Famous titles are known to LLMs.** The verifier's leakage check and the instruction "never use outside
  knowledge" mitigate this, but don't eliminate it.
