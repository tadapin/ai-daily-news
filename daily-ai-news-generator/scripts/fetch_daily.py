#!/usr/bin/env python3
"""
Daily AI News - フィード取得・重複排除・サマリー生成スクリプト
ai-news-feedsスキルの全フィードから過去24時間の記事を収集する

フィード一覧はai-news-feedsスキル（/home/ubuntu/skills/ai-news-feeds/SKILL.md）をベースにしつつ、
ローカル追加の公式RSSも含む（全44件）。

処理フロー:
  1. 全フィードから記事取得
  2. タイトルベースの重複排除（URL一致 + 文字列類似度）
  3. Geminiでサマリー生成
  4. Geminiでサマリーベースの意味的重複排除
  5. GeminiでAI関連フィルタリング
  6. JSON出力
"""

import feedparser
import requests
import re
import json
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from google import genai
from google.genai import types
from difflib import SequenceMatcher

# ===== 設定 =====
DAYS_BACK = 1
OLSHANSK_BASE = "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DailyAINews/1.0)"}

# LLMによる重複・関連性チェックのバッチサイズ
FILTER_BATCH_SIZE = 20
REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "daily-ai-news-generator" / "output"
OUTPUT_JSON = OUTPUT_DIR / "daily_articles.json"
GEMINI_MODEL = "gemini-3-flash-preview"
ENV_PATH = REPO_ROOT / ".env"

# ===== カテゴリ別フィード定義（ai-news-feedsスキルと完全一致） =====

FEED_CATEGORIES = {
    # --- Olshansk/rss-feeds: Anthropic関連 ---
    "Anthropic": [
        ("Anthropic（総合）",         OLSHANSK_BASE + "feed_anthropic.xml"),
        ("Claude Code Changelog",    OLSHANSK_BASE + "feed_anthropic_changelog_claude_code.xml"),
        ("Anthropic Engineering",    OLSHANSK_BASE + "feed_anthropic_engineering.xml"),
        ("Anthropic News",           OLSHANSK_BASE + "feed_anthropic_news.xml"),
        ("Anthropic RED",            OLSHANSK_BASE + "feed_anthropic_red.xml"),
        ("Anthropic Research",       OLSHANSK_BASE + "feed_anthropic_research.xml"),
        ("Claude",                   OLSHANSK_BASE + "feed_claude.xml"),
    ],
    # --- Olshansk/rss-feeds: AI開発ツール ---
    "AI開発ツール": [
        ("Cursor",                   OLSHANSK_BASE + "feed_cursor.xml"),
        ("Ollama",                   OLSHANSK_BASE + "feed_ollama.xml"),
        ("Windsurf Blog",            OLSHANSK_BASE + "feed_windsurf_blog.xml"),
        ("Windsurf Changelog",       OLSHANSK_BASE + "feed_windsurf_changelog.xml"),
        ("Windsurf Next Changelog",  OLSHANSK_BASE + "feed_windsurf_next_changelog.xml"),
    ],
    # --- Olshansk/rss-feeds: その他 + AIベンダー公式 ---
    "AIベンダー": [
        ("Google AI (Olshansk)",     OLSHANSK_BASE + "feed_google_ai.xml"),
        ("xAI News",                 OLSHANSK_BASE + "feed_xainews.xml"),
        ("Thinking Machines",        OLSHANSK_BASE + "feed_thinkingmachines.xml"),
        ("BlogSurge AI",             OLSHANSK_BASE + "feed_blogsurgeai.xml"),
        ("Dagster",                  OLSHANSK_BASE + "feed_dagster.xml"),
        ("OpenAI Research",          OLSHANSK_BASE + "feed_openai_research.xml"),
        ("OpenAI News",              "https://openai.com/news/rss.xml"),
        ("Google DeepMind",          "https://deepmind.google/blog/rss.xml"),
        ("Google AI Blog",           "https://blog.google/innovation-and-ai/technology/ai/rss/"),
        ("Microsoft AI",             "https://news.microsoft.com/source/topics/ai/feed/"),
        ("Microsoft AI Models",      "https://microsoft.ai/news-categories/models/feed/"),
        ("AWS ML Blog",              "https://aws.amazon.com/blogs/machine-learning/feed/"),
        ("Hugging Face Blog",        "https://huggingface.co/blog/feed.xml"),
        ("NVIDIA Deep Learning",     "https://blogs.nvidia.com/blog/category/deep-learning/feed/"),
    ],
    # --- AIニュースサイト ---
    "AIニュース・メディア": [
        ("MIT Technology Review AI", "https://www.technologyreview.com/topic/artificial-intelligence/feed/"),
        ("VentureBeat",              "https://venturebeat.com/feed"),
        ("TechCrunch AI",            "https://techcrunch.com/category/artificial-intelligence/feed"),
        ("WIRED AI",                 "https://www.wired.com/feed/tag/ai/latest/rss"),
        ("The Verge",                "https://www.theverge.com/rss/index.xml"),
        ("Ars Technica AI",          "https://arstechnica.com/ai/feed/"),
        ("AI News",                  "https://www.artificialintelligence-news.com/feed/"),
        ("The Batch (DeepLearning.AI)", OLSHANSK_BASE + "feed_the_batch.xml"),
    ],
    # --- 研究者ブログ・ニュースレター ---
    "研究者・ニュースレター": [
        ("Import AI (Jack Clark)",   "https://importai.substack.com/feed"),
        ("The Gradient",             "https://thegradient.pub/rss/"),
        ("Towards Data Science",     "https://towardsdatascience.com/feed"),
        ("Ahead of AI (S. Raschka)", "https://magazine.sebastianraschka.com/feed"),
        ("Simon Willison",           "https://simonwillison.net/atom/everything/"),
        ("Andrej Karpathy",          "https://karpathy.substack.com/feed"),
        ("Last Week in AI",          "https://lastweekin.ai/feed"),
        ("Chander Ramesh",           OLSHANSK_BASE + "feed_chanderramesh.xml"),
        ("Hamel Husain",             OLSHANSK_BASE + "feed_hamel.xml"),
        ("Paul Graham",              OLSHANSK_BASE + "feed_paulgraham.xml"),
    ],
}

