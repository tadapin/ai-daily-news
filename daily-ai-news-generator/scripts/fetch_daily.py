#!/usr/bin/env python3
"""
Daily AI News - フィード取得・重複排除・サマリー生成スクリプト
ai-news-feedsスキルの全フィードから過去24時間の記事を収集する

フィード一覧はai-news-feedsスキル（/home/ubuntu/skills/ai-news-feeds/SKILL.md）をベースにしつつ、
ローカル追加の公式RSSも含む（全44件）。

処理フロー:
  1. 全フィードから記事取得
  2. タイトルベースの重複排除（URL一致 + 文字列類似度）
  3. OpenAI互換APIでサマリー生成
  4. OpenAI互換APIでAI関連フィルタリング
  5. JSON出力
"""

import feedparser
import requests
import re
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from openai import OpenAI
from difflib import SequenceMatcher

# ===== 設定 =====
DAYS_BACK = 1
OLSHANSK_BASE = "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DailyAINews/1.0)"}

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "daily-ai-news-generator" / "output"
OUTPUT_JSON = OUTPUT_DIR / "daily_articles.json"
ENV_PATH = REPO_ROOT / ".env"
DEFAULT_SUMMARY_CONCURRENCY = 3

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
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

if not OPENAI_API_KEY:
    raise RuntimeError(
        "OPENAI_API_KEY が設定されていません。.env を確認してください。"
    )

client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL or None,
)

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

def log_now():
    return (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%H:%M:%S")

def extract_json_object(text):
    text = text.strip()
    if not text:
        raise ValueError("empty response")
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("json object not found")
    return json.loads(text[start:end + 1])

def get_summary_concurrency():
    raw_value = os.environ.get("SUMMARY_CONCURRENCY", str(DEFAULT_SUMMARY_CONCURRENCY))
    try:
        concurrency = int(raw_value)
    except (TypeError, ValueError):
        print(
            f"[WARN] SUMMARY_CONCURRENCY={raw_value!r} は不正です。"
            f"デフォルト値 {DEFAULT_SUMMARY_CONCURRENCY} を使用します。"
        )
        return DEFAULT_SUMMARY_CONCURRENCY

    if concurrency < 1:
        print(
            f"[WARN] SUMMARY_CONCURRENCY={concurrency} は 1 以上を指定してください。"
            f"デフォルト値 {DEFAULT_SUMMARY_CONCURRENCY} を使用します。"
        )
        return DEFAULT_SUMMARY_CONCURRENCY

    return concurrency

# ─── Step 2: タイトルベースの重複排除（高速・LLM不要） ──────────────────────

def normalize_title(title):
    normalized = title.lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"[“”\"'‘’]", "", normalized)
    normalized = re.sub(r"\s*[-:|]\s.*$", "", normalized)
    normalized = re.sub(r"[^a-z0-9\u3040-\u30ff\u3400-\u9fff\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized

def is_title_duplicate(title1, title2, threshold=0.75):
    normalized1 = normalize_title(title1)
    normalized2 = normalize_title(title2)
    if not normalized1 or not normalized2:
        return False
    if normalized1 == normalized2:
        return True
    ratio = SequenceMatcher(None, normalized1, normalized2).ratio()
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

JSON_SYSTEM_PROMPT = "You are a JSON generator. No talk. No code blocks. Output exactly one JSON object."
SUMMARY_FILTER_JSON_SCHEMA = {
    "name": "summary_filter_result",
    "schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "is_ai_related": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": ["summary", "is_ai_related", "reason"],
        "additionalProperties": False,
    },
}

def generate_text(
    prompt,
    max_output_tokens=300,
    temperature=0.3,
    system_prompt=None,
    json_mode=False,
    json_schema=None,
):
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    request_kwargs = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_output_tokens,
    }
    if json_schema:
        request_kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": json_schema,
        }
    elif json_mode:
        request_kwargs["response_format"] = {"type": "json_object"}

    resp = client.chat.completions.create(**request_kwargs)
    return (resp.choices[0].message.content or "").strip()

def normalize_summary_text(text):
    summary = text.strip()
    summary = re.sub(r"^\s*(日本語サマリー|要約)\s*[:：]\s*", "", summary)
    summary = re.sub(r"^\s*サマリー\s*[:：]\s*", "", summary)
    summary = re.sub(r"^「", "", summary)
    summary = re.sub(r"」$", "", summary)
    return summary.strip()

def count_summary_sentences(summary):
    return len([s for s in re.split(r"[。.!?]+", summary) if s.strip()])

def is_summary_primarily_japanese(summary):
    if not summary:
        return False
    japanese_chars = len(re.findall(r"[\u3040-\u30ff\u3400-\u9fff]", summary))
    latin_letters = len(re.findall(r"[A-Za-z]", summary))
    return japanese_chars >= max(20, latin_letters)

