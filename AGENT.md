# Agent Notes

## Repository Purpose

- This repository publishes the `Daily AI News` GitHub Pages site.
- Public pages are served from `docs/`.
- The project also contains generator scripts under `daily-ai-news-generator/` so daily content can be rebuilt and republished from the same repository.

## Published Output

- `docs/index.html`: archive landing page. It renders the archive as a month-by-month calendar view and links to each daily edition.
- `docs/YYYY-MM-DD.html`: one generated page per day.
- `docs/archive-index.json`: list of published dates used by `docs/index.html`.

## Generator Scripts

- `daily-ai-news-generator/scripts/fetch_daily.py`
  - Fetches recent items from 44 RSS feeds.
  - Deduplicates by title similarity.
  - Uses an OpenAI-compatible API to generate Japanese summaries.
  - Uses the same OpenAI-compatible API for summary generation and AI relevance filtering.
  - Writes `daily-ai-news-generator/output/daily_articles.json`.
- `daily-ai-news-generator/scripts/generate_html.py`
  - Reads `daily_articles.json`.
  - Generates `docs/YYYY-MM-DD.html`.
  - Generated daily pages include local-only saved state UI using `localStorage` with labels `保存` / `保存済み`.
- `daily-ai-news-generator/scripts/push_to_github.py`
  - Updates `docs/archive-index.json`.
  - Ensures the generated daily HTML is in the expected `docs/` location.
  - Does not push by itself; git commit/push is handled separately.
- `daily-ai-news-generator/scripts/serve_docs.py`
  - Runs a simple local server for `docs/`.
  - Use this when `file://` access breaks `fetch('archive-index.json')` on the archive page.

## Python Environment

- Python is managed with `uv`.
- Project metadata lives in `pyproject.toml`.
- Python version target is recorded in `.python-version`.
- Typical setup:

```bash
uv sync
```

- Typical execution:

```bash
uv run python daily-ai-news-generator/scripts/fetch_daily.py
uv run python daily-ai-news-generator/scripts/generate_html.py
uv run python daily-ai-news-generator/scripts/push_to_github.py --date YYYY-MM-DD --html docs/YYYY-MM-DD.html
```

- For real-time progress logs from `fetch_daily.py`, prefer unbuffered execution:

```bash
.venv/bin/python -u daily-ai-news-generator/scripts/fetch_daily.py
```

- Local preview:

```bash
uv run python daily-ai-news-generator/scripts/serve_docs.py
```

## Secrets And Environment Files

- `daily-ai-news-generator/scripts/fetch_daily.py` loads the repository-root `.env` via `python-dotenv`.
- LLM access depends on `OPENAI_API_KEY` being available in that `.env`.
- For OpenAI-compatible providers, set `OPENAI_BASE_URL` and `OPENAI_MODEL` in `.env` as needed.
- Summary parallelism is controlled by `.env` variable `SUMMARY_CONCURRENCY` and defaults to `3`.
- Local benchmarking in this environment showed `SUMMARY_CONCURRENCY=5` outperforming `1` and `3` during the early summary phase, so treat `5` as a good starting point when GPU headroom is available.
- When working in a worktree, confirm that the active worktree can also read the required environment configuration before running scripts.
- If `.env` or equivalent environment configuration is missing, or if `OPENAI_API_KEY` has not been restored, stop and ask the user how they want secrets restored before proceeding.
- Do not guess, synthesize, or silently replace secret values.

## Operational Expectations

- Do not publish or commit a zero-article daily edition caused by network failure or missing secrets.
- When updating daily content, verify that `docs/index.html`, `docs/archive-index.json`, and the target daily page remain in a coherent published state.
- Keep generated intermediate files out of git; `daily-ai-news-generator/output/` is intentionally ignored.
