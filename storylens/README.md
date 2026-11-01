# storylens

**Subtitle-first understanding and automatic recaps** for films, series and telenovelas, and for **podcasts, talk
shows, sermons and lectures**, in any spoken language, as long as you have English subtitles or a timestamped
transcript.

It builds a durable **understanding** of a title once, then produces as many **recaps** as you like from it:
- the main story at any length (60 s … unlimited; a shorter recap is always contained in a longer one),
- **a character's story**: the villain's side of a hero movie, or a side character's hidden arc across seasons,
- **trait / theme compilations**: "all the times Leo was a good friend",
- **what someone said about a topic** ("what Pastor X said about women", "what a guest said about the meaning of
  life"), as a **no-narrator supercut** of their own words with lower thirds,
- **across all your sources at once**: search everything at the level of title, episode, point, claim or line; build
  collections; recap a whole set of sources,
- styles: recap-channel, dramatic/comedic, short & direct, fan cut, detailed, character, compilation, clips-only.

You review at gates (understanding → script → final cut), and an AI agent (or you) can do any LLM step through
plain files.

```
evidence (subtitles, speech, shots) ─▶ FACTS (what every character does, learns, feels, reveals)
        ─▶ STRUCTURE (beats, tiers, threads, turning points, causes) ─▶ LENSES (main · character · trait · storyline)
        ─▶ selection ─▶ script ─▶ independent verification ─▶ your review ─▶ voice + render
```

## Quick start (laptop)

```bash
git clone <this repo> && cd linger/storylens
python -m venv .venv && source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[voice]"                                  # add ,system-voice for an offline system voice fallback
storylens demo                                             # sample story, offline mock LLM — checks your setup
export ANTHROPIC_API_KEY=sk-ant-...                        # Windows: setx ANTHROPIC_API_KEY sk-ant-...  (new terminal)
storylens serve                                            # → http://127.0.0.1:8765
```

You also need **Python 3.10+** and **ffmpeg** on your PATH for video. Step-by-step instructions for
Windows, macOS and Linux, the first-title walkthrough and troubleshooting are in **[docs/QUICKSTART.md](docs/QUICKSTART.md)**.

## Documentation

| | |
|---|---|
| [docs/QUICKSTART.md](docs/QUICKSTART.md) | install, first title, CLI cheatsheet, costs, troubleshooting |
| [docs/METHODOLOGY.md](docs/METHODOLOGY.md) | the method in depth: four tiers, every pass and prompt, lenses, selection, verification, rendering, and the research behind each choice |
| [docs/AGENTIC.md](docs/AGENTIC.md) | the folder protocol: let Claude Code (or a person) answer LLM steps, review gates, instructions, autonomy |
| [../research/recap/](../research/recap/) | the experiments this design comes from (15 experiments, literature review) |

## LLM backends

| backend | when | notes |
|---|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` set (auto-detected) | Claude via the official SDK. Default model `claude-opus-5-5`, with JSON-schema structured outputs, streaming, prompt caching, and **server-side refusal fallback enabled** (`fallbacks: "default"`; disable with `"fallbacks": false` in settings). Set `bulk_model` (e.g. `claude-sonnet-5-5`) to make the per-chunk passes cheaper. |
| `folder` | no key; or you want an agent / human in the loop | every LLM step waits as files until Claude Code (see AGENTS.md in your workspace) or you write the answer |
| `mock` | demos & tests | deterministic offline heuristics, low quality |

## Tests

```bash
pip install -e ".[dev]" && pytest -q
```
