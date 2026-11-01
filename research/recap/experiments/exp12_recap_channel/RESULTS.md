# exp12 — Can the understanding layer produce "recap-channel" narration? (Panic Room, subtitles only, names scrambled)

Target style: YouTube movie-recap channels (present tense, a hook in the first line, dense chronological
coverage, punchy sentences, light roasting, cliffhanger transitions; ~8–15 min for a feature). We wrote a 6-minute
version (~900 words) of a 112-minute film from **dialogue only**, and evaluated it against the **independent Wikipedia
synopsis** (TRIPOD), the cited subtitle lines, and leak/flow metrics.

| | A: SUL only | C: SUL + zoom-in pass | notes |
|---|---|---|---|
| words / est. duration | 879 / 5:38 | 938 / 6:01 | |
| synopsis coverage (C + ½P, manual, 32 sentences) | 0.64 | **0.66** | 5/32 sentences unreachable from dialogue (gas ignited, struggle, killing of the gunman…) |
| contradictions with reference | 1 | **0** | the zoom-in re-read caught "who pumped the gas" |
| segments unsupported by cited lines | 1/30 | **0/27** | self-judged; partly-supported ≈ 20% in both (speaker/addressee inference) |
| real-world knowledge leakage | 0 | 0 | no real names / facts only known from outside the subtitles |
| grounding: content-word overlap with cited lines | 0.24 | **0.41** | |
| grounding: cosine(segment, cited lines) | 0.36 | **0.42** | |
| specifics per 100 words | 2.4 | **3.8** | quotes, numbers, names |
| dialogue references ("says/asks/…") | 11 | **35** | recap channels quote characters a lot |
| sentence length mean ± sd | 13.5 ± 7.7 | 13.0 ± 7.6 | mix of short punchy + long |
| punchy sentences (≤ 6 words) | 22% | 21% | |
| hooks / transitions | 6 / 23 | 5 / 23 | |
| embedding coverage@0.55 (automatic) | 0.81 | 0.69 | **misleading**: detail-heavy sentences look less like abstract synopsis text |

## What limits "recap-channel" quality, in order
1. **Dialogue-free action** (16% of synopsis missing, ~30% only partially covered, mostly *mechanisms*: how the
   swap happened, how the gunman died). → needs the vision pass (exp05c) on gaps between subtitles.
2. **Detail density / voice.** SUL-only narration is correct but generic; the **zoom-in pass** (re-read cited lines
   of the selected beats, harvest quotes/numbers/callbacks) is what gives the channel feel (+60% specifics, 3× quotes)
   and it also **corrects** SUL errors. Cost: only the selected beats' lines are re-read (~40% of the film here).
3. **Dangling setups.** Both narrations plant the door-sensor ("remember that") but never pay it off because the
   payoff is visual. Rule for P4-verify: a setup may only be teased if its `pays_off` partner is in the selection.
4. **Speaker/addressee inference** accounts for most "partly supported" sentences → speaker layer (exp03) matters.
5. **Reference mismatch:** the dataset's screenplay is a draft (e.g. the burglar's motive is gambling in the draft,
   his child in the final film) — evaluation against a synopsis must flag draft/version differences (D).

## Not done here (needs independent API calls)
**Option B — single-pass narration straight from raw subtitles (no understanding layer)** cannot be measured
cleanly in-session: the same model had already built the understanding. The folder protocol (02_agentic_folder_protocol.md)
makes this a 1-command run with isolated contexts; the evaluation script here is reusable as-is.
