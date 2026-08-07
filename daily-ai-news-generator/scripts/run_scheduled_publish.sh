#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"
exec uv run python daily-ai-news-generator/scripts/publish_daily.py --publish
