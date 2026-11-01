# Autonomous, language-agnostic LLM recaps — research & experiments

**Goal.** Take any film, series or telenovela with **English subtitles** (soft or burned in) plus the media in
*any* spoken language, and automatically produce recaps in four styles at any duration from 60 s to unlimited:
- **dramatic/comedic**: joke-dropping narrator,
- **short & direct**,
- **fan/silent**: for people who know the story; the actors' own emotional moments, minimal text,
- **detailed/full**.

Underneath sits a **persisted story-understanding layer** that linger can query.

> 📄 Literature review: [`01_literature.md`](01_literature.md) · 🧪 Experiments: [`experiments/`](experiments) ·
> 🧰 Library: [`recaplib/`](recaplib) · 🎬 Sample renders: [`samples/`](samples)

---

## TL;DR — answers to the questions we started with

| Question | Answer from the experiments |
|---|---|
| **Can an LLM understand a film from subtitles alone?** | **For the plot spine, yes. For what's on screen, no.** From subtitle text only (names scrambled), the multi-pass LLM recovered the full causal spine of *Tears of Steel* and *Panic Room* and placed 3 of 5 *Panic Room* turning points within ±2 scenes (position prior: 2/5). But **34% of *Panic Room*'s salient scenes and 3 of its 5 gold turning-point scenes contain no dialogue at all** (exp05). A vision pass on keyframes fixed what subtitles can't know in *Tears of Steel*: a "40 YEARS LATER" card, the hero's age, the giant robots, the city, the credits (exp05c). → **Subtitle-first, plus a cheap keyframe vision pass for gaps.** |
| **Who said what?** | Heuristics: 17–20%. LLM over dialogue context: **62%** (Friends window). Language-agnostic **voice clusters × LLM names**: 80% cluster/name agreement, and they name 25 of the 27 lines the LLM left unknown (exp03). |
| **How do we rank what goes into a 15-min vs 60-s recap?** | Two-level importance. P1 gives local scene salience; P2 gives **global** importance, tiers P0–P3, setup→payoff edges and turning points. Then a **nested multiple-choice knapsack** over beats with full/short/micro renderings. At 60 s on *Panic Room* it keeps 91% of P0 beats and all turning points, against 46% for greedy. Every shorter recap is a strict subset of every longer one, so the duration slider only ever adds context (exp06). |
| **Does it scale to 3 seasons in 15 min?** | Yes, hierarchically: scene cards → episode digests → series arcs → arc-weighted beats. Friends S1–S3 (73 episodes, 184k dialogue words): the 15-min plan covers **all P0/P1 beats, 55/73 episodes and every arc** in proportion to its importance. The P1 scene-card pass is >90% of tokens (~310k in), runs in parallel per episode and is cached once per title (exp07). |
| **Styles?** | All four rendered end-to-end from one understanding: Kokoro neural TTS, ducked original audio under narration, and original-audio "hero clips" (exp09). Every script cites only real beat ids (0 invented). The closed-loop fit pass lands within 1.3% of target (60.2/60 s, 120.3/120 s, 91.2/90 s). |
| **Language-agnostic?** | Meaning comes only from English subtitle **text**. Audio is used only through language-independent signals. **Silero VAD** (ONNX): its correlation with subtitle activity is 0.56 vs 0.13 for WebRTC, and its false speech is 1.9% vs 64%. It **recovers subtitle offsets and 25↔23.976 fps stretch exactly** (residual ≈ the constant 0.15 s subtitle lead). Snapping cuts to silence drops cuts inside speech from 16% to 5% (exp11). Hardsubs in another language are just pixels: we found real burned-in Chinese subs in our test video and are still using the English SRT. |
| **Can the understanding live in a DB for linger?** | Yes. The SQLite schema [`recaplib/schema.sql`](recaplib/schema.sql) holds cues, speakers, scenes, beats, edges, moments, turning points, vectors and FTS. On FriendsQA (2,990 questions → 326 scenes), the understanding-layer index beats raw subtitle search; see exp10 below. |

---

## The pipeline (what we'd build into linger)