def is_summary_in_range(summary, min_len=140, max_len=240, min_sentences=2, max_sentences=4):
    sentence_count = count_summary_sentences(summary)
    return min_len <= len(summary) <= max_len and min_sentences <= sentence_count <= max_sentences

def finalize_summary_text(summary, min_len=140, max_len=240, max_sentences=4):
    summary = normalize_summary_text(summary)
    sentences = [s.strip() for s in re.split(r"(?<=[。.!?])\s*", summary) if s.strip()]

    if len(sentences) > max_sentences:
        summary = "".join(sentences[:max_sentences]).strip()
        sentences = [s.strip() for s in re.split(r"(?<=[。.!?])\s*", summary) if s.strip()]

    if len(summary) <= max_len:
        return summary

    trimmed = ""
    for sentence in sentences:
        candidate = f"{trimmed}{sentence}".strip()
        if len(candidate) > max_len:
            break
        trimmed = candidate

    if trimmed and len(trimmed) >= min_len:
        return trimmed

    if trimmed and sentences:
        remaining = max_len - len(trimmed)
        if remaining > 10:
            next_sentence = summary[len(trimmed):].strip()
            addition = next_sentence[:remaining].rstrip(" 、,")
            candidate = f"{trimmed}{addition}".strip()
            if candidate and candidate[-1] not in "。.!?":
                candidate += "。"
            if len(candidate) >= min_len:
                return candidate

    if len(summary) > max_len:
        clipped = summary[:max_len].rstrip(" 、,")
        if clipped and clipped[-1] not in "。.!?":
            clipped += "。"
        return clipped

    return summary[:max_len].rstrip()

def summarize_and_filter(title, url, text, source):
    prompt = f"""Read the article below and return only a single JSON object.
Do not include code blocks, markdown, or any text outside the JSON.

JSON Schema:
{{
  "summary": "[Japanese] A natural 2-4 sentence summary (140-240 characters). Focus on what happened, what is new, and its significance. No headers or quotes.",
  "is_ai_related": boolean,
  "reason": "[Japanese] A brief, one-sentence explanation for why the article is or is not AI-related."
}}

AI Relevance Criteria:
- True: The main topic is AI/ML/LLM, robotics, AI research, AI products, AI companies, or concrete AI use cases.
- False: The main topic is general tech, gadgets, sales, entertainment, politics, sports, or other non-AI news, even if AI is mentioned incidentally.

Article Data:
Source: {source}
Title: {title}
URL: {url}
Content: {text}
"""
    retry_prompt = f"""Fix the response and return only a single JSON object.
Do not include code blocks, markdown, or any text outside the JSON.

Requirements:
- summary must be natural Japanese
- summary must be 140-240 characters and 2-4 sentences
- summary must explain what happened, what is new, and why it matters
- is_ai_related must be a JSON boolean
- reason must be one short Japanese sentence explaining why the article is or is not AI-related

Title: {title}
Content: {text}
"""
    expand_prompt = f"""Rewrite the JSON and return only a single JSON object.
Do not include code blocks, markdown, or any text outside the JSON.

Keep the facts, but make summary longer.
- summary must be natural Japanese
- summary must be 140-240 characters and 2-4 sentences
- summary must explain what happened, what is new, and why it matters

Title: {title}
Content: {text}
Previous JSON:
{{payload}}
"""
    japanese_retry_prompt = f"""Rewrite the JSON and return only a single JSON object.
Do not include code blocks, markdown, or any text outside the JSON.

The summary is not Japanese enough.
- summary must be natural Japanese only
- do not leave English sentences in summary
- summary must be 140-240 characters and 2-4 sentences
- reason must be one short Japanese sentence

Title: {title}
Content: {text}
Previous JSON:
{{payload}}
"""
    translation_retry_prompt = """Rewrite the JSON and return only a single JSON object.
Do not include code blocks, markdown, or any text outside the JSON.

Translate the summary into natural Japanese.
- keep the facts unchanged
- do not leave English sentences in summary
- summary must be 140-240 characters and 2-4 sentences
- reason must be one short Japanese sentence

Previous JSON:
{payload}
"""
    try:
        payload = None
        for attempt, temperature in enumerate((0.3, 0.2, 0.1), start=1):
            current_prompt = prompt if attempt == 1 else retry_prompt
            raw = generate_text(
                current_prompt,
                max_output_tokens=500,
                temperature=temperature,
                system_prompt=JSON_SYSTEM_PROMPT,
                json_schema=SUMMARY_FILTER_JSON_SCHEMA,
            )
            payload = extract_json_object(raw)
            summary = finalize_summary_text(str(payload.get("summary", "")))
            is_ai_related = bool(payload.get("is_ai_related"))
            payload["summary"] = summary
            payload["is_ai_related"] = is_ai_related
            payload["reason"] = str(payload.get("reason", "")).strip()
            if is_ai_related and is_summary_in_range(summary) and is_summary_primarily_japanese(summary):
                break
        if payload is None:
            raise ValueError("classification payload missing")

        if payload.get("is_ai_related") and len(payload["summary"]) < 140:
            raw = generate_text(
                expand_prompt.format(payload=json.dumps(payload, ensure_ascii=False)),
                max_output_tokens=500,
                temperature=0.2,
                system_prompt=JSON_SYSTEM_PROMPT,
                json_schema=SUMMARY_FILTER_JSON_SCHEMA,
            )
            expanded = extract_json_object(raw)
            payload["summary"] = finalize_summary_text(str(expanded.get("summary", payload["summary"])))
            payload["reason"] = str(expanded.get("reason", payload.get("reason", ""))).strip()
            payload["is_ai_related"] = bool(expanded.get("is_ai_related", payload["is_ai_related"]))

        if payload.get("is_ai_related") and not is_summary_primarily_japanese(payload["summary"]):
            raw = generate_text(
                japanese_retry_prompt.format(payload=json.dumps(payload, ensure_ascii=False)),
                max_output_tokens=500,
                temperature=0.1,
                system_prompt=JSON_SYSTEM_PROMPT,
                json_schema=SUMMARY_FILTER_JSON_SCHEMA,
            )
            rewritten = extract_json_object(raw)
            payload["summary"] = finalize_summary_text(str(rewritten.get("summary", payload["summary"])))
            payload["reason"] = str(rewritten.get("reason", payload.get("reason", ""))).strip()
            payload["is_ai_related"] = bool(rewritten.get("is_ai_related", payload["is_ai_related"]))

        if payload.get("is_ai_related") and not is_summary_primarily_japanese(payload["summary"]):
            raw = generate_text(
                translation_retry_prompt.format(payload=json.dumps(payload, ensure_ascii=False)),
                max_output_tokens=500,
                temperature=0,
                system_prompt=JSON_SYSTEM_PROMPT,
                json_schema=SUMMARY_FILTER_JSON_SCHEMA,
            )
            translated = extract_json_object(raw)
            payload["summary"] = finalize_summary_text(str(translated.get("summary", payload["summary"])))
            payload["reason"] = str(translated.get("reason", payload.get("reason", ""))).strip()
            payload["is_ai_related"] = bool(translated.get("is_ai_related", payload["is_ai_related"]))

        return {
            "summary": finalize_summary_text(str(payload.get("summary", ""))).strip(),
            "is_ai_related": bool(payload.get("is_ai_related")),
            "reason": str(payload.get("reason", "")).strip(),
        }
    except Exception as e:
        print(f"  [{log_now()}] [SUMMARY/FILTER ERROR] {title[:40]}: {e}")
        return {
            "summary": "（サマリー生成に失敗しました）",
            "is_ai_related": True,
            "reason": "AI関連判定に失敗したため記事を維持",
        }