load_dotenv(ENV_PATH)
client = genai.Client()

# ─── ユーティリティ ────────────────────────────────────────────────────────

def get_cutoff():
    return datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)

def parse_time(entry):
    for field in ['published_parsed', 'updated_parsed']:
        t = getattr(entry, field, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None

def fetch_feed(name, url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return feedparser.parse(resp.content)
    except Exception as e:
        print(f"  [SKIP] {name}: {e}")
        return None

def get_text(entry):
    content = ""
    if hasattr(entry, 'content') and entry.content:
        content = entry.content[0].get('value', '')
    elif hasattr(entry, 'summary'):
        content = entry.summary
    content = re.sub(r'<[^>]+>', ' ', content)
    content = re.sub(r'\s+', ' ', content).strip()
    return content[:2000]

def format_jst(dt):
    if dt:
        jst = dt + timedelta(hours=9)
        return jst.strftime("%Y-%m-%d %H:%M JST")
    return "日時不明"

# ─── Step 2: タイトルベースの重複排除（高速・LLM不要） ──────────────────────

def is_title_duplicate(title1, title2, threshold=0.75):
    ratio = SequenceMatcher(None, title1.lower(), title2.lower()).ratio()
    return ratio >= threshold

def deduplicate_by_title(articles):
    """URL一致 + タイトル文字列類似度による重複排除"""
    seen_urls = set()
    seen_titles = []
    result = []
    for art in articles:
        url = art.get("url", "")
        title = art.get("title", "")
        if url and url in seen_urls:
            continue
        if any(is_title_duplicate(title, t) for t in seen_titles):
            continue
        if url:
            seen_urls.add(url)
        seen_titles.append(title)
        result.append(art)
    return result

# ─── Step 3: サマリー生成 ────────────────────────────────────────────────────

def generate_text(prompt, max_output_tokens=300, temperature=0.3):
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type="text/plain",
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return (resp.text or "").strip()

def normalize_summary_text(text):
    summary = text.strip()
    summary = re.sub(r"^\s*(日本語サマリー|要約)\s*[:：]\s*", "", summary)
    summary = re.sub(r"^\s*サマリー\s*[:：]\s*", "", summary)
    summary = re.sub(r"^「", "", summary)
    summary = re.sub(r"」$", "", summary)
    return summary.strip()

def summarize(title, url, text, source):
    prompt = (
        "以下の記事を日本語で要約してください。"
        "必ず2〜3文で、合計120〜220文字程度にしてください。"
        "1文だけで終えず、何が起きたか、何が新しいか、なぜ重要かを含めてください。"
        "箇条書きは禁止です。"
        "見出し、前置き、説明、引用符は不要です。"
        "『日本語サマリー:』『要約:』のようなラベルは絶対に出力せず、要約本文だけをそのまま返してください。\n\n"
        f"情報源: {source}\n"
        f"タイトル: {title}\n"
        f"URL: {url}\n"
        f"本文（抜粋）: {text}\n\n"
        "要約本文のみを出力:"
    )
    retry_prompt = (
        "次の要約を書き直してください。"
        "短すぎます。必ず2〜3文、120〜220文字程度で、"
        "何が起きたか、何が新しいか、なぜ重要かを盛り込んでください。"
        "箇条書きは禁止です。"
        "見出し、前置き、説明、引用符は不要です。"
        "『日本語サマリー:』『要約:』のようなラベルは絶対に出力せず、要約本文だけを返してください。\n\n"
        f"タイトル: {title}\n"
        f"元記事情報: {text}\n\n"
        "要約本文のみを出力:"
    )
    try:
        summary = normalize_summary_text(
            generate_text(prompt, max_output_tokens=400, temperature=0.3)
        )
        sentence_count = len([s for s in re.split(r"[。.!?]+", summary) if s.strip()])
        if len(summary) < 80 or sentence_count < 2:
            summary = normalize_summary_text(
                generate_text(retry_prompt, max_output_tokens=400, temperature=0.2)
            )
        return summary.strip()
    except Exception as e:
        print(f"  [SUMMARY ERROR] {title[:40]}: {e}")
        return "（サマリー生成に失敗しました）"

# ─── Step 4: サマリーベースの意味的重複排除（LLM） ──────────────────────────

def deduplicate_by_summary_llm(articles):
    """
    全カテゴリをまたいだ意味的重複をLLMで検出・除去する。
    同じトピックを複数ソースが報じている場合、最初に登場したものを残す。
    """
    if len(articles) <= 1:
        return articles

    # 記事リストをLLMに渡して重複インデックスを返させる
    items_text = "\n".join(
        f"[{i}] {art['title']} （{art['source']}）\nサマリー: {art['summary'][:150]}"
        for i, art in enumerate(articles)
    )

    prompt = (
        "以下はAIニュース記事の一覧です。同じトピック・出来事を報じている記事が複数ある場合、"
        "最初に登場したもの（番号が小さいもの）を「残す」とし、それ以外を「重複」として除去してください。\n\n"
        "完全に同じ内容でなくても、同じニュースを別の視点で報じているものも重複とみなしてください。\n\n"
        f"{items_text}\n\n"
        "除去すべき記事の番号をカンマ区切りで返してください。除去すべきものがなければ「なし」と返してください。\n"
        "例: 2,5,8\n"
        "回答（番号のみ）:"
    )

    try:
        answer = generate_text(prompt, max_output_tokens=100, temperature=0).strip()
        if answer == "なし" or not answer:
            return articles

        remove_indices = set()
        for part in answer.split(","):
            part = part.strip()
            if part.isdigit():
                remove_indices.add(int(part))

        kept = [art for i, art in enumerate(articles) if i not in remove_indices]
        removed = len(articles) - len(kept)
        if removed > 0:
            print(f"  [意味的重複排除] {removed}件を除去 → {len(kept)}件")
        return kept
    except Exception as e:
        print(f"  [DEDUP ERROR] {e}")
        return articles

# ─── Step 5: AI関連フィルタリング（LLM） ────────────────────────────────────

def filter_ai_related_llm(articles):
    """
    AIに関連しない記事をLLMで検出・除去する。
    バッチ処理でAPI呼び出し回数を削減。
    """
    if not articles:
        return articles

    result = []
    for i in range(0, len(articles), FILTER_BATCH_SIZE):
        batch = articles[i:i + FILTER_BATCH_SIZE]
        items_text = "\n".join(
            f"[{j}] {art['title']}\nサマリー: {art['summary'][:120]}"
            for j, art in enumerate(batch)
        )

        prompt = (
            "以下の記事について、AIまたは機械学習・データサイエンス・LLM・自動化・ロボティクスに"
            "直接関連するものを「関連あり」、そうでないものを「関連なし」と判定してください。\n\n"
            "判定基準:\n"
            "- 関連あり: AI技術・製品・研究・規制・企業動向・AI活用事例など\n"
            "- 関連なし: スポーツ、エンタメ、ガジェットレビュー、セール情報、一般ニュースなど（AIと無関係なもの）\n\n"
            f"{items_text}\n\n"
            "「関連なし」の記事の番号をカンマ区切りで返してください。すべて関連ありなら「なし」と返してください。\n"
            "例: 1,3\n"
            "回答（番号のみ）:"
        )
        try:
            answer = generate_text(prompt, max_output_tokens=100, temperature=0).strip()
            if answer == "なし" or not answer:
                result.extend(batch)
                continue

            remove_indices = set()
            for part in answer.split(","):
                part = part.strip()
                if part.isdigit():
                    remove_indices.add(int(part))

            kept = [art for j, art in enumerate(batch) if j not in remove_indices]
            removed = len(batch) - len(kept)
            if removed > 0:
                removed_titles = [batch[j]["title"][:50] for j in remove_indices if j < len(batch)]
                print(f"  [AI関連フィルタ] {removed}件を除去: {removed_titles}")
            result.extend(kept)
        except Exception as e:
            print(f"  [FILTER ERROR] {e}")
            result.extend(batch)

    return result

# ─── メイン処理 ──────────────────────────────────────────────────────────────

def main():
    cutoff = get_cutoff()
    today_jst = (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y年%m月%d日")
    print(f"=== Daily AI News 取得開始 ===")
    print(f"対象日: {today_jst}")
    print(f"取得期間: {cutoff.strftime('%Y-%m-%d %H:%M UTC')} 以降")
    print(f"フィード数: {sum(len(v) for v in FEED_CATEGORIES.values())}件")
    print()

    all_articles_flat = []  # 全カテゴリをまたいだ重複排除用

    # ── Step 1〜2: 取得・タイトル重複排除 ──
    for category, feeds in FEED_CATEGORIES.items():
        print(f"[{category}]")
        raw_articles = []

        for feed_name, url in feeds:
            feed = fetch_feed(feed_name, url)
            if not feed:
                continue
            for entry in feed.entries:
                t = parse_time(entry)
                if t and t >= cutoff:
                    raw_articles.append({
                        "source": feed_name,
                        "category": category,
                        "title": getattr(entry, 'title', '（タイトルなし）'),
                        "url": getattr(entry, 'link', ''),
                        "date": format_jst(t),
                        "date_raw": t.isoformat(),
                        "text": get_text(entry),
                    })

        # タイトルベースの重複排除（カテゴリ内）
        deduped = deduplicate_by_title(raw_articles)
        print(f"  {len(raw_articles)}件取得 → タイトル重複排除後 {len(deduped)}件")

        all_articles_flat.extend(deduped)
        print()

    print(f"全カテゴリ合計: {len(all_articles_flat)}件")
    print()

    print("=== Step 3: サマリー生成 ===")
    for art in all_articles_flat:
        print(f"  サマリー: {art['title'][:60]}...")
        art["summary"] = summarize(art["title"], art["url"], art["text"], art["source"])
        time.sleep(0.3)
    print(f"サマリー生成完了: {len(all_articles_flat)}件")
    print()

    # ── Step 4: 全記事をまたいだ意味的重複排除（LLM） ──
    print("=== Step 4: 意味的重複排除（LLM）===")
    after_dedup = deduplicate_by_summary_llm(all_articles_flat)
    removed_dedup = len(all_articles_flat) - len(after_dedup)
    print(f"意味的重複排除: {len(all_articles_flat)}件 → {len(after_dedup)}件（{removed_dedup}件除去）")
    print()

    # ── Step 5: AI関連フィルタリング（LLM） ──
    print("=== Step 5: AI関連フィルタリング（LLM）===")
    after_filter = filter_ai_related_llm(after_dedup)
    removed_filter = len(after_dedup) - len(after_filter)
    print(f"AI関連フィルタ: {len(after_dedup)}件 → {len(after_filter)}件（{removed_filter}件除去）")
    print()

    # ── カテゴリ別に再分類 ──
    categorized: dict[str, list] = {cat: [] for cat in FEED_CATEGORIES}
    for art in after_filter:
        cat = art.get("category", "AIニュース・メディア")
        if cat in categorized:
            categorized[cat].append(art)

    total = len(after_filter)
    print(f"最終合計: {total}件")
    for cat, arts in categorized.items():
        print(f"  {cat}: {len(arts)}件")

    output = {
        "date": today_jst,
        "date_slug": (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y-%m-%d"),
        "generated_at": (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M JST"),
        "total": total,
        "stats": {
            "fetched": len(all_articles_flat),
            "after_title_dedup": len(all_articles_flat),
            "after_semantic_dedup": len(after_dedup),
            "after_ai_filter": total,
        },
        "categories": categorized,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"保存完了: {OUTPUT_JSON}")
    return output

if __name__ == "__main__":
    main()