```
             media (any language)                 English subtitles (soft / OCR'd hardsub / sidecar)
                    │                                              │
   P0  ingest ──────┼── proxy, shots, Silero VAD, loudness,        ├── parse + SDH tags ([laughs] ♪ (gunshot) NAME:)
                    │   1 fps faces + expressions, keyframes       ├── re-sync to VAD (offset / fps stretch)
                    │                                              └── utterance merge, line ids L###
                    ▼                                              ▼
   P1  scene cards (LLM, incremental, ~160 lines/chunk, running story-so-far + roster)
         scenes · speakers · atomic BEATS (kind, local importance, emotion) · humor · quotes · MOMENTS
   P1v vision patch (LLM w/ images): keyframe grid per scene/gap → intertitles, identity/age, setting,
         non-dialogue events, credits, hardsub presence                             ← exp05c
   P2  integrate (LLM, whole work / per season):  logline · characters · threads/arcs · 5 turning points ·
         GLOBAL importance 0-100 · tiers P0-P3 · requires/pays_off edges · short forms · spoiler level
   P2s series: episode digests → arcs → arc-weighted beat priorities                ← exp07
   ──────────────────────────── persisted: Story Understanding Layer (SQLite) ──────────────────────────
   P3  select:  nested MCKP over beats (full/short/micro) under duration, dependency closure    ← exp06
   P4  script (LLM, per style card): segments {narration | hero_clip | title_card} citing beat ids
         + visual line ranges; P4v verify: claims vs cited lines
   P5  ground:  footage = cited lines → snapped to shots/silence; hero clips = top AV-intensity moments;
         stills = sharp + face + expressive − near-cut − burned-in text                  ← exp08
   P6  voice + render: Kokoro TTS → closed-loop fit to target duration → ffmpeg EDL → MP4 ← exp09
```

Every LLM output cites **subtitle line ids**, so any beat, joke or emotional moment maps back to exact
timestamps. That one design choice makes clip-cutting, verification and DB retrieval trivial.

## Experiments (each ran in its own git worktree / branch `recap/expNN-*`, merged here)

| # | Experiment | Data | Key result | Verdict |
|---|---|---|---|---|
| 01 | Ingest: soft subs, **hardsub OCR**, SDH | Tears of Steel | Soft-sub extraction 76/76 identical. Hardsub OCR v1 (plain threshold + tesseract): recall 45%, CER 31%, 844 false cues. v2 (glyph+outline text mask, crop, ×2, voting): see `experiments/exp01_ingest/results.json` | Soft subs: solved. Hardsubs: OCR is feasible but needs a text detector or VLM; Whisper→translate is the fallback |
| 02 | Scene segmentation from subtitle text | Friends S1 (24 ep) + 26 screenplays | TextTiling(MiniLM) Pk 0.48 / 0.47 vs evenly spaced 0.52 / 0.51 (oracle K); F1@2 ≤ 0.46 | Lexical tiling is weak. Use the LLM (3/4 exact breaks in exp03) + time gaps + shot changes |
| 03 | Speaker attribution | Friends S1; ToS diarization | majority 17%, vocative+alternation 20%, **LLM 62%**. Voice-cluster × LLM-name purity 0.80; 25/27 unknowns named | Fuse voice clusters (language-agnostic) with LLM naming |
| 04 | Non-LLM saliency priors | 21 MENSA films (3,613 scenes), 15 TRIPOD TP films | Single features AUC: dialogue length 0.66, centrality/PageRank 0.66, future-callback 0.64, position 0.54. LogReg leave-one-movie-out **AUC 0.674**, P@k 0.50 | Cheap, about as good as the LLM at *scene-level* saliency (both capped by dialogue-free scenes). Use as prior/tie-breaker |
| 05 | Multi-pass LLM understanding | ToS; *Panic Room* (614 cues, names scrambled) | Full spine recovered; TP hit@2 **3/5** (prior 2/5); MENSA scene AUC 0.65 (dialogue length 0.66; 20/58 salient scenes have no dialogue) | Good for the spine; scene-level saliency capped by dialogue-free scenes |
| 05c | Vision correction pass | ToS keyframe grid | 8 corrections: time jump, age/identity, giant robots, setting, credits, hardsubs. 14/18 beats correct, 4 needed visual detail, 0 wrong | Add P1v |
| 06 | Budgeted selection | ToS (18 beats), Panic Room (47) | 60 s Panic Room: greedy 46% P0 / strict prefix **0 beats** / MCKP 100% P0 but 23 micro-beats (choppy) / **nested MCKP + 1.5 s pacing: 13 beats, 91% P0, 100% TPs, nested** | Nested MCKP with pacing overhead |
| 07 | Series scale | Friends S1–S3 (73 ep) | 10 arcs; 1 min = 10 beats (Ross & Rachel spine); 15 min = 116 beats, all P0/P1, 59% P2, 55 episodes | Hierarchical works. Arc weighting gives balanced coverage |
| 08 | Visual grounding | ToS 1 fps timeline | LLM moments are **1.8×** more facially expressive than the film average; LLM intensity ↔ loudness r = 0.59; 17/18 stills contain faces | Text-predicted moments align with AV signals; use AV to choose the exact clip |
| 09 | Render 4 styles | ToS | Closed-loop fit: short **60.2/60 s**, dramatic **120.3/120 s**, fan **91.2/90 s**, detailed 219.8 s unlimited (open loop: 40.6 / 142.0 / 162.9 s); 0 invented beat ids; −15.9 LUFS | End-to-end pipeline works |
| 10 | SUL database + retrieval | ToS + Panic Room DB; FriendsQA S1 | see table below | DB layer is the foundation for linger |
| 11 | Language-agnostic sync | ToS | Silero ≫ WebRTC; offsets ±6 s and 4.27% fps stretch recovered; cuts inside speech 16% → 5% | Use Silero VAD for sync and cut hygiene |

