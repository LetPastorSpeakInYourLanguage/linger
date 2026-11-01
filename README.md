# linger

| folder | what |
|---|---|
| [`storylens/`](storylens/) | **The understanding layer + recaps, run with the Claude desktop app through a shared folder (no API).** Films, series, podcasts, sermons: evidence → facts → structure → lenses; recaps in any style and length, character stories, trait compilations, topic and pattern supercuts, cross-source search. **Start here:** [storylens/README.md](storylens/README.md) · [Quick start](storylens/docs/QUICKSTART.md) · [Working with Claude](storylens/docs/AGENTIC.md) · [Methodology](storylens/docs/METHODOLOGY.md) |
| [`research/recap/`](research/recap/) | The research behind storylens: literature review, 16 experiments, architecture docs (`01_literature.md`, `02_agentic_folder_protocol.md`, `03_understanding_architecture.md`) |
| [`app/`](app/) | The original Recomposer studio (cutter, recompositions, dubbing) — see [app/README.md](app/README.md) |

```bash
cd storylens && python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[voice]" && storylens demo && storylens serve       # → http://127.0.0.1:8765
# then, in the Claude desktop app, open ~/storylens-workspace and say: "do the storylens queue"
```
