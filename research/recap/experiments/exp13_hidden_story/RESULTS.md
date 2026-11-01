# exp13 — Hidden-story recaps: can the understanding layer tell a *non-main* story?

Examples asked for: the villain's story inside a hero movie, a side character's arc across a series.
Test subjects: **Lena**, the reluctant burglar of *Panic Room* (secondary antagonist; names scrambled), and
**Gunther** in *Friends* S1–S3 (background character, 43 lines across 16 episodes).

## 1. How much of the character's story is in the main-flow understanding?
| | Lena (film) | Gunther (series) |
|---|---|---|
| gold presence | 140 spoken lines, 32 scenes | 43 spoken + 19 mentioning utterances, 24 scenes, 18 episodes |
| **O1 main SUL** (beats that involve the character) | 19 beats; recall 57% of lines / 56% of scenes | 4 digest beats; **12.5%** of scenes |
| **O2a lens by name mentions** (±2 lines) | **3%** of lines / 6% of scenes — characters rarely say each other's names | 62.5% of scenes |
| **O2b lens by mentions + speaker attribution** | 100% / 100% at 52% of the film | 100% at **1.1%** of the corpus (200 utterances) |

→ The main flow under-represents secondary characters, by design (it keeps what the *main* plot needs).
→ Name search alone fails, so **speaker attribution is the prerequisite for character stories**.
→ The second pass is cheap for side characters (1% of tokens) and still affordable for leads.

## 2. What does the lens pass add? (dossiers with line evidence)
| | facts | already in main SUL | **new from lens** | new kinds |
|---|---|---|---|---|
| Lena | 17 | 11 | 6 | backstory, inner life ("woulda been a hell of a dad"), moral choices (objects to the gas, protests the beating), skill |
| Gunther | 14 | 3 | **11** | ex-soap-actor bond with Joey, café enforcer, inner monologue of love, rivalry with Ross, **the hidden turning point: Gunther is the one who tells Rachel about the Xerox girl, which ends Ross & Rachel**, failed ask-out, cocoa |

The Gunther finding is exactly the "hidden gem" pattern: a background character who **causes a P0 beat of the main
arc**, which the main-flow summary attributes to no one.

Reference check (Lena vs the 13 synopsis sentences about his real-film counterpart): covered 5, partial 4,
missing 3 (entering the room, locking it, and returning to shoot the gunman are dialogue-free action), 1 draft
difference. → The emotional climax of a villain's arc is often *visual*; the vision pass matters even more for
side stories.

## 3. Can the system discover hidden gems by itself?
`hidden_gem_ranking.json` ranks non-main characters by span × presence × co-occurrence with spine scenes.
It finds the obvious arcs (Carol, Susan, Richard, Janice) and puts Gunther 8th with the **widest span of any side
character (16 episodes)**, but with *zero* spine co-occurrence, even though he caused the breakup. Generic labels
("Woman", "Guy") also pollute the list. **Co-occurrence can't see causality.** Discovery needs the main pass to
record **who causes / reveals / witnesses each beat**.

## 4. Options and recommendation
| Option | What | Cost | Verdict |
|---|---|---|---|
| O1 main SUL only | filter beats by `who` | 0 | insufficient for side characters (12–57% recall), loses inner life |
| O2 on-demand character lens | speaker-attributed lines + mentions ±2 → dossier → narration | 1% (side) – 50% (lead) of P1 tokens | **best depth**; run when a user asks "tell me X's story" |
| O3 always-on character ledger in P1 | each scene card records, for *every* character present: `wants`, `does`, `learns`, `feels`, `relationship_delta`, `secret`, `caused_beats`, `revealed_info` | ≈ +25% P1 output tokens (≈3 chars × 25 tokens per scene) | **makes every character queryable and enables discovery** (causal involvement → hidden-influence score) |
| O4 vision pass on the character's dialogue-free scenes | keyframes where the character is on screen but silent | small | needed for villain climaxes (exp05c / §2) |

**Recommended:** O3 always (cheap, makes the layer nuance-capable), O2 on demand (depth and quotes), O4 for the
action gaps, all on top of the speaker layer (exp03). Hidden-gem discovery score =
`span × presence × (1 + caused_or_revealed(P0/P1 beats))`, plus inner-life lines (asides, confessions).
