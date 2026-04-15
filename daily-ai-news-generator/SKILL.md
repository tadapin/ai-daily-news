---
name: daily-ai-news-generator
description: 44本のRSSフィードから過去24時間のAIニュースを収集・要約・重複排除・AI関連フィルタリングして、このリポジトリの`docs/`に日次HTMLを生成するCodex用スキル。「Daily AI Newsを更新して」「今日のAIニュースを公開して」などの依頼や、Codexオートメーションでの日次更新時に使用する。
---

# Daily AI News Generator

44本のRSSフィードから過去24時間のAIニュースを収集し、日本語サマリー付きHTMLを生成して、このリポジトリのGitHub Pages用`docs/`を更新する。

## 使う場面

- `ai-daily-news` リポジトリを日次更新するとき
- `docs/YYYY-MM-DD.html` と `docs/archive-index.json` を更新するとき
- Codexオートメーションで定期実行するとき

## 前提

- カレントワーキングディレクトリはリポジトリルートにする
- リポジトリルートの`.env`に `OPENAI_API_KEY` を設定しておく
- OpenAI互換APIを使う場合は必要に応じて `OPENAI_BASE_URL` と `OPENAI_MODEL` も `.env` に設定しておく
- 要約の並列度は `.env` の `SUMMARY_CONCURRENCY` で調整し、未設定時は `3` を使う
- `git` でコミット・プッシュできる状態が望ましい
- Python環境は `uv` で管理する

```bash
uv sync
```

## 基本手順

### 1. 記事取得と要約

```bash
uv run python daily-ai-news-generator/scripts/fetch_daily.py
```

出力:
- `daily-ai-news-generator/output/daily_articles.json`

### 2. HTML生成

```bash
uv run python daily-ai-news-generator/scripts/generate_html.py
```

出力:
- `docs/YYYY-MM-DD.html`

### 3. アーカイブ更新

```bash
DATE=$(uv run python -c "from datetime import datetime, timezone, timedelta; print((datetime.now(timezone.utc)+timedelta(hours=9)).strftime('%Y-%m-%d'))")
uv run python daily-ai-news-generator/scripts/push_to_github.py --date "$DATE" --html "docs/$DATE.html"
```

このスクリプトは Codex 環境では GitHub API へ直接 push しない。`docs/archive-index.json` を更新し、必要なら `docs/YYYY-MM-DD.html` を所定位置へそろえるローカル整備用として使う。

### 4. Gitで反映

Codexオートメーションで公開まで行う場合は、変更内容を確認して通常のGit操作で反映する。

```bash
git status --short
git add docs daily-ai-news-generator
git commit -m "Update Daily AI News for $DATE"
git push origin HEAD
```

## 報告内容

実行後は次を簡潔に報告する。
- 取得件数
- タイトル重複排除後件数
- AI関連フィルタ後の最終件数
- カテゴリ別内訳
- 更新したファイル
- 必要なら公開URL

公開URL:
- トップページ: https://tadapin.github.io/ai-daily-news/
- 当日号: https://tadapin.github.io/ai-daily-news/YYYY-MM-DD.html

## スクリプトの処理フロー

`fetch_daily.py` の処理：
1. 44フィードから過去24時間の記事を取得
2. タイトルベースの重複排除（SequenceMatcher、閾値0.75）
3. OpenAI互換APIで日本語サマリー生成（2〜3文、十分な長さ）
4. OpenAI互換APIで AI 関連フィルタリング（AI/ML/LLM/自動化に無関係な記事を除去）
5. `daily-ai-news-generator/output/daily_articles.json` に出力

`generate_html.py` の処理：
- `daily_articles.json` を読み込みダークテーマのHTMLを生成
- 左サイドバー（カテゴリナビ・統計）＋右カードグリッドのレイアウト
- 出力: `docs/YYYY-MM-DD.html`

`push_to_github.py` の処理：
- `docs/archive-index.json` に対象日を追加
- 必要なら指定HTMLを `docs/YYYY-MM-DD.html` にそろえる
- Git操作自体は行わず、Codexまたはオートメーション本体に委ねる

## フィード一覧（44件）

| カテゴリ | 件数 | 主な情報源 |
|---|---|---|
| Anthropic | 7件 | Anthropic News/Research/Engineering、Claude Code Changelog等 |
| AI開発ツール | 5件 | Cursor、Ollama、Windsurf Blog/Changelog等 |
| AIベンダー | 13件 | OpenAI、Google DeepMind、Microsoft AI、AWS ML Blog、Hugging Face、NVIDIA等 |
| AIニュース・メディア | 8件 | MIT Technology Review、VentureBeat、TechCrunch AI、WIRED AI、The Verge等 |
| 研究者・ニュースレター | 10件 | Import AI、Ahead of AI、Simon Willison、Andrej Karpathy、Last Week in AI等 |
