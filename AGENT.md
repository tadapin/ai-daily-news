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
- `daily-ai-news-generator/scripts/deduplicate_by_summary.py`
  - Reads `daily_articles.json` after summary generation.
  - Uses `hotchpotch/static-embedding-japanese` via `sentence-transformers` to detect near-duplicate summaries.
  - Keeps the article with the longest summary as the representative within each similar cluster.
  - Marks the remaining articles as duplicate candidates instead of deleting them from JSON.
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
uv run python daily-ai-news-generator/scripts/deduplicate_by_summary.py
uv run python daily-ai-news-generator/scripts/generate_html.py
uv run python daily-ai-news-generator/scripts/push_to_github.py --date YYYY-MM-DD --html docs/YYYY-MM-DD.html
```

- To run the fetch and HTML generation pipeline in one command:

```bash
./daily-ai-news-generator/scripts/run_daily_to_html.sh
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

- `daily-ai-news-generator/scripts/fetch_daily.py` loads `daily-ai-news-generator/local-llm.env` via `python-dotenv`.
- LLM access uses a local OpenAI-compatible Chat Completions server configured by `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_MODEL`, and optional `LOCAL_LLM_API_KEY`.
- The default local configuration is `http://127.0.0.1:1234/v1/` with `google/gemma-4-e2b`; no real API credential is required.
- Summary parallelism is controlled by `SUMMARY_CONCURRENCY` and defaults to `3`.
- Local benchmarking in this environment showed `SUMMARY_CONCURRENCY=5` outperforming `1` and `3` during the early summary phase, so treat `5` as a good starting point when GPU headroom is available.
- Summary-level deduplication uses `SUMMARY_DEDUP_MODEL` and `SUMMARY_DEDUP_THRESHOLD`; defaults are `hotchpotch/static-embedding-japanese` and `0.65`.
- `daily-ai-news-generator/local-llm.env` is intentionally tracked and should contain only copyable local defaults. Do not add provider credentials to it.
- When working in a worktree, confirm that the local LLM server is running before running scripts.

## Daily Publish Workflow

- Use `uv run python ...` or `.venv/bin/python ...`; do not rely on a bare `python` executable being available.
- The generation worktree may be detached and may have a stale or noncanonical `docs/archive-index.json`.
- Generate the daily HTML in the active worktree, but create the publish commit from a clean temporary clone when the active worktree is detached or has unreliable git metadata.
- Choose the publish base from remote refs. Use `origin/main` only when it already contains the prior published archive entries; otherwise base the commit on the latest previous `origin/automation/daily-ai-news-publish-YYYY-MM-DD` branch.
- Prefer `git ls-remote` for remote ref checks in detached worktrees because `git fetch` can fail when linked worktree metadata is not writable.
- In the publish clone, copy in only `docs/YYYY-MM-DD.html`, rerun `daily-ai-news-generator/scripts/push_to_github.py`, then verify that `docs/archive-index.json` starts with the new date and still includes recent prior dates.
- Commit only `docs/YYYY-MM-DD.html` and `docs/archive-index.json` for daily publish branches.
- Do not commit `.venv` or `daily-ai-news-generator/output/`.

## Operational Expectations

- Do not publish or commit a zero-article daily edition caused by network failure or local LLM failure.
- Validate `daily-ai-news-generator/output/daily_articles.json` before publishing. Confirm nonzero AI-filtered total, nonzero visible published count, duplicate-candidate count, and category breakdown.
- When updating daily content, verify that `docs/archive-index.json` and the target daily page remain in a coherent published state.
- Keep generated intermediate files out of git; `daily-ai-news-generator/output/` is intentionally ignored.
