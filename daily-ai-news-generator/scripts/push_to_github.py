#!/usr/bin/env python3
"""
Daily AI News → docs 更新スクリプト

生成されたHTMLをこのリポジトリのdocs/に配置し、
archive-index.jsonを更新する。

使い方:
    python3 push_to_github.py --date 2026-03-13 --html /path/to/2026-03-13.html
"""

import argparse
import json
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "docs"
INDEX_PATH = DOCS_DIR / "archive-index.json"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="日付 (YYYY-MM-DD)")
    parser.add_argument("--html", required=True, help="生成されたHTMLファイルのパス")
    args = parser.parse_args()

    date = args.date  # e.g. "2026-03-13"
    html_path = Path(args.html).resolve()

    if not html_path.exists():
        raise FileNotFoundError(f"HTMLファイルが見つかりません: {html_path}")

    print("=== docs 更新開始 ===")
    print(f"日付: {date}")
    print(f"HTML: {html_path}")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n[1] HTMLファイルを配置: docs/{date}.html")
    dest_html = DOCS_DIR / f"{date}.html"
    if html_path != dest_html.resolve():
        shutil.copy2(html_path, dest_html)

    print("\n[2] archive-index.jsonを更新...")
    if INDEX_PATH.exists():
        with INDEX_PATH.open("r", encoding="utf-8") as f:
            dates = json.load(f)
    else:
        dates = []

    if date not in dates:
        dates.append(date)
    dates.sort(reverse=True)  # 新しい順

    with INDEX_PATH.open("w", encoding="utf-8") as f:
        json.dump(dates, f, ensure_ascii=False, indent=2)
    print(f"  アーカイブ一覧: {dates}")

    print("\n[3] docs 更新完了")
    print("必要ならこのあと Codex か automation 側で git add / commit / push を実行してください。")
    print(f"URL: https://tadapin.github.io/ai-daily-news/{date}.html")
    print(f"トップ: https://tadapin.github.io/ai-daily-news/")

if __name__ == "__main__":
    main()
