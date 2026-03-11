from __future__ import annotations

import logging
from typing import Any

import httpx

from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

HN_ALGOLIA_BASE = "https://hn.algolia.com/api/v1/search"
HEADERS = {
    "User-Agent": "FikirBulucu/1.0 (AI Opportunity Radar; personal research tool)",
    "Accept": "application/json",
}
TIMEOUT = 30.0


class HackerNewsScraper(BaseScraper):
    name = "hackernews"

    def __init__(self) -> None:
        super().__init__(rate_limit_seconds=2.0)

    def _fetch_stories(self, tag: str, hits_per_page: int = 30) -> list[dict]:
        self._enforce_rate_limit()
        try:
            with httpx.Client(timeout=TIMEOUT, headers=HEADERS) as client:
                response = client.get(
                    HN_ALGOLIA_BASE,
                    params={"tags": tag, "hitsPerPage": hits_per_page},
                )
                response.raise_for_status()
                data = response.json()
                return data.get("hits", [])
        except httpx.HTTPError as exc:
            logger.warning("HackerNews HTTP error for tag=%s: %s", tag, exc)
            return []
        except Exception as exc:
            logger.warning("HackerNews unexpected error for tag=%s: %s", tag, exc)
            return []

    def _hit_to_signal(self, hit: dict[str, Any]) -> dict:
        title = hit.get("title") or hit.get("story_title") or ""
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
        points = hit.get("points") or 0
        num_comments = hit.get("num_comments") or 0
        story_text = hit.get("story_text") or hit.get("comment_text") or ""

        content_parts = []
        if story_text:
            content_parts.append(story_text)

        content = " ".join(content_parts).strip()

        return self._make_signal(
            title=title,
            url=url,
            content=content,
            metadata={
                "points": points,
                "num_comments": num_comments,
                "author": hit.get("author", ""),
                "created_at": hit.get("created_at", ""),
                "object_id": hit.get("objectID", ""),
                "tags": hit.get("_tags", []),
            },
        )

    def scrape(self) -> list[dict]:
        signals: list[dict] = []
        seen_urls: set[str] = set()

        for tag in ("show_hn", "front_page"):
            hits = self._fetch_stories(tag, hits_per_page=30)
            logger.info("HackerNews tag=%s: %d hits", tag, len(hits))
            for hit in hits:
                signal = self._hit_to_signal(hit)
                if signal["title"] and signal["url"] not in seen_urls:
                    seen_urls.add(signal["url"])
                    signals.append(signal)

        logger.info("HackerNews total signals: %d", len(signals))
        return signals
