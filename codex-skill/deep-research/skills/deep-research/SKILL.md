---
name: deep-research
description: Run the local Deep Research Agent for evidence-oriented web research. Use when a user asks for a current industry analysis, hot-topic timeline, policy/academic/technical research, source-backed report, or PDF research deliverable. The skill invokes the project's CLI/API, preserves source and evidence warnings, and never presents unverified claims as confirmed facts.
---

# Deep Research Skill

## When To Use

Use this skill for research that needs current web information, multiple search angles, source-backed findings, a timeline, or a reusable Markdown/PDF report.

Do not use it for casual questions, private data lookup, medical/legal decisions, or a claim that requires guaranteed truth. For sensitive hot topics, explicitly preserve `reported_not_verified`, `rumor`, `disputed`, and `unknown` statuses.

## Local Project

The default project path is:

`C:\Users\haiju\Desktop\学习\deep-research-agent`

From that directory:

```powershell
uv run research "<question>" --max-queries 3 --use-memory
```

For a PDF deliverable:

```powershell
uv run research "<question>" --max-queries 3 --use-memory --pdf
```

For the web UI:

```powershell
uv run --extra web streamlit run app.py
```

## Research Modes

Use `--research-mode hot_topic` in the API, or let the project infer a mode from the question:

- `hot_topic`: timeline, independent sources, rumor/confirmation separation
- `policy`: government and regulator sources
- `academic`: papers, publication dates, limitations
- `technical`: official docs, repositories, reproducible details
- `industry`: company filings, market reports, statistics

Force a mode from the CLI when the intent is known:

```powershell
uv run research "<question>" --research-mode hot_topic --max-queries 4 --use-memory --pdf
```

The report includes evidence coverage, epistemic status, confidence, source type, and source-quality signals. Low-evidence output receives one bounded repair pass before it is saved.

## Quality Rules

1. Keep the current date in the research context.
2. Prefer Tavily when `TAVILY_API_KEY` is configured; otherwise use the language-aware fallback chain.
3. Inspect the generated source list and evidence coverage.
4. Run source verification for important reports.
5. Treat social posts and single-source claims as unverified until independently corroborated.

## Troubleshooting

- If Streamlit shows an old function signature, restart the Streamlit process.
- If Ollama is unavailable, start `ollama serve` and verify `http://127.0.0.1:11434/api/version`.
- If the project moved, run `uv sync --extra dev --extra web` to rebuild its virtual environment.
