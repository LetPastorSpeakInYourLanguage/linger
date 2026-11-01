# 01 — Literature review: LLM understanding of films & series from subtitles

*Scope: what the research says about (1) how much story understanding is recoverable from subtitles,
(2) multi-pass / hierarchical LLM processing of long narratives, (3) deciding what matters (saliency,
turning points), (4) who-said-what without speaker labels, (5) turning understanding into recaps,
trailers and narrated video. Each section ends with what we took into the experiments.*

---

## 1. Are subtitles enough? (Mostly yes for *what happens*. Not for *what it looks like*.)

| Evidence | Finding |
|---|---|
| **Video-MME** (Fu et al., CVPR 2025) — [paper](https://openaccess.thecvf.com/content/CVPR2025/papers/Fu_Video-MME_The_First-Ever_Comprehensive_Evaluation_Benchmark_of_Multi-modal_LLMs_in_CVPR_2025_paper.pdf) | Adding subtitles to frames raised Gemini 1.5 Pro on **long** videos by **+10.1 pts** (67.4 → 77.4). On multilingual long videos the gain was +16.7. Subtitles helped more than raw audio, and more on long than short videos. |
| **MovieRecapsQA** (Shaar et al., CVPR 2026) — [arXiv 2601.02536](https://arxiv.org/html/2601.02536), [data](https://huggingface.co/datasets/sshaar/movierecapsqa) | Built from YouTube recap videos aligned to films and their subtitles. Finds that *"removing visual input often improves model factuality"*, and that the bottleneck is **visual perception**, not reasoning. |
| **Long Story Short** (Chung & Yu, BMVC 2023) — [arXiv 2311.01233](https://arxiv.org/abs/2311.01233) | Summarize-then-search: per-clip subtitle(+caption) summaries form a "plot". QA retrieves clips by plot index. Zero-shot GPT-3 beat supervised models on MovieQA/DramaQA. |
| **ScreenWriter** (Mahon & Lapata, 2024) — [arXiv 2410.19809](https://arxiv.org/abs/2410.19809) | Plain ASR transcripts lack **scene breaks, speaker names and non-dialogue events**. Their pipeline adds MDL-based scene segmentation, face-bank naming and keyframe captions. A hierarchical summary from this automatic screenplay **beat summaries made from gold screenplays**. |

**Takeaway for us:** a subtitle-first design is well supported. The known blind spots are scene
structure, speaker identity, and purely visual events. We measured those blind spots ourselves
(exp05: 34% of a thriller's salient scenes contain no dialogue; exp05c: Tears of Steel's
"40 YEARS LATER" card and its giant robots are invisible to subtitles).

## 2. Multi-pass processing of very long narratives

| Work | Finding |
|---|---|
| **Recursively summarizing books** (Wu et al., OpenAI 2021) | Hierarchical chunk → merge summaries with human feedback. This is the template for book-length inputs. |
| **BooookScore** (Chang et al., ICLR 2024) — [arXiv 2310.00785](https://arxiv.org/abs/2310.00785) | **Hierarchical merging** gives more coherent summaries. **Incremental updating** keeps more detail but makes more coherence errors, except with large chunks (Claude 2 at 88k scored 90.9 vs 90.3). Bigger chunks help incremental updating, not hierarchical merging. |
| **FABLES** (Kim et al., 2024) | Faithfulness of book-length LLM summaries: most unfaithful claims concern events and character states. Omissions are common, and errors concentrate where the model must infer across distant parts. |
| **Lost in the middle** (Liu et al., 2023) | Long-context models under-use mid-context information. This argues for structured intermediate representations over one giant prompt. |

**Takeaway:** use a hybrid. Run **incremental scene-card passes** (P1) with a running "story so far"
and roster, so each chunk sees the past. Follow with a **global integration pass** (P2) that sees all
cards and assigns *global* importance. Keep everything as structured JSON with line-id evidence, so
later passes don't depend on fragile free text.

## 3. What matters: saliency & narrative structure

| Work | Finding |
|---|---|
| **TRIPOD — turning points** (Papalampidi, Keller & Lapata, EMNLP 2019) — [ACL](https://aclanthology.org/D19-1180/), [data](https://github.com/ppapalampidi/TRIPOD) | Five TPs (opportunity, change of plans, point of no return, major setback, climax) segment a film into acts. They come with gold scene-level TP labels for 15 test films, and a strong **position prior**. |
| **Screenplay summarization using latent narrative structure** (Papalampidi et al., ACL 2020) — [ACL](https://aclanthology.org/2020.acl-main.174/) | Treating TPs as latent improves extractive scene selection for CSI episodes, giving more complete and diverse summaries. |
| **Select & Summarize / MENSA** (Saxena & Keller, NAACL Findings 2024) — [arXiv 2404.03561](https://arxiv.org/abs/2404.03561), [code](https://github.com/saxenarohit/select_summ) | Salient scene = scene mentioned in the Wikipedia plot (human-aligned for 100 films). Summarizing **only salient scenes beats feeding the whole script**. Explicit content selection works. |
| **MovieSum** (Saxena & Keller, 2024) | 2,200 screenplays with Wikipedia summaries. Used by ScreenWriter for evaluation. |
| **"Previously on…" / PlotSnap / TaleSumm** (Singh, Srivastava & Tapaswi, CVPR 2024) — [paper](https://openaccess.thecvf.com/content/CVPR2024/papers/Singh_Previously_on_..._From_Recaps_to_Story_Summarization_CVPR_2024_paper.pdf) | Professional TV recaps used as labels for shot/dialog importance (24, Prison Break). **88% of recap shots come from the immediately preceding episode**, and recap shots are short (1.9 s). This shows that series recaps are strongly recency-weighted. |

**Takeaway:** importance is two-level. There is *local* salience (is something happening in this
scene?) and *global* salience (does the story need it?). Our P2 pass rescores every beat against
the whole story and adds **requires/pays-off edges** (setup → payoff), so short recaps stay
coherent. For series we weight by **arc importance** (exp07); recency weighting from PlotSnap
becomes an option for "previously on" mode.

## 4. Who said what (subtitles have no speaker names)

| Work | Finding |
|---|---|
| **"Hello! My name is… Buffy"** (Everingham et al., BMVC 2006) | Classic alignment of subtitles (timing) with fan transcripts (names), then face tracks. |
| **Character-aware audio-visual subtitling** (Korbar, Huh & Zisserman, 2024) — [arXiv 2401.12039](https://arxiv.org/html/2401.12039v1); follow-up [arXiv 2410.11068](https://arxiv.org/html/2410.11068) | Builds per-character **voice exemplars** from high-precision face-visible segments, then classifies all speech by voice. The follow-up adds an **LLM pass** that predicts unknown speakers from ±15 lines of named context. |
| **Bazinga!** (Lerner et al., LREC 2022) — [HF](https://huggingface.co/datasets/bazinga/bazinga) | 16 series, 400 h, speaker/addressee/entity-linking gold labels. This is the right benchmark for scaling exp03. |
| **Emory character-mining (Friends)** — [GitHub](https://github.com/emorynlp/character-mining) | 10 seasons with scene ids, speakers, crowd scene plots and FriendsQA. We used it (exp02/03/07/10). |

**Takeaway:** text alone gets you part of the way, and the LLM does much better than heuristics
(exp03: 62% vs 17%). Voice clusters are language-agnostic and complement it well: in exp03 they
named 25 of the 27 lines the LLM left unknown. The production design is **diarize → LLM names
clusters from dialogue context → LLM fills the rest**.

## 5. From understanding to recaps, trailers and narrated video

| Work | Finding |
|---|---|
| **AutoAD I/II/III** (Han et al., CVPR/ICCV 2023-24) — [AutoAD](https://openaccess.thecvf.com/content/CVPR2023/papers/Han_AutoAD_Movie_Description_in_Context_CVPR_2023_paper.pdf), [AutoAD II](https://openaccess.thecvf.com/content/ICCV2023/html/Han_AutoAD_II_The_Sequel_-_Who_When_and_What_in_ICCV_2023_paper.html) | Audio description must fit **dialogue gaps** ("when"), name characters via a **character bank** ("who"), and condition on previous ADs and subtitles ("what"). Directly relevant to placing narration around hero clips. |
| **Towards Automated Movie Trailer Generation (TGT)** (Argaw et al., CVPR 2024) — [arXiv 2404.03477](https://arxiv.org/abs/2404.03477) | Shot selection and ordering as seq2seq over shot features. It does not model dialogue or sound. |
| **TRAILDREAMS** (Balestri et al., 2024/2025) — [ICFSP](https://doi.org/10.1109/icfsp62546.2024.10785516), [OJCMT](https://doi.org/10.30935/ojcmt/16669) | An LLM selects key visual sequences and **quote clips**, writes the voice-over and picks music. Viewers preferred it to earlier automatic methods but not to human trailers. The **quote clip + standard clip** split is close to our hero_clip + narration B-roll design. |
| **MovieRecapsQA** (again) | Recap videos are dense, chronological, scene-by-scene and ~8–15 min long. Their structure (voice-over over aligned clips) is exactly our output format, and the dataset gives aligned recap↔film segments for future evaluation. |

## 6. Gaps the literature leaves (and where this project adds something)

1. **Duration-controllable, nested recaps.** None of the above lets a user move a slider from
   1 minute to 1 hour and get coherent, *nested* content. We frame it as a multiple-choice knapsack
   over beats with full/short/micro renderings, dependency edges and a nesting constraint (exp06).
2. **Style-conditioned narration over the same understanding** (dramatic/comedic, short, fan/silent,
   detailed). Trailer and recap work hard-codes a single style.
3. **Language-agnostic production.** Prior work assumes English audio or ASR. We read meaning only
   from English subtitle text and use audio only through language-independent signals: VAD for
   cut hygiene and subtitle re-sync, voice clusters for speakers, loudness for intensity (exp08/11).
4. **Persisted, queryable understanding** (a database of beats, edges, moments and turning points
   with timestamps) that serves recaps, Q&A and recomposition (linger), instead of a one-off
   summary (exp10).

## Datasets usable in this sandbox (GitHub-reachable)

- Tears of Steel (12 min open movie, English SRT, video with burned-in Chinese subs): `xiaotangii/tears-of-steel-dialogue-dataset`
- Friends S1–S10 (scenes, speakers, plots, QA): `emorynlp/character-mining`
- TRIPOD (99 screenplays, synopses, TP gold): `ppapalampidi/TRIPOD`
- MENSA salient-scene alignments (100 films): `saxenarohit/select_summ`
- *Blocked here but recommended:* Bazinga!, MovieSum, MovieRecapsQA, SummScreen (Hugging Face), and
  public-domain feature films (archive.org).
