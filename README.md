# linger

| folder | what |
|---|---|
| [`storylens/`](storylens/) | **Story understanding + automatic recaps app.** Subtitle-first understanding (evidence → facts → structure → lenses), recaps in any style and length, character stories, trait compilations, review gates, and agentic folder-based LLM steps. **Start here:** [storylens/README.md](storylens/README.md) · [Quick start](storylens/docs/QUICKSTART.md) · [Methodology](storylens/docs/METHODOLOGY.md) · [Agentic use](storylens/docs/AGENTIC.md) |
| [`research/recap/`](research/recap/) | The research behind storylens: literature review, 15 experiments, architecture docs (`01_literature.md`, `02_agentic_folder_protocol.md`, `03_understanding_architecture.md`) |
| [`app/`](app/) | The original Recomposer studio (cutter, recompositions, dubbing) — see [app/README.md](app/README.md) |

```bash
cd storylens && python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[voice]" && storylens demo && storylens serve       # → http://127.0.0.1:8765
```
