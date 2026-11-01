# exp15 — Trait / theme compilations: "All the times Joey was a good friend" (Friends S1–S3)

**Answer: yes, it's possible, but not with semantic search over the current layer.** It needs *behavior-level*
annotations per scene (the character ledger proposed in exp13), followed by an LLM verification pass.

## Measurements (Joey appears in 459 of 967 scenes)
| Method | P@20 strong | P@20 incl. weak |
|---|---|---|
| R1 dense: query vs Joey's own lines | 0.10 | 0.25 |
| R2 dense: query vs scene summary (understanding layer) | 0.05 | 0.20 |
| R3 dense: query vs whole scene dialogue | 0.15 | 0.25 |
| **random Joey scene (base rate)** | **0.10** | 0.22 |

- The pooled top-20s (56 scenes) held 6 strong moments (10.7%), which is the same as the random base rate (10%).
- Estimated **≈ 46 strong "good friend" moments** exist in S1–S3, so retrieval found ~13% of them.

**Why it fails:** "being a good friend" is a *judgment about behavior* in context: who helps whom, at what cost.
It isn't a topic. Dialogue embeddings match the words "friend" and "help", not the act. Scene summaries (crowd
plots) mostly describe the main plot and omit Joey's small supportive acts.

## What works (recommended design)
1. **Character ledger in P1** (exp13 O3). For every character in every scene, record
   `acts: [{type: helps|supports|defends|sacrifices|gifts|advises|lies|betrays|mocks|jealous…, target, cost, evidence: L-ids}]`
   plus wants/feels/learns. This is computed once, for everyone, at ~+25% P1 output.
   A trait compilation then becomes a structured query (`char=Joey AND type IN prosocial AND target IN friends`),
   followed by an LLM verify pass over the candidates and ranking by "how much it cost him" × emotional intensity.
2. **On-demand trait sweep** for traits the ledger didn't anticipate ("all the times Joey misunderstood a word").
   Classify every scene the character is in (S1–S3 Joey ≈ 182k words of scene text ≈ 320k input tokens).
   It is exhaustive and cheap with a small model, and parallel per episode.
3. **Then** reuse the normal pipeline: nested duration selection, a compilation script (title cards or a narrator
   linking moments), hero clips with original audio, and verification.

## Compilation outline from the moments found so far (10 of ~46 estimated)
| # | Ep / scene | Moment |
|---|---|---|
| 1 | s02_e15_c01 | His soap option gets picked up and he buys *two* recliners: one is Chandler's |
| 2 | s03_e01_c10–c12 | Agrees to Janice's "Day of Fun" — *for Chandler* — and comes back admitting he tried, he really did |
| 3 | s03_e08_c02 | Agonizes over whether to tell Chandler he saw Janice kissing her ex-husband |
| 4 | s03_e08_c09 | Is there for Chandler when Janice can't choose |
| 5 | s03_e09_c02 | Drags a heartbroken Chandler off the couch: "you have to start getting over her" |
| 6 | s03_e10_c12 | Saves Phoebe's beloved "dying" Christmas trees: "You saved them! You're the best!" |
| 7 | s03_e11_c14 | "He cannot do this to Phoebe" — marches upstairs to defend her |
| 8 | s03_e21_c05 | Surprises Chandler with a gift: a chick |
| 9 | s03_e22_c06 | Comforts Kate after the brutal review |
| (+ weak) | s01_e15_c08, s03_e08_c05 … | Coaching Ross through dirty talk; steering Chandler away from buying Janice pearls |

Any trait or theme works the same way: "every time Ross said 'we were on a break'", "Monica's competitiveness",
"every lie Chandler told", "the villain's acts of mercy". This is the main argument for making acts and their
evidence first-class in the understanding layer.
