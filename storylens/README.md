# storylens

**A local understanding layer for stories and talks, and recaps made from it.** It works for films, series and
telenovelas, and for **podcasts, talk shows, sermons and lectures**, in any spoken language, as long as you have
English subtitles or a timestamped transcript.

**You, storylens and the Claude desktop app share one folder:**
- **storylens** does the mechanical work: reading files, aligning, indexing, selecting, checking and rendering.
- **Claude** does all the thinking, by answering task files in the folder.
- **You** review.

There is no API key and nothing leaves your laptop except what Claude reads in that folder.

From one **understanding** per title, made once, you can make:
- the main story at any length: 60 s to unlimited, where a shorter recap is always contained in a longer one, and
  a 15-minute recap of three seasons keeps only the top-priority story;
- **a character's story**: the villain's side of a hero movie, or a side character's hidden arc across seasons;
- **trait / theme compilations**: "all the times Leo was a good friend";
- **what someone said about a topic**: "what Pastor X said about women", as a **no-narrator supercut** of their
  own words with lower thirds;
- **how a speaker builds ideas**: the recurring pattern of a preacher's moves (question → reading → story →
  application), shown as clips labelled by step;
- **the gist of a talk**: e.g. "under 5 minutes", narrated;
- **across all your sources at once**: search everything at the level of title, episode, point, claim or line,
  build collections, and recap a whole set of sources.

Styles: recap-channel, dramatic/comedic, short & direct, fan cut, detailed, character, compilation, clips-only.

```
evidence (subtitles, speech, shots) ─▶ FACTS (what every character/speaker does, says, feels, reveals; topics, stance)
        ─▶ STRUCTURE (beats/points, tiers P0–P3, threads/themes, turning/key points, causes) ─▶ LENSES
        ─▶ selection ─▶ script from the exact lines ─▶ checks ─▶ your review ─▶ voice + render
```

## Quick start (laptop)

```bash
git clone <this repo> && cd linger/storylens
python -m venv .venv && source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[voice]"
storylens demo                     # sample film + podcast, answered offline: checks ffmpeg, voices, rendering
storylens serve                    # → http://127.0.0.1:8765, and the workspace is ~/storylens-workspace
```

Then, in the **Claude desktop app**, give Claude the folder `~/storylens-workspace` and say **"do the storylens
queue"**. Claude reads `CLAUDE.md` there and takes it from there. You can also just talk to Claude:
- "Add my sermons folder as *Grace Church* and understand it."
- "What did the pastor say about forgiveness?"
- "Make a 3-minute recap-channel video of season 1."

Claude turns these into requests for storylens and answers the tasks they create.

You need **Python 3.10+** and **ffmpeg**. Step-by-step setup for Windows, macOS and Linux:
**[docs/QUICKSTART.md](docs/QUICKSTART.md)**.

## Documentation

| | |
|---|---|
| [docs/QUICKSTART.md](docs/QUICKSTART.md) | install, first title, CLI cheatsheet, troubleshooting |
| [docs/AGENTIC.md](docs/AGENTIC.md) | **working with Claude**: the workspace, tasks (`TASK.md` → `answer.json`), requests, review gates, instructions, corrections |
| [docs/METHODOLOGY.md](docs/METHODOLOGY.md) | the method in depth: the four tiers, every pass, lenses, selection, checks, rendering, and the research behind each choice |
| [../research/recap/](../research/recap/) | the experiments this design comes from (16 experiments, literature review) |

## Tests

```bash
pip install -e ".[dev]" && pytest -q
```
