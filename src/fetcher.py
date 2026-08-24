"""
RSS / Atom feed fetcher.
Reads feeds.yaml, fetches each feed with feedparser, deduplicates by URL,
and returns a list of Article objects published within the lookback window.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import List
from pathlib import Path

import feedparser
import requests
import yaml

from models import Article

logger = logging.getLogger(__name__)


def _parse_date(entry) -> datetime | None:
    """Try to extract a timezone-aware datetime from a feedparser entry."""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(entry, attr, None)
        if t:
            import time
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def fetch_articles(config: dict) -> List[Article]:
    """
    Fetch all articles from feeds defined in feeds.yaml.

    Returns articles published within the last `lookback_hours` hours,
    deduplicated by URL.
    """
    feeds_path = Path(config["paths"]["feeds"])
    lookback_hours = config["html"].get("lookback_hours", 24)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    with open(feeds_path) as f:
        feeds_config = yaml.safe_load(f)

    all_articles: List[Article] = []
    seen_urls: set[str] = set()

    for feed_def in feeds_config.get("feeds", []):
        name = feed_def["name"]
        url = feed_def["url"]
        logger.info(f"Fetching: {name} ({url})")

        try:
            # feedparser can handle most RSS/Atom directly
            parsed = feedparser.parse(
                url,
                request_headers={"User-Agent": "llm-cs-news/1.0 (security digest bot)"},
            )
        except Exception as e:
            logger.warning(f"Failed to fetch {name}: {e}")
            continue

        if parsed.bozo and not parsed.entries:
            logger.warning(f"Feed error for {name}: {parsed.bozo_exception}")
            continue

        for entry in parsed.entries:
            article_url = entry.get("link", "")
            if not article_url or article_url in seen_urls:
                continue

            published = _parse_date(entry)
            # If we can't determine publish time, include it (conservative)
            if published and published < cutoff:
                continue

            # Build summary text
            summary = ""
            if hasattr(entry, "summary"):
                summary = entry.summary
            elif hasattr(entry, "content") and entry.content:
                summary = entry.content[0].get("value", "")

            # Strip basic HTML tags from summary
            import re
            summary = re.sub(r"<[^>]+>", " ", summary).strip()
            summary = re.sub(r"\s+", " ", summary)[:1500]

            article = Article(
                title=entry.get("title", "Untitled").strip(),
                url=article_url,
                summary=summary,
                source=name,
                published=published,
            )

            all_articles.append(article)
            seen_urls.add(article_url)

        logger.info(f"  → {len([a for a in all_articles if a.source == name])} new articles")

    logger.info(f"Total fetched: {len(all_articles)} articles from {len(feeds_config['feeds'])} feeds")
    return all_articles