def process_article(index, article):
    title = article["title"]
    print(f"  [{log_now()}] [START {index}] {title[:60]}...")
    analysis = summarize_and_filter(
        article["title"],
        article["url"],
        article["text"],
        article["source"],
    )
    return index, analysis

# ─── メイン処理 ──────────────────────────────────────────────────────────────

def main():
    cutoff = get_cutoff()
    today_jst = (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y年%m月%d日")
    summary_concurrency = get_summary_concurrency()
    print(f"=== Daily AI News 取得開始 ===")
    print(f"対象日: {today_jst}")
    print(f"取得期間: {cutoff.strftime('%Y-%m-%d %H:%M UTC')} 以降")
    print(f"フィード数: {sum(len(v) for v in FEED_CATEGORIES.values())}件")
    print(f"要約並列度: {summary_concurrency}")
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

    print("=== Step 3: サマリー生成・AI関連判定 ===")
    after_filter = []
    total_to_process = len(all_articles_flat)
    completed = 0
    with ThreadPoolExecutor(max_workers=summary_concurrency) as executor:
        future_to_index = {
            executor.submit(process_article, index, art): index
            for index, art in enumerate(all_articles_flat, start=1)
        }

        for future in as_completed(future_to_index):
            index, analysis = future.result()
            art = all_articles_flat[index - 1]
            art["summary"] = analysis["summary"]
            art["reason"] = analysis["reason"]

            completed += 1
            print(f"  [{log_now()}] [DONE {completed}/{total_to_process}] {art['title'][:60]}...")

            if analysis["is_ai_related"]:
                after_filter.append(art)
            else:
                print(f"  [{log_now()}] [AI関連フィルタ] 除外: {art['title'][:50]} / {analysis['reason']}")

    after_filter.sort(key=lambda art: art["date_raw"], reverse=True)
    print(f"サマリー生成・判定完了: {len(all_articles_flat)}件")
    print()

    after_dedup = all_articles_flat
    print("=== Step 4: AI関連フィルタ結果 ===")
    removed_filter = len(all_articles_flat) - len(after_filter)
    print(f"AI関連フィルタ: {len(all_articles_flat)}件 → {len(after_filter)}件（{removed_filter}件除去）")
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
            "after_dedup": len(after_dedup),
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
