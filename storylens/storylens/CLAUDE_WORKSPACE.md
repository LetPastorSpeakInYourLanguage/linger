# storylens workspace: instructions for Claude

This folder is shared by the user, the storylens app running on their laptop, and you (Claude). storylens does the
mechanical work: reading subtitle and transcript files, audio and video, indexing, selecting, timing and rendering.
**You do all of the thinking.** Every understanding, lens, script and review step is a task file here that you
answer. There is no API; nothing happens until you answer.

For storylens to react, it must be running on the laptop: `storylens serve` (web app + watcher) or `storylens watch`.

## 1. Every time you start: do the queue

Read `tasks/QUEUE.md`. For every open task, top to bottom:
1. Open `tasks/<id>/TASK.md`. It is self-contained: what to do, the input (numbered subtitle or transcript lines,
   sometimes images in the same folder), and the exact JSON shape of the answer.
2. Write `tasks/<id>/answer.json` with valid JSON in exactly that shape. Do not edit any other file in the folder.
3. A few seconds later, check for `tasks/<id>/ANSWER_ERRORS.md`. If it appears, fix the problems it lists and write
   `answer.json` again.

Answering tasks unlocks new ones: integration after every part of an episode, the script after a lens, and so on.
Re-read `tasks/QUEUE.md` until it says "Nothing to do right now". Many tasks at once are normal: understanding a
season queues one task per part of each episode. Work through them all.

QUEUE.md also lists **reviews waiting for the user** (`jobs/<job>/review/<gate>.md`). Summarize the review for the
user. Write a decision only when the user tells you to (see the `decide` request below).

## 2. How to answer well

- **Use only the input in the task**: the lines and images given. Never add what you know about the title from
  elsewhere: no plot facts, no names, no later events. Spoilers come only from the lines you were given.
- **Cite exactly**: line ids such as `L123` and spans `[first, last]` must come from the input.
- **The facts ledger is the point.** Understanding tasks ask for every act, state change, reveal, quote, joke and
  emotional moment of *every* character or speaker, not just the main plot. Side characters and villains matter
  ("all the times Joey was a good friend", "the villain's story", "what the pastor said about women"). Be
  exhaustive; long answers are fine.
- Write in English, whatever the source language.
- When a speaker is unclear, say so (`"?"` or the field the schema gives for it). Do not guess confidently.
- When a task gives a CONTINUITY section ("story so far"), keep names and ids consistent with it.

## 3. Asking storylens to do things: requests

Write a JSON file (any name) into `requests/new/`. storylens picks it up within a few seconds and moves it:
- to `requests/done/<name>.json` with the job id (results are in `jobs/<job>/`), or
- to `requests/failed/<name>.json` with the error.

```json
{"do": "add_title", "name": "Grace Church", "kind": "sermon", "folder": "/Users/me/Sermons", "cast": ["Pastor Ruth Adeyemi"]}
{"do": "understand", "title": "grace-church"}
{"do": "lens", "title": "my-show", "lens": "character:Marta"}
{"do": "recap", "title": "my-show", "lens": "main", "style": "recap_channel", "duration": 600, "instructions": "keep it light"}
{"do": "recap", "title": "grace-church", "lens": "topic:Pastor Ruth Adeyemi/women and marriage", "style": "clips", "duration": 300}
{"do": "recap", "title": "grace-church", "lens": "pattern:Pastor Ruth Adeyemi", "style": "clips", "duration": 240}
{"do": "recap", "collection": "all", "lens": "topic:/the meaning of life", "style": "clips", "duration": 600}
{"do": "find", "query": "meaning of life", "level": "claim"}
{"do": "decide", "job": "<job id>", "gate": "G2_script", "decision": "approve"}
{"do": "decide", "job": "<job id>", "gate": "G2_script", "decision": "revise", "notes": "less snark; mention Ines saved them"}
{"do": "send", "job": "<job id>", "text": "focus on the brothers"}
{"do": "rerun", "job": "<job id>"}
{"do": "collection", "name": "Philosophy", "titles": ["within-reason", "long-table"]}
```

- **kinds**: film, series, podcast, talkshow, sermon, lecture.
- **lenses**:
  - `main`
  - `character:NAME`
  - `thread:ID`
  - `trait:[ACTOR/]WHAT` (e.g. `trait:Joey/being a good friend`)
  - `topic:[SPEAKER/]WHAT`
  - `pattern:[SPEAKER]`: how a speaker builds ideas
  - `overview`
- **styles**: recap_channel, dramatic_comedic, short_direct, fan_silent (clips with a little narration),
  detailed_full, character, compilation, clips (no narrator: the speakers' own words with lower thirds).
- **duration**: in seconds; `0` means unlimited (cover everything).
- A short recap keeps only the highest-priority story (P0/P1). A longer one adds detail.

Every job action also accepts `"instructions"` and `"autonomy"`:
- `gates` (default): the user decides at each review.
- `autopilot`: approve automatically when the checks pass.
- `auto`: approve everything.

## 4. Where things are (read these to answer the user directly)

| file | what |
|---|---|
| `CATALOG.md` | everything that exists: titles, episodes, characters/speakers, threads, topics, lenses, recent jobs |
| `library/<title>/understanding/CURRENT` | the current understanding version, e.g. `v002` |
| `library/<title>/understanding/<v>/bible.json` | logline, characters, threads, turning points, themes |
| `library/<title>/understanding/<v>/beats.jsonl` | the story beats with tier P0–P3, score, causes, lines |
| `library/<title>/understanding/<v>/facts.jsonl` | the facts ledger: who did/said/felt/revealed what, topics, stance, lines |
| `library/<title>/views/<lens>/view.json` | a built lens: the ordered items it selected |
| `library/<title>/instructions.md`, `instructions.md` | the user's notes for one title and for everything |
| `library/<title>/corrections.jsonl` | fixes to the understanding (`{"target": id, "field": "tier", "value": "P0"}`) |
| `jobs/<job>/state.json`, `jobs/<job>/artifacts/` | job status; outputs (view.json, script.json, report.md, recap.mp4) |

To answer a question about a title ("what happens to Marta in season 2?", "what did the pastor say about money?"),
you can read the facts and beats directly. That is often faster than starting a job. For questions across many
sources, use a `find` request; its results land in `requests/done/<name>.result.md`.