<!-- EXP10_TABLE -->

## Ideas we evaluated and the recommendation for each

1. **Single-pass whole-film prompt vs hierarchical vs incremental.** A whole film's subtitles fit in a modern context
   window (*Panic Room* ≈ 9k words), but series don't. BooookScore shows incremental updating keeps detail while
   hierarchical merging is more coherent. **Recommendation:** incremental P1 (chunk ≈160 lines, story-so-far + roster)
   followed by a global P2 that re-scores importance. For a single film on a long-context model, P1 can run as one
   call, but keep the *structured* outputs.
2. **Importance = LLM global score, informed by priors.** Use the exp04 features (position, centrality, callbacks)
   as tie-breakers and sanity checks, and turning points as anchors.
3. **"Elastic beats"** (full/short/micro renderings) + **nested MCKP**. This is the duration slider. Add a pacing
   overhead per cut (1–1.5 s) or tight budgets become choppy lists.
4. **Dependency edges** (requires / pays_off) keep short recaps coherent ("why does she hate him?").
5. **Hero clips** (actors' original audio) are chosen where LLM moment ∩ high loudness ∩ expressive faces. They are
   language-agnostic by nature, since the viewer hears the actor's real emotion in any language.
6. **Vision patch pass (P1v):** send 1 keyframe per ~20 s of non-dialogue time plus scene boundaries to a multimodal
   LLM. This is cheap and fixes identity, time-jump and action-scene blind spots.
7. **Speaker identity:** Silero VAD → voice embeddings (ECAPA/Resemblyzer) → clusters → LLM names clusters from
   dialogue. This is language-agnostic.
8. **Re-sync before anything else:** subtitle-activity ↔ VAD correlation search (offset × {1, 25/23.976, 23.976/25}).
9. **Closed-loop duration control** after real TTS durations (cap hero clips → re-time voice 0.9–1.2× → pad → drop
   lowest tier). The open loop missed targets by up to 81%.
10. **Burned-in text hygiene:** detect hardsub bands (exp01 v2 text mask) and blur/crop them in renders and stills,
    and drop credits from candidates.
11. **Series "previously on" mode:** recency-weighted importance (PlotSnap: 88% of recap shots come from the last
    episode) as an alternative weighting to arc importance.
12. **Comedy:** SDH `[laughs]`/laugh-track tags and P1 humor annotations feed the dramatic style's jokes. Jokes must
    be grounded in cited beats, which the verification pass checks.

## How this maps onto linger (`app/backend`)

| linger module today | becomes |
|---|---|
| `llm.py` (provider-agnostic `complete_json`) | the backend for `recaplib.llm.LLM` (replay protocol → real API) |
| `srt_parser.py`, `ingest.py` | `recaplib.subs` (SDH tags, utterance merge, line ids) + re-sync (exp11) |
| `segmentation.py`, `themes.py` | scenes/beats/threads from P1/P2 instead of embedding-only topic segmentation |
| `vectors.py`, `search.py` | SUL `embedding` + `fts` tables; hybrid retrieval over scene summaries + speaker-attributed lines (exp10) |
| `jobs.py` | each pass is a resumable job: P0 analysis → P1 per chunk (parallel) → P2 → recap renders |
| `compose.py`, `media_ops.py`, `overlay_ops.py` | the recap EDL renderer (`recaplib.render`) = an automatic recomposition |
| `translation_ops.py`, dubbing | narration can be dubbed into any language with the same engine |

## Honest limitations

- **No Anthropic API key in this sandbox.** Every LLM call went through a file-based replay protocol
  (`*.prompt.md` → `*.response.json`), and the responses were written in-session by Claude from exactly those
  prompts. Everything is auditable and re-runnable against the API (`RECAP_LLM=anthropic`).
- **Contamination:** famous titles (Friends, Panic Room) are known to LLMs. Name scrambling reduces but does not
  remove this. Public-domain or obscure titles are needed for a clean benchmark.
- Small n (2 films and 1 series for the LLM passes). Network policy blocked archive.org and Hugging Face, so
  MovieRecapsQA, Bazinga!, MovieSum and full-length PD films should be added when available.
- Kokoro TTS is English-first. Multilingual narration would use linger's existing dubbing stack.

## Reproduce

```bash
python3 -m venv recap-venv && . recap-venv/bin/activate && pip install -r research/recap/requirements.txt
# models (all from GitHub; no torch): kokoro-onnx release, opencv_zoo YuNet + FER, silero-vad wheel ONNX,
# all-MiniLM-L6-v2 safetensors (sha256 53aa5117…) → $RECAP_MODELS (default /home/user/models)
python research/recap/experiments/exp05_understanding/run_tos.py      # replay → reads stored responses
python research/recap/experiments/exp09_render/run_exp09.py --fit      # renders 4 styles
```
