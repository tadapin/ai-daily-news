#!/usr/bin/env python3
"""
Daily AI News HTML生成スクリプト
daily_articles.jsonからモダンなHTMLニュースページを生成する
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta
import html as html_module

REPO_ROOT = Path(__file__).resolve().parents[2]
INPUT_JSON = REPO_ROOT / "daily-ai-news-generator" / "output" / "daily_articles.json"
DOCS_DIR = REPO_ROOT / "docs"
ARCHIVE_INDEX = DOCS_DIR / "archive-index.json"

def load_data():
    with INPUT_JSON.open("r", encoding="utf-8") as f:
        return json.load(f)

def load_archive_dates():
    if not ARCHIVE_INDEX.exists():
        return []
    with ARCHIVE_INDEX.open("r", encoding="utf-8") as f:
        dates = json.load(f)
    return sorted(dates, reverse=True)

CATEGORY_ICONS = {
    "Anthropic": "🤖",
    "OpenAI / Google / Microsoft": "🏢",
    "AI開発ツール": "🛠️",
    "AI企業・プラットフォーム": "🚀",
    "AIニュース・メディア": "📰",
    "研究者・ニュースレター": "🔬",
}

CATEGORY_COLORS = {
    "Anthropic": "#c85250",
    "OpenAI / Google / Microsoft": "#4285f4",
    "AI開発ツール": "#34a853",
    "AI企業・プラットフォーム": "#ff6d00",
    "AIニュース・メディア": "#7c4dff",
    "研究者・ニュースレター": "#00897b",
}

def e(text):
    """HTMLエスケープ"""
    return html_module.escape(str(text))

def article_id(article):
    raw = "||".join([
        str(article.get("category", "")),
        str(article.get("source", "")),
        str(article.get("title", "")),
        str(article.get("url", "")),
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

def generate_html(data):
    date_str = data["date"]
    date_slug = data.get("date_slug")
    if not date_slug:
        date_slug = data["date"].replace("年", "-").replace("月", "-").replace("日", "").replace("--", "-")
    generated_at = data["generated_at"]
    total = data["total"]
    categories = data["categories"]
    archive_dates = load_archive_dates()

    if date_slug not in archive_dates:
        archive_dates = sorted({date_slug, *archive_dates}, reverse=True)

    current_index = archive_dates.index(date_slug)
    newer_date = archive_dates[current_index - 1] if current_index > 0 else None
    older_date = archive_dates[current_index + 1] if current_index + 1 < len(archive_dates) else None

    # カテゴリ別件数サマリー
    cat_summary = [(cat, len(arts)) for cat, arts in categories.items() if arts]

    # サイドバーナビ
    nav_items = ""
    for cat, count in cat_summary:
        icon = CATEGORY_ICONS.get(cat, "📌")
        color = CATEGORY_COLORS.get(cat, "#666")
        anchor = cat.replace(" ", "-").replace("/", "").replace("・", "")
        nav_items += f'''
        <a href="#{anchor}" class="nav-item" style="border-left-color:{color}">
          <span class="nav-icon">{icon}</span>
          <span class="nav-label">{e(cat)}</span>
          <span class="nav-count" style="background:{color}">{count}</span>
        </a>'''

    # カテゴリ別記事セクション
    sections = ""
    for cat, articles in categories.items():
        if not articles:
            continue
        icon = CATEGORY_ICONS.get(cat, "📌")
        color = CATEGORY_COLORS.get(cat, "#666")
        anchor = cat.replace(" ", "-").replace("/", "").replace("・", "")

        cards = ""
        for art in articles:
            article_key = article_id(art)
            title = e(art.get("title", ""))
            url = e(art.get("url", "#"))
            source = e(art.get("source", ""))
            date = e(art.get("date", ""))
            summary = e(art.get("summary", ""))

            cards += f'''
            <article class="news-card" data-article-id="{article_key}">
              <div class="card-meta">
                <span class="card-source" style="color:{color}">{source}</span>
                <span class="card-date">{date}</span>
              </div>
              <div class="card-actions">
                <button
                  type="button"
                  class="interest-toggle"
                  data-article-id="{article_key}"
                  aria-pressed="false"
                >
                  <span class="interest-icon" aria-hidden="true">☐</span>
                  <span class="interest-label">気になる</span>
                </button>
              </div>
              <h3 class="card-title">
                <a href="{url}" target="_blank" rel="noopener">{title}</a>
              </h3>
              <p class="card-summary">{summary}</p>
              <a href="{url}" target="_blank" rel="noopener" class="card-link" style="color:{color}">
                記事を読む →
              </a>
            </article>'''

        sections += f'''
      <section class="category-section" id="{anchor}">
        <div class="category-header" style="border-left-color:{color}">
          <span class="category-icon">{icon}</span>
          <h2 class="category-title">{e(cat)}</h2>
          <span class="category-badge" style="background:{color}">{len(articles)}件</span>
        </div>
        <div class="cards-grid">
          {cards}
        </div>
      </section>'''

    html = f'''<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Daily AI News — {e(date_str)}</title>
  <style>
    :root {{
      --bg: #0f1117;
      --surface: #1a1d27;
      --surface2: #22263a;
      --border: #2e3250;
      --text: #e8eaf0;
      --text-muted: #8b90a8;
      --accent: #6c63ff;
      --radius: 12px;
      --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Hiragino Sans', sans-serif;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: var(--font);
      line-height: 1.7;
      min-height: 100vh;
    }}

    /* ===== ヘッダー ===== */
    .site-header {{
      background: linear-gradient(135deg, #1a1d27 0%, #0f1117 100%);
      border-bottom: 1px solid var(--border);
      padding: 28px 40px;
      position: sticky;
      top: 0;
      z-index: 100;
      backdrop-filter: blur(12px);
    }}
    .header-inner {{
      max-width: 1400px;
      margin: 0 auto;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
    }}
    .site-title {{
      font-size: 1.5rem;
      font-weight: 800;
      letter-spacing: -0.5px;
      background: linear-gradient(135deg, #6c63ff, #a78bfa);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }}
    .header-meta {{
      display: flex;
      align-items: center;
      gap: 20px;
    }}
    .header-tools {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .header-date {{
      font-size: 0.95rem;
      color: var(--text-muted);
    }}
    .header-total {{
      background: var(--accent);
      color: white;
      padding: 4px 14px;
      border-radius: 20px;
      font-size: 0.85rem;
      font-weight: 600;
    }}
    .header-filter {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border: 1px solid var(--border);
      border-radius: 999px;
      background: rgba(255,255,255,0.03);
      padding: 6px 12px;
      color: var(--text-muted);
      font-size: 0.82rem;
    }}
    .header-filter input {{
      accent-color: var(--accent);
    }}
    .day-navigation {{
      max-width: 1400px;
      margin: 0 auto;
      padding: 18px 36px 0;
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
    }}
    .nav-pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: var(--surface);
      color: var(--text);
      text-decoration: none;
      padding: 9px 14px;
      font-size: 0.84rem;
      transition: border-color 0.2s, transform 0.15s, color 0.2s;
    }}
    .nav-pill:hover {{
      border-color: var(--accent);
      color: #fff;
      transform: translateY(-1px);
    }}
    .nav-pill.is-muted {{
      color: var(--text-muted);
      background: rgba(255,255,255,0.02);
    }}
    .nav-pill.is-disabled {{
      color: var(--text-muted);
      opacity: 0.5;
      pointer-events: none;
    }}
    .nav-spacer {{
      flex: 1 1 auto;
    }}

    /* ===== レイアウト ===== */
    .layout {{
      max-width: 1400px;
      margin: 0 auto;
      display: grid;
      grid-template-columns: 260px 1fr;
      gap: 0;
      padding: 0;
    }}

    /* ===== サイドバー ===== */
    .sidebar {{
      position: sticky;
      top: 81px;
      height: calc(100vh - 81px);
      overflow-y: auto;
      padding: 28px 20px;
      border-right: 1px solid var(--border);
      background: var(--surface);
    }}
    .sidebar-title {{
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: var(--text-muted);
      margin-bottom: 14px;
      padding: 0 8px;
    }}
    .nav-item {{
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 12px;
      border-radius: 8px;
      border-left: 3px solid transparent;
      text-decoration: none;
      color: var(--text);
      font-size: 0.88rem;
      margin-bottom: 4px;
      transition: background 0.15s;
    }}
    .nav-item:hover {{ background: var(--surface2); }}
    .nav-icon {{ font-size: 1rem; flex-shrink: 0; }}
    .nav-label {{ flex: 1; }}
    .nav-count {{
      font-size: 0.72rem;
      font-weight: 700;
      color: white;
      padding: 2px 8px;
      border-radius: 10px;
      flex-shrink: 0;
    }}
    .sidebar-stats {{
      margin-top: 28px;
      padding: 16px;
      background: var(--surface2);
      border-radius: var(--radius);
      border: 1px solid var(--border);
    }}
    .stats-title {{
      font-size: 0.75rem;
      color: var(--text-muted);
      margin-bottom: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .stats-item {{
      display: flex;
      justify-content: space-between;
      font-size: 0.82rem;
      color: var(--text-muted);
      padding: 3px 0;
    }}
    .stats-item strong {{ color: var(--text); }}

    /* ===== メインコンテンツ ===== */
    .main-content {{
      padding: 32px 36px;
      min-height: calc(100vh - 81px);
    }}

    /* ===== カテゴリセクション ===== */
    .category-section {{
      margin-bottom: 52px;
      scroll-margin-top: 100px;
    }}
    .category-header {{
      display: flex;
      align-items: center;
      gap: 12px;
      padding-left: 16px;
      border-left: 4px solid;
      margin-bottom: 22px;
    }}
    .category-icon {{ font-size: 1.4rem; }}
    .category-title {{
      font-size: 1.25rem;
      font-weight: 700;
      letter-spacing: -0.3px;
    }}
    .category-badge {{
      font-size: 0.78rem;
      font-weight: 700;
      color: white;
      padding: 3px 12px;
      border-radius: 12px;
    }}

    /* ===== カードグリッド ===== */
    .cards-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
      gap: 18px;
    }}
    .news-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 20px 22px;
      transition: border-color 0.2s, transform 0.15s, box-shadow 0.2s;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}
    .news-card:hover {{
      border-color: var(--accent);
      transform: translateY(-2px);
      box-shadow: 0 8px 24px rgba(108,99,255,0.12);
    }}
    .card-meta {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }}
    .card-actions {{
      display: flex;
      justify-content: flex-end;
      margin-top: -2px;
    }}
    .interest-toggle {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border: 1px solid var(--border);
      background: var(--surface2);
      color: var(--text-muted);
      border-radius: 999px;
      padding: 7px 12px;
      font-size: 0.8rem;
      cursor: pointer;
      transition: border-color 0.2s, background 0.2s, color 0.2s;
    }}
    .interest-toggle:hover {{
      border-color: var(--accent);
      color: var(--text);
    }}
    .interest-toggle.is-selected {{
      border-color: var(--accent);
      background: rgba(108,99,255,0.12);
      color: var(--text);
    }}
    .interest-icon {{
      font-size: 0.95rem;
      line-height: 1;
    }}
    .news-card.is-selected {{
      border-color: var(--accent);
      box-shadow: 0 10px 26px rgba(108,99,255,0.14);
    }}
    .news-card.is-hidden-by-filter {{
      display: none;
    }}
    .card-source {{
      font-size: 0.78rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .card-date {{
      font-size: 0.75rem;
      color: var(--text-muted);
      white-space: nowrap;
    }}
    .card-title {{
      font-size: 0.97rem;
      font-weight: 600;
      line-height: 1.45;
    }}
    .card-title a {{
      color: var(--text);
      text-decoration: none;
    }}
    .card-title a:hover {{ color: var(--accent); }}
    .card-summary {{
      font-size: 0.86rem;
      color: var(--text-muted);
      line-height: 1.65;
      flex: 1;
    }}
    .card-link {{
      font-size: 0.82rem;
      font-weight: 600;
      text-decoration: none;
      margin-top: 4px;
      display: inline-block;
    }}
    .card-link:hover {{ text-decoration: underline; }}

    /* ===== フッター ===== */
    .site-footer {{
      border-top: 1px solid var(--border);
      padding: 24px 40px;
      text-align: center;
      color: var(--text-muted);
      font-size: 0.82rem;
      background: var(--surface);
    }}

    /* ===== レスポンシブ ===== */
    @media (max-width: 900px) {{
      .layout {{ grid-template-columns: 1fr; }}
      .sidebar {{ position: static; height: auto; border-right: none; border-bottom: 1px solid var(--border); }}
      .main-content {{ padding: 24px 20px; }}
      .cards-grid {{ grid-template-columns: 1fr; }}
      .site-header {{ padding: 18px 20px; }}
      .day-navigation {{ padding: 14px 20px 0; }}
      .header-inner {{ align-items: flex-start; flex-direction: column; }}
      .header-meta {{ width: 100%; justify-content: space-between; flex-wrap: wrap; }}
      .nav-spacer {{ display: none; }}
    }}

    /* ===== スクロールバー ===== */
    ::-webkit-scrollbar {{ width: 6px; }}
    ::-webkit-scrollbar-track {{ background: var(--bg); }}
    ::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 3px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: var(--text-muted); }}
  </style>
</head>
<body>

  <header class="site-header">
    <div class="header-inner">
      <div class="site-title">⚡ Daily AI News</div>
      <div class="header-meta">
        <div class="header-tools">
          <span class="header-date">📅 {e(date_str)}</span>
          <label class="header-filter">
            <input type="checkbox" id="interestFilter">
            <span>気になる記事だけ表示</span>
          </label>
        </div>
        <span class="header-total">本日 {total} 件</span>
      </div>
    </div>
  </header>

  <nav class="day-navigation" aria-label="日付ナビゲーション">
    <a class="nav-pill is-muted" href="index.html">← アーカイブ一覧へ</a>
    {f'<a class="nav-pill" href="{older_date}.html">← 前の日</a>' if older_date else '<span class="nav-pill is-disabled">← 前の日</span>'}
    <span class="nav-spacer"></span>
    {f'<a class="nav-pill" href="{newer_date}.html">次の日 →</a>' if newer_date else '<span class="nav-pill is-disabled">次の日 →</span>'}
  </nav>

  <div class="layout">
    <aside class="sidebar">
      <div class="sidebar-title">カテゴリ</div>
      {nav_items}

      <div class="sidebar-stats">
        <div class="stats-title">統計</div>
        {''.join(f'<div class="stats-item"><span>{e(cat)}</span><strong>{count}件</strong></div>' for cat, count in cat_summary)}
        <div class="stats-item" style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border)">
          <span>合計</span><strong>{total}件</strong>
        </div>
      </div>
    </aside>

    <main class="main-content">
      {sections}
    </main>
  </div>

  <footer class="site-footer">
    生成日時: {e(generated_at)} &nbsp;|&nbsp;
    情報源: <a href="https://github.com/Olshansk/rss-feeds" target="_blank" style="color:var(--accent)">Olshansk/rss-feeds</a> および各公式RSSフィード &nbsp;|&nbsp;
    サマリーはAIにより自動生成されています
  </footer>

  <script>
    (() => {{
      const currentDateSlug = '{date_slug}';
      const navRoot = document.querySelector('.day-navigation');
      const storageKey = 'daily-ai-news:interests';
      const filterKey = 'daily-ai-news:interest-filter';
      const cards = Array.from(document.querySelectorAll('.news-card'));
      const buttons = Array.from(document.querySelectorAll('.interest-toggle'));
      const filterCheckbox = document.getElementById('interestFilter');

      const loadSelected = () => {{
        try {{
          const parsed = JSON.parse(localStorage.getItem(storageKey) || '[]');
          return new Set(Array.isArray(parsed) ? parsed : []);
        }} catch (_error) {{
          return new Set();
        }}
      }};

      const saveSelected = (selected) => {{
        localStorage.setItem(storageKey, JSON.stringify(Array.from(selected)));
      }};

      const applyCardState = (selected) => {{
        cards.forEach((card) => {{
          const id = card.dataset.articleId;
          const isSelected = selected.has(id);
          card.classList.toggle('is-selected', isSelected);
        }});

        buttons.forEach((button) => {{
          const id = button.dataset.articleId;
          const isSelected = selected.has(id);
          button.classList.toggle('is-selected', isSelected);
          button.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
          const icon = button.querySelector('.interest-icon');
          const label = button.querySelector('.interest-label');
          if (icon) icon.textContent = isSelected ? '☑' : '☐';
          if (label) label.textContent = isSelected ? '保存済み' : '保存';
        }});
      }};

      const applyFilterState = (selected) => {{
        const onlyInterested = Boolean(filterCheckbox?.checked);
        cards.forEach((card) => {{
          const id = card.dataset.articleId;
          const shouldHide = onlyInterested && !selected.has(id);
          card.classList.toggle('is-hidden-by-filter', shouldHide);
        }});
      }};

      const selected = loadSelected();
      applyCardState(selected);

      if (filterCheckbox) {{
        filterCheckbox.checked = localStorage.getItem(filterKey) === 'true';
        applyFilterState(selected);
        filterCheckbox.addEventListener('change', () => {{
          localStorage.setItem(filterKey, String(filterCheckbox.checked));
          applyFilterState(selected);
        }});
      }}

      buttons.forEach((button) => {{
        button.addEventListener('click', () => {{
          const id = button.dataset.articleId;
          if (!id) return;
          if (selected.has(id)) {{
            selected.delete(id);
          }} else {{
            selected.add(id);
          }}
          saveSelected(selected);
          applyCardState(selected);
          applyFilterState(selected);
        }});
      }});

      if (navRoot) {{
        fetch('archive-index.json')
          .then((response) => response.json())
          .then((dates) => {{
            const sortedDates = [...dates].sort((a, b) => b.localeCompare(a));
            const index = sortedDates.indexOf(currentDateSlug);
            if (index === -1) return;

            const olderDate = sortedDates[index + 1];
            const newerDate = index > 0 ? sortedDates[index - 1] : null;
            const navItems = navRoot.querySelectorAll('.nav-pill');
            const olderLink = navItems[1];
            const newerLink = navItems[2];

            if (olderDate && olderLink) {{
              olderLink.classList.remove('is-disabled');
              olderLink.setAttribute('href', `${{olderDate}}.html`);
            }}
            if (!olderDate && olderLink) {{
              olderLink.removeAttribute('href');
              olderLink.classList.add('is-disabled');
            }}

            if (newerDate && newerLink) {{
              newerLink.classList.remove('is-disabled');
              newerLink.setAttribute('href', `${{newerDate}}.html`);
            }}
            if (!newerDate && newerLink) {{
              newerLink.removeAttribute('href');
              newerLink.classList.add('is-disabled');
            }}
          }})
          .catch(() => {{
            // archive-index.json が読めない環境でも、初期レンダリング済みのナビをそのまま使う
          }});
      }}
    }})();
  </script>

</body>
</html>'''
    return html

def main():
    data = load_data()
    html = generate_html(data)
    date_slug = data.get("date_slug")
    if not date_slug:
        date_slug = data["date"].replace("年", "-").replace("月", "-").replace("日", "").replace("--", "-")
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = DOCS_DIR / f"{date_slug}.html"
    with output_path.open("w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML生成完了: {output_path}")
    return str(output_path)

if __name__ == "__main__":
    main()
