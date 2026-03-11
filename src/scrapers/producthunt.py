from __future__ import annotations

import logging
from typing import Any

import feedparser
import httpx
from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

PH_RSS_URL = "https://www.producthunt.com/feed"
PH_NEWEST_URL = "https://www.producthunt.com/newest"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FikirBulucu/1.0; +https://github.com/fikirbulucu)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
TIMEOUT = 30.0


class ProductHuntScraper(BaseScraper):
    name = "producthunt"

    def __init__(self) -> None:
        super().__init__(rate_limit_seconds=2.0)

    def _scrape_rss(self) -> list[dict]:
        self._enforce_rate_limit()
        try:
            with httpx.Client(timeout=TIMEOUT, headers=HEADERS) as client:
                response = client.get(PH_RSS_URL)
                response.raise_for_status()
                feed_text = response.text
        except httpx.HTTPError as exc:
            logger.warning("ProductHunt RSS HTTP error: %s", exc)
            return []
        except Exception as exc:
            logger.warning("ProductHunt RSS unexpected error: %s", exc)
            return []

        try:
            feed = feedparser.parse(feed_text)
        except Exception as exc:
            logger.warning("ProductHunt RSS parse error: %s", exc)
            return []

        signals: list[dict] = []
        for entry in feed.entries:
            title = getattr(entry, "title", "") or ""
            url = getattr(entry, "link", "") or ""
            summary = getattr(entry, "summary", "") or ""

            soup = BeautifulSoup(summary, "lxml")
            description = soup.get_text(separator=" ", strip=True)

            tagline = ""
            if " - " in title:
                parts = title.split(" - ", 1)
                title = parts[0].strip()
                tagline = parts[1].strip()

            if title:
                signals.append(
                    self._make_signal(
                        title=title,
                        url=url,
                        content=description,
                        metadata={
                            "tagline": tagline,
                            "published": getattr(entry, "published", ""),
                            "source_type": "rss",
                        },
                    )
                )

        return signals

    def _scrape_html(self) -> list[dict]:
        self._enforce_rate_limit()
        try:
            with httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
                response = client.get(PH_NEWEST_URL)
                response.raise_for_status()
                html = response.text
        except httpx.HTTPError as exc:
            logger.warning("ProductHunt HTML HTTP error: %s", exc)
            return []
        except Exception as exc:
            logger.warning("ProductHunt HTML unexpected error: %s", exc)
            return []

        signals: list[dict] = []
        try:
            soup = BeautifulSoup(html, "lxml")
            items = soup.find_all("li", attrs={"data-test": True})
            if not items:
                items = soup.find_all("div", class_=lambda c: c and "item" in c.lower())

            for item in items[:30]:
                name_el = item.find(["h3", "h2", "strong"])
                tagline_el = item.find(["p", "span"], class_=lambda c: c and "tagline" in (c or "").lower())
                link_el = item.find("a", href=True)

                title = name_el.get_text(strip=True) if name_el else ""
                tagline = tagline_el.get_text(strip=True) if tagline_el else ""
                url = ""
                if link_el:
                    href = link_el["href"]
                    url = href if href.startswith("http") else f"https://www.producthunt.com{href}"

                if title:
                    signals.append(
                        self._make_signal(
                            title=title,
                            url=url,
                            content=tagline,
                            metadata={"tagline": tagline, "source_type": "html"},
                        )
                    )
        except Exception as exc:
            logger.warning("ProductHunt HTML parse error: %s", exc)

        return signals

    def scrape(self) -> list[dict]:
        signals = self._scrape_rss()
        if signals:
            logger.info("ProductHunt RSS: %d signals", len(signals))
            return signals

        logger.info("ProductHunt RSS empty, falling back to HTML scrape")
        signals = self._scrape_html()
        logger.info("ProductHunt HTML: %d signals", len(signals))
        return signals
