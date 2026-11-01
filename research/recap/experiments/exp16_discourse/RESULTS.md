# exp16 — Discourse media: podcasts, talk shows, sermons

**Data** (real, GitHub-hosted):
- 7 sermons by one pastor (~38k words), plus 2 sermons by others from the same church. The transcripts are
  speaker-labelled by service part, with no timestamps.
- 8 Joe Rogan Experience episodes with Jordan Peterson, 2017–2025 (~272k words). These are YouTube auto-captions:
  lowercase, unpunctuated, `[mm:ss]` stamps, no speakers.

**Questions:** "What does Pastor Andrew VanderMaas say about women and marriage?" and "What does Jordan Peterson
say about the meaning of life?" Each corpus was split into ~45 s windows and ranked by three retrievers; the
pooled top-10s were judged.

| corpus | retriever | P@10 (strong) | P@10 (incl. partial) | duplicates in top-10 |
|---|---|---|---|---|
| sermons | BM25 | 0.9 | 1.0 | 4 |
| sermons | dense (MiniLM) | 1.0 | 1.0 | 5 |
| sermons | hybrid (RRF) | 0.9 | 1.0 | 3 |
| JRE auto-captions | BM25 | 0.6 | 0.8 | 0 |
| JRE auto-captions | dense | 0.6 | 0.9 | 0 |
| JRE auto-captions | hybrid | **0.8** | **1.0** | 0 |

## Findings
1. **Discourse is the easy case for retrieval.** Topics are said out loud, so P@10 reaches 0.8–1.0, against ~0.1
   for behavioral traits in narrative (exp15). Search is enough to *find* candidates. The ledger is still needed for
   the next three points.
2. **Who said it.**
   - Auto-captions have no speakers, and 2 of the 18 pooled Peterson hits were mostly the *host* talking.
   - "What X said" needs speaker attribution in the ledger (LLM plus voice clusters, exp03) before a clip can be
     credited to X.
   - Every clip can carry a speaker-confidence flag (`speaker_uncertain` in the plan).
3. **Duplicates across sources.**
   - Two "different" sermons were two recordings of the same sermon, which made 7 of the 18 sermon hits
     duplicates.
   - A cross-source layer must de-duplicate near-identical claims (embedding similarity plus same speaker) before
     selection, otherwise supercuts repeat themselves.
4. **No-narrator supercuts work best as an argument, not a timeline.**
   - The Peterson plan (2:12) orders 5 clips from 4 episodes spanning 2018–2025 as one line of reasoning:
     suffering → meaning as antidote → responsibility not rights → concentric responsibility → maximal
     responsibility = the meaning of life.
   - The only "narration" is a title card and per-clip lower thirds (source + year).
   - This needs claim-level facts with **topics**, **stance** and **supports/contradicts** links, plus clip spans
     at caption-line precision snapped to audio pauses (exp11 VAD).
5. **The schema holds, with a discourse vocabulary.** Beats become the talk's *points*, threads become *themes*,
   turning points become *key points*, and fact `act_type` uses asserts / argues / illustrates / cites / asks /
   answers / advises / jokes / prays / reads, with `topics` and `stance` (see `discourse_ledger_sample.json`).
   Tiers, lenses, nested selection and rendering are unchanged.
6. **Timestamps are a prerequisite.** Sermon text without time codes can't be cut. Media without subtitles needs
   ASR (linger already has WhisperX) or forced alignment.

## Implications for the build
- **Media profile** `discourse` (podcast / talk show / sermon / lecture), with its own P1 prompt and act
  vocabulary; `topics` and `stance` stored on facts.
- **Topic lens:** "what <speaker> says about <topic>", via search (high precision here) plus ledger
  speaker/topic filters, then LLM verification, de-duplication, and argument ordering.
- **`clips` style:** no narrator; hero clips only, with an optional title card and lower thirds.
- **Cross-source layer:** a library-wide index of facts with levels of detail (collection → title → episode →
  point → claim), cross-title lenses, and cross-title supercuts.
