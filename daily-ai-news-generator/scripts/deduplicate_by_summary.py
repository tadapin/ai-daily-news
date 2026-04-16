#!/usr/bin/env python3
"""
Daily AI News summary-level deduplication script.

Uses sentence embeddings to annotate near-duplicate articles after summary generation.
When multiple similar articles are found, the article with the longest summary is marked
as the representative and the rest are marked as duplicate candidates.
"""

from __future__ import annotations

import json
import os
import hashlib
from collections import defaultdict
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

REPO_ROOT = Path(__file__).resolve().parents[2]
INPUT_JSON = REPO_ROOT / "daily-ai-news-generator" / "output" / "daily_articles.json"
DEFAULT_MODEL_NAME = "hotchpotch/static-embedding-japanese"
DEFAULT_SIMILARITY_THRESHOLD = 0.92


class UnionFind:
    def __init__(self, size: int):
        self.parent = list(range(size))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        root_a = self.find(a)
        root_b = self.find(b)
        if root_a != root_b:
            self.parent[root_b] = root_a


def get_model_name() -> str:
    return os.environ.get("SUMMARY_DEDUP_MODEL", DEFAULT_MODEL_NAME)


def get_similarity_threshold() -> float:
    raw_value = os.environ.get(
        "SUMMARY_DEDUP_THRESHOLD",
        str(DEFAULT_SIMILARITY_THRESHOLD),
    )
    try:
        threshold = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"Invalid SUMMARY_DEDUP_THRESHOLD: {raw_value!r}") from exc

    if not 0.0 <= threshold <= 1.0:
        raise ValueError("SUMMARY_DEDUP_THRESHOLD must be between 0 and 1")

    return threshold


def load_data() -> dict:
    with INPUT_JSON.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data: dict) -> None:
    with INPUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def article_id(article: dict) -> str:
    raw = "||".join(
        [
            str(article.get("category", article.get("_category", ""))),
            str(article.get("source", "")),
            str(article.get("title", "")),
            str(article.get("url", "")),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def flatten_articles(data: dict) -> list[dict]:
    flat_articles: list[dict] = []
    for category, articles in data.get("categories", {}).items():
        for article in articles:
            article["_category"] = category
            flat_articles.append(article)
    return flat_articles


def summary_sort_key(article: dict) -> tuple:
    return (
        len(article.get("summary", "")),
        len(article.get("text", "")),
        article.get("date_raw", ""),
        article.get("title", ""),
    )


def collect_clusters(similarities: np.ndarray, threshold: float) -> dict[int, list[int]]:
    size = similarities.shape[0]
    union_find = UnionFind(size)

    for i in range(size):
        for j in range(i + 1, size):
            if similarities[i, j] >= threshold:
                union_find.union(i, j)

    clusters: dict[int, list[int]] = defaultdict(list)
    for index in range(size):
        clusters[union_find.find(index)].append(index)
    return clusters


def reset_duplicate_metadata(articles: list[dict]) -> None:
    for article in articles:
        article["article_id"] = article_id(article)
        article["is_duplicate_candidate"] = False
        article["duplicate_of"] = None
        article["duplicate_score"] = None
        article["duplicate_count"] = 0
        article["duplicate_group_id"] = article["article_id"]


def clear_internal_fields(data: dict) -> None:
    for articles in data.get("categories", {}).values():
        for article in articles:
            article.pop("_category", None)


def main() -> dict:
    data = load_data()
    model_name = get_model_name()
    threshold = get_similarity_threshold()
    flat_articles = flatten_articles(data)
    reset_duplicate_metadata(flat_articles)

    print("=== Step: サマリー類似度による重複排除 ===")
    print(f"入力記事数: {len(flat_articles)}件")
    print(f"埋め込みモデル: {model_name}")
    print(f"類似度閾値: {threshold:.2f}")

    if len(flat_articles) <= 1:
        print("記事数が1件以下のためスキップします。")
        data["total"] = len(flat_articles)
        data.setdefault("stats", {})["after_summary_dedup"] = len(flat_articles)
        data["stats"]["duplicate_candidates"] = 0
        data["stats"]["visible_after_summary_dedup"] = len(flat_articles)
        clear_internal_fields(data)
        save_data(data)
        return data

    model = SentenceTransformer(model_name, trust_remote_code=True)
    summaries = [article.get("summary", "").strip() or article.get("title", "") for article in flat_articles]
    embeddings = model.encode(
        summaries,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=True,
    )

    similarities = embeddings @ embeddings.T
    clusters = collect_clusters(similarities, threshold)

    duplicate_count = 0

    for cluster_indices in clusters.values():
        if len(cluster_indices) == 1:
            continue

        cluster_articles = [flat_articles[index] for index in cluster_indices]
        representative = max(cluster_articles, key=summary_sort_key)
        representative_id = representative["article_id"]
        representative["duplicate_group_id"] = representative_id
        kept_duplicates = 0

        print(
            f"  [CLUSTER] {len(cluster_articles)}件 -> 1件採用: "
            f"{representative.get('title', '')[:80]}"
        )

        rep_index = flat_articles.index(representative)
        for article in cluster_articles:
            if article is representative:
                continue
            score_to_rep = round(float(similarities[rep_index, flat_articles.index(article)]), 4)
            if score_to_rep < threshold:
                continue
            duplicate_count += 1
            kept_duplicates += 1
            article["is_duplicate_candidate"] = True
            article["duplicate_of"] = representative_id
            article["duplicate_group_id"] = representative_id
            article["duplicate_score"] = score_to_rep

        representative["duplicate_count"] = kept_duplicates

    total_articles = len(flat_articles)
    visible_articles = total_articles - duplicate_count
    data["total"] = total_articles
    data.setdefault("stats", {})["after_summary_dedup"] = total_articles
    data["stats"]["duplicate_candidates"] = duplicate_count
    data["stats"]["visible_after_summary_dedup"] = visible_articles
    clear_internal_fields(data)

    save_data(data)

    print(
        f"サマリー類似度による重複注釈完了: "
        f"{total_articles}件中 {duplicate_count}件を重複候補としてマーク"
    )
    print(f"保存完了: {INPUT_JSON}")
    return data


if __name__ == "__main__":
    main()
