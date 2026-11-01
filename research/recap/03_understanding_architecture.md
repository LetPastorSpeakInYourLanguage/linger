# 03 — Understanding-layer architecture: "capture wide once, project narrow many times"

**Question.** Merge everything into one understanding layer, or keep a main layer for the core story plus a
secondary layer for side details?

**Answer: neither.** Use a **single fact base with derived views**, the event-sourcing pattern applied to stories.
- **Evidence** (subtitle lines, speakers, frames) and **facts** (every act by every character, in every scene) are
  captured *once*, in the same pass, and are never thrown away.
- **The main story is a view**: a ranked projection of the facts. So is every character story, trait compilation,
  thread and "previously on".
- Views are small, cached, versioned and rebuilt only when their inputs change.
- The main flow never sees side detail unless a view asks for it. Side detail is never lost because the main flow
  didn't need it.

Why not the alternatives (from our experiments):

| Option | What goes wrong |
|---|---|
| **One merged layer** (everything in one big bible) | P2 and every script prompt get congested with side detail. Global ranking gets noisier. Cost grows with detail. Recap quality depends on prompt size (lost-in-the-middle). |
| **Main + secondary layers built by separate passes** | The secondary layer re-reads the subtitles, which doubles cost. Its facts aren't linked to main beats, so you can't ask "which side act caused this main beat?" (exp13: *Gunther told Rachel* was invisible to the main summary). The two layers drift and contradict each other. |
| **Fact base + views (recommended)** | One extraction pass at ~+25% output (exp13 O3). Every fact links to evidence *and* to the beats it belongs to. Any number of views, each small. Deep detail is fetched on demand by zoom/lens passes that cache back into the fact base. |

---

## The four tiers

```
 T0  EVIDENCE      cues (text, time, SDH) · speakers + voice clusters · scenes · shots · keyframes · visual notes
        │  (deterministic + P1 speaker/scene pass + P1v vision)                       immutable per media version
        ▼
 T1  FACTS         one row per atomic thing that happens, for EVERY character in EVERY scene:
                   act (who → type → target, cost) · state change (learns / feels / wants / relationship Δ)
                   · reveal / secret · quote · joke · moment (AV intensity)  — each with L-id evidence
        │  (P1, same call as scene cards: the "character ledger")                     append-only, versioned
        ▼
 T2  STRUCTURE     beats = clusters of facts that move a story · threads/arcs · edges (requires / pays_off /
                   caused_by / revealed_by / callback) · turning points · characters (roster, aliases, roles)
        │  (P2 integrate: sees beats + roster, NOT raw facts)                         small, re-derivable
        ▼
 T3  VIEWS         main_spine · character:<name> · trait:<name>/<trait> · thread:<id> · previously_on:<ep>
                   · theme:<text> · qa index — each = selected facts/beats + per-view salience + cached text
                   (built on demand by a view builder; cached by hash of inputs)
```

### The key idea: salience lives on the edge between a fact and a view, not on the fact

A fact has no single "importance". *"Gunther tells Rachel about the Xerox girl"* is P0 for `character:Gunther`,
P1 for `main_spine` as the *cause* of the breakup, and irrelevant for `trait:Joey/good-friend`. So:

```
fact_view(view_id, fact_id, salience 0-100, tier P0-P3, role "cause|payoff|texture|…", reason)
```

The main spine stays clean because its salience rows are computed only for the facts its beats contain. Side views
get their own rows, computed lazily when the view is first requested.

---

## Schema sketch (extends `recaplib/schema.sql`)

```sql
-- T1 facts (the ledger). One P1 call per chunk fills cards + facts together.
CREATE TABLE fact (
  id TEXT PRIMARY KEY, media_id TEXT, scene_id TEXT, cue0 INT, cue1 INT, t0 REAL, t1 REAL,
  kind TEXT CHECK(kind IN ('act','state','reveal','quote','joke','moment','visual')),
  actor TEXT, act_type TEXT,            -- helps|defends|sacrifices|gifts|advises|lies|betrays|mocks|threatens|kills|…
  target TEXT, cost INT,                -- cost 0-3: how much it costs the actor (drives "good friend" ranking)
  field TEXT, value TEXT,               -- for 'state': learns/feels/wants/relationship:<other>
  text TEXT,                            -- one-line paraphrase
  intensity INT, confidence REAL, source TEXT,   -- 'P1' | 'P1v' | 'zoom' | 'lens' | 'human'
  version INT);
CREATE TABLE beat_fact (beat_id TEXT, fact_id TEXT, role TEXT);       -- T2 ↔ T1 links
CREATE TABLE edge (src TEXT, dst TEXT, kind TEXT);                    -- requires | pays_off | caused_by | revealed_by | callback
CREATE TABLE view (id TEXT PRIMARY KEY, kind TEXT, params TEXT, inputs_hash TEXT, built_at TEXT, summary TEXT);
CREATE TABLE fact_view (view_id TEXT, fact_id TEXT, salience REAL, tier TEXT, role TEXT, reason TEXT);
CREATE TABLE detail (fact_id TEXT, text TEXT, cue INT, source TEXT);  -- zoom/lens harvest cache (quotes, numbers, callbacks)
CREATE INDEX fact_actor ON fact(actor, act_type);   -- trait queries become index lookups
CREATE VIRTUAL TABLE fact_fts USING fts5(id, text); -- plus vectors over fact/beat/view text
```

