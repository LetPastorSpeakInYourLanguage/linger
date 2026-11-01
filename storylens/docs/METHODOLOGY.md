# Methodology: capture wide once, project narrow many times

storylens turns English subtitles (plus optional video) into a **persistent, queryable understanding** of a story,
then derives any number of recaps from it. Every design choice below traces back to a measured experiment in
[`research/recap/`](../../research/recap/README.md), cited as (expNN).

**Who does what.** storylens does the mechanical work: reading files, aligning, indexing, selecting, checking,
timing and rendering. **Claude does all the thinking**, through the shared workspace folder. Each pass below is a
*task* (`tasks/<id>/TASK.md` → `answer.json`; see [AGENTIC.md](AGENTIC.md)). There is no API anywhere. So the
method is shaped to need **few, large, self-contained tasks**:
- understanding a feature film is ~6–10 tasks;
- a 22-minute episode is ~2–3;
- a recap is 1–4.

```
T0 EVIDENCE    cues + SDH tags · speakers · speech activity · shots · keyframes      immutable per media
T1 FACTS       every act / state / reveal / quote / joke / moment of EVERY character  one pass, append-only
T2 STRUCTURE   beats · tiers P0–P3 · threads · turning points · requires/pays_off ·  derived from T1 (beats only)
               caused_by / revealed_by · characters
T3 LENSES      main · character · trait · thread · topic · pattern · overview          on demand, cached
RECAP          nested selection → script from the exact lines → checks (+ optional review) → G2 → voice → render → fit → G3
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

The subtitles are split into **parts** of ~220 lines (`chunk_lines`) at the largest silences. Each part is one
Claude task that sees:
- the part's lines;
- the cast you gave and your instructions;
- a CONTINUITY note pointing at the previous part.

All parts of a media are **queued at once**, so Claude can work through an episode in one sitting, in order,
carrying the story and names forward itself. This is incremental updating, chosen over pure hierarchical merging
(BooookScore), without making storylens wait between parts. Each task returns:

| output | purpose |
|---|---|
| `scenes` with `speakers` per line | who said what (LLM 62% vs heuristics 17% on Friends; exp03). Characters rarely say each other's names (3% recall by name), so speaker attribution is the prerequisite for character stories (exp13) |
| `beats` (+ `local_importance`, emotion, intensity, who, **`caused_by`, `revealed_by`**) | the central flow: events that move a plot or relationship, and **who made each happen or brought the information to light**, for any character, however minor. This used to be a separate pass (P2c); asking for it while the lines are in view is cheaper and just as good, and it is what makes hidden influence discoverable (co-occurrence can't see causality, exp13 §3) |
| `facts` for **every** character present | `kind`: act / state / reveal / quote / joke / moment. Acts use a fixed taxonomy (helps, comforts, defends, protects, rescues, sacrifices, gifts, advises, encourages, thanks, apologizes, forgives, confesses, reveals, discovers, decides, plans, refuses, quits, leaves, returns, jokes, teases, mocks, flirts, kisses, rejects, breaks_up, argues, accuses, lies, deceives, betrays, steals, threatens, attacks, kills, other) with `actor → target`, `cost` 0–3 (what it costs the actor), evidence lines and the beat it belongs to. States use `learns / feels / wants / status / relationship:<other>` |

**Why the ledger is required:**
- **Trait compilations:** semantic search for a trait performs at chance. P@20 was 0.05–0.15 against a 0.10
  base rate, recovering ~13% of instances (exp15), because "being a good friend" is a judgment about behavior.
- **Side stories:** the main flow under-represents secondary characters (12–57% recall, exp13).

**P1v — vision patch** (optional; setting `vision: gaps`, or `--vision on`). For every dialogue gap ≥ 8 s (up to
24 per media), one keyframe image is placed in a **single task per media**. Claude opens the images and returns,
per gap: visible events, on-screen text, setting, and whether it is credits. The results are inserted into the
parts as `V@mm:ss` lines before P1, and kept as `visual` facts.
- **Why:** 34% of a thriller's salient scenes, and 3 of its 5 turning points, contain *no dialogue* (exp05). A
  keyframe pass caught a "40 YEARS LATER" title card, a character's age and the giant robots, all invisible to the
  subtitles (exp05c).

## T2 — Structure (P2 integrate; `understand.integrate_pass`)

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

**Ids are storylens's job.** Whatever ids an answer uses, storylens makes every scene, beat and fact id
globally unique (`<media>-c<part>-<local id>`) and remaps references inside the part. Claude never has to keep a
global counter.

**G1 review.** You see the logline, characters, turning points, the spine, coverage and the unknown-speaker rate.
Corrections (tier changes, deletions, field fixes) go to `corrections.jsonl` and are applied on every load, so they
survive re-runs and feed every lens.

## T3 — Lenses (`views.py`)

| lens | candidates | ranking |
|---|---|---|
| `main` | all beats | P2 global importance + tiers; `requires` edges kept for coherent short cuts |
| `thread:<id>` | the thread's beats | P2 |
| `character:<name>` | facts where the character (incl. aliases) is actor or target, beats they are in, beats they caused or revealed | a Claude **lens task** ranks items for *their* arc (salience 0–100, tier, role, why) and lists **hidden gems** (what the main plot doesn't credit them for) |
| `trait:<actor>/<query>` | the query is interpreted into act types + keywords → ledger filter + FTS. `deep` also sweeps every scene the actor is in, judged from its lines | Claude checks **every** candidate (match + strength 0–3, in batches); salience = 25×strength + 8×intensity |
| `topic:<speaker>/<query>` | claims by topic/text + full-text passages (discourse; below) | Claude checks relevance, speaker, stance, the tightest clip |
| `pattern:<speaker>` | the speaker's claims in order, as moves (question, reading, story, argument, application…) per point | recurring move sequences are mined (n-grams over points); Claude names the pattern and its steps; one example per step becomes a clip |

Lenses are cached in `views/<id>/view.json`, keyed by understanding version + corrections + parameters.

## Recap (`select.py`, `script.py`, `recap.py`, `render.py`)

1. **Nested selection** (exp06). Each item can be told in three forms: **full / short / micro**. A
   multiple-choice knapsack maximizes salience × form value × tier bonus under the time budget, with a 1.5 s pacing
   overhead per cut so tight budgets don't become choppy lists. Dependencies are closed. Budgets are solved in
   ascending order with forced inclusion, so **the 1-minute recap is always a subset of the 5-minute one**.
   - At 60 s on a feature film: 13 beats, 91% of P0 and all turning points, against greedy's 46% of P0.
2. **Script, from the exact lines.** One task holds the style card, your layered instructions (global → title →
   job → mid-run messages) and every selected item **followed by its exact subtitle lines**. Reading the lines is
   what gives specifics and quotes: the old separate zoom-in pass gave +60% specifics and 3× quotes in exp12, and
   it is now folded into the script task. The answer is segments `{narration | hero_clip | title_card}`, each
   citing item refs and a line range in one media. Rule: never tease a setup whose payoff isn't included (exp12
   flow flaw).
3. **Checks (always, no Claude needed):**
   - the cited lines exist;
   - the segment cites a selected item;
   - every quoted phrase in the narration actually appears (fuzzily) in its cited lines.

   **Optional Claude review** (`review: true`, or a tick on the recap form): a separate task sees each segment with
   its lines and returns supported / partly / unsupported, fixes, and outside-knowledge leakage.
4. **G2 review.** Segments with verdicts. Edit inline, approve, or revise with notes (up to 2 rewrites).
   Autopilot requires 0 unsupported, 0 leakage, and estimated duration within 25%.
5. **Voice + render** (exp08/09):
   - Narration footage comes from the cited lines, snapped to shot boundaries.
   - Hero clips play the original audio, cut on silences.
   - Original audio is ducked under narration (−18 dB), which keeps the language-agnostic ambience.
   - Voices: Kokoro neural, the system voice, or captions when no voice engine is available.
   - **Closed-loop duration fit:** after real TTS durations are known, hero clips are capped, the voice is
     re-timed 0.9–1.2×, then footage is padded. The open loop missed targets by up to 81%, the closed loop by ≤ 1.3%
     (exp09).
6. **G3 review** of the final cut.

## Discourse media: podcasts, talk shows, sermons, lectures (profile `discourse`)

Titles of kind `podcast`, `talkshow`, `sermon` or `lecture` use the same four tiers with a discourse vocabulary
(research exp16):

| narrative | discourse |
|---|---|
| scenes | **segments** (topic segments of the conversation/talk) |
| beats | **points** made |
| threads | **themes** that recur across episodes |
| turning points | **KEY1–KEY5** key points; the logline is the thesis / main question |
| acts (helps, lies…) | **claims**: `asserts · argues · illustrates · cites · asks · answers · advises · agrees · disagrees · confesses · jokes · prays · reads · quotes · predicts` |
| — | every fact also carries **`topics`** (1–4 labels) and **`stance`** (for / against / nuanced) |

- **Inputs:** `.srt/.vtt`, or plain timestamped transcripts (`[mm:ss] text`, YouTube/podcast exports, Whisper/AssemblyAI
  JSON). Auto-caption fragments (1–3 s, no punctuation) are merged into thought-sized cues: 4,953 → 784 cues for a
  2.5-hour episode, which makes prompts ~6× shorter.
- **Audio-only media** (MP3/M4A sermons and podcasts) render as a waveform picture.
- **Who said it:** auto-captions have no speakers. In exp16, 2 of the 18 pooled hits for a guest's view were mostly
  the host talking. The discourse pass attributes speakers, and topic lenses flag `speaker_uncertain`. Lower thirds
  show "Speaker? · Source S01E02" so viewers see the uncertainty.

**Topic lens** — `topic:<speaker>/<query>`, e.g. "Pastor Andrew VanderMaas / women and marriage":
1. The request is interpreted into topic labels, synonyms and speaker aliases.
2. Candidates come from the claim ledger (topics/text) **plus** full-text passage search. Discourse topics are said
   out loud, so search is precise here: hybrid P@10 was 0.8–1.0 on sermons and podcast auto-captions (exp16),
   against ~0.1 for behavioral traits in films (exp15).
3. Claude checks each candidate: relevant? who says it (confidence)? the claim in one sentence, its stance and
   strength, and the **tightest self-contained clip** (first..last line).
4. **De-duplication** removes the same statement said twice or recorded twice. In exp16 two "different" sermons were
   one sermon recorded twice, which made 7 of 18 hits duplicates.

**Pattern lens** — `pattern:<speaker>`: *how* a preacher or guest builds an idea.
1. Each claim is mapped to a move: question, reading, citation, story, argument, claim, application, prayer,
   confession, humor, response.
2. Moves are read in order within each point, and recurring sequences of 3–5 moves are counted across the corpus,
   e.g. `question → reading → story → application`.
3. One Claude task names the pattern and labels its steps.
4. The lens returns, for the best examples, one clip per step, labelled with its step name (the lower third). A
   `clips` recap therefore *shows* the method in the speaker's own words.

**`clips` style (no narrator)** — the most important format for discourse:
- Only the speakers' own words, as complete thoughts (8–45 s).
- An optional opening title card, and a lower third on each clip (speaker · source · episode) that is shown on
  screen, never spoken.
- Ordered **as an argument** (problem → claims → reasons → conclusion) rather than chronologically. For example, the
  exp16 plan "what Jordan Peterson says about meaning" orders 5 clips from 4 episodes spanning 2018–2025 as one line
  of reasoning.

## The cross-source layer: everything you have understood, searchable together (`library.py`)

Every approved understanding, whether films, series, podcasts or sermons, feeds one **library index**
(`<workspace>/library.sqlite`, rebuilt automatically, never the source of truth).

- **Search at five levels of detail:** `title` (which sources talk about it, how much) → `episode` → `point` →
  `claim` (who said what) → `line` (exact words). Optionally restricted to a speaker and a collection.
- **Collections:** any set of titles ("Pastor X — all 200 sermons", "Philosophy podcasts", "Everything"). Cross-title
  lenses are built from each title's cached lens, then merged, de-duplicated and re-ranked:
  - `topic`: what anyone or one speaker said about something, across every episode and show;
  - `trait` and `character`: across titles (for example a character's arc over several films);
  - `overview`: the P0/P1 spine of every title, to "recap a whole set of sources".
- **Collection recaps:** the same pipeline (selection → script → checks → render). Segments cite composite media
  ids (`title::media`), so one supercut can cut between a film's video and a podcast's audio.

Scale note: understanding is per title and cached. A 200-episode sermon archive is 200 P1 runs, parallel and done
once: ~2–4 tasks per one-hour episode. After that, every cross-source question is index lookups plus a few check
tasks.

## Evaluation you can run

- Every job records metrics: check verdicts, leakage, duration error, coverage, unknown-speaker rate, and the number
  of Claude tasks (new vs reused from the answer cache).
- The research harness ([exp12](../../research/recap/experiments/exp12_recap_channel/RESULTS.md)) measures
  faithfulness, coverage of an independent synopsis, leakage, and flow statistics. Use it to compare models,
  effort levels or prompt changes.

## Known limits

- **Dialogue-free action** needs the vision pass. Without it, ~16% of synopsis events are unreachable (exp12).
- **Speaker attribution** is the weakest automatic layer (62% text-only). Adding voice clusters (diarization)
  named 25 of 27 unknown lines in exp03. This is the next engine to add.
- **Famous titles are known to Claude.** The instruction "use only the lines given" (in every task and in
  `CLAUDE.md`), the quote check and the optional review's leakage check mitigate this, but don't eliminate it.