## Pass flow and what each pass sees (this is what avoids congestion)

| Pass | Reads | Writes | Prompt stays small because… |
|---|---|---|---|
| P0 ingest (tools) | media, subs | T0 | – |
| **P1 cards + ledger** (one call per ~160 lines) | chunk lines + roster + story-so-far | scenes, speakers, **facts for every character**, candidate beats | local window only |
| P1v vision | keyframes of dialogue gaps | visual facts | per gap |
| **P2 integrate** | **beats + roster only** (facts summarized as beat text) | threads, tiers, edges, TPs, `main_spine` view | never sees raw facts → the central flow stays uncongested |
| P2c causal links | for each P0/P1 beat: facts in its scene ±1 | `caused_by` / `revealed_by` edges to *any* character | per beat, tiny; this is what surfaces "Gunther caused the breakup" |
| View builder (on demand) | an index query over facts (+ edges) → candidates | `fact_view` rows, ordered story, cached text | only the view's facts (1–5% of the corpus for a side character, exp13) |
| Zoom / lens (on demand) | cited lines of the view's facts | `detail` rows (quotes, numbers) and corrections | only those lines; cached forever |

## How each recap type maps to a view

| Recap | View query (T1/T2) → then the shared pipeline (select → script → verify → render) |
|---|---|
| Main recap, any duration | `main_spine` beats by global tier, nested MCKP (exp06) |
| Villain / side character story | facts where `actor = X` or `target = X`, plus beats with `caused_by/revealed_by = X`, ordered by time; salience = arc relevance (exp13) |
| "All the times Joey was a good friend" | `fact WHERE actor='Joey' AND act_type IN (helps, defends, sacrifices, gifts, comforts)`, LLM-verified, ranked by cost × intensity (exp15) |
| Unanticipated trait ("every time Joey misunderstood a word") | no index hit → **trait sweep** over the character's scenes (≈190k tokens for Joey S1–S3), results written back as facts so the next query is free |
| Thread / theme / relationship ("Ross & Rachel") | thread beats + `relationship:<other>` state facts |
| "Previously on" | main_spine ∩ recent episodes, recency-weighted (PlotSnap) |
| Q&A / search (linger) | hybrid FTS + vectors over facts, beats and views, with speaker-attributed lines (exp10) |

## Why this is the optimal trade-off

- **Accuracy of the main story** is unaffected by detail: P2 and the main scripts see beats, not facts.
- **Detail is complete by construction.** Every character is processed in every scene at extraction time, so hidden
  gems exist in T1 even if no view ever asked for them. Discovery then becomes a query ("facts where a minor
  character `caused_by` a P0 beat").
- **Cost is front-loaded once** (+~25% on P1), and everything after that is cheap, cached and parallel. On-demand
  passes write back into T1, so the base gets richer with use, which suits linger.
- **Agentic and folder-friendly.** T0/T1 are append-only files per version. T2/T3 are derived and rebuildable.
  Human corrections go to a corrections log that every view re-applies (02_agentic_folder_protocol.md).
- **Evolvable.** New recap types are new view builders, not new layers or re-extractions.

## What to build first (in linger)

1. Extend P1 to emit the ledger (`fact` rows) alongside scene cards, with a fixed act taxonomy plus a free-text
   fallback.
2. Keep P2 on beats only, and add the per-beat causal-link pass.
3. Build a generic **view builder**: query, verify, order, then cache to `view` and `fact_view`. Implement three
   views first: `main_spine`, `character:X`, `trait:X/Y`.
4. Make zoom/lens passes write `detail` and `fact` rows back. Expose views in the UI as filterable "story lenses"
   feeding the existing selection, script and render pipeline.
