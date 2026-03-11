from __future__ import annotations

import logging

import httpx
from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

IH_BASE_URL = "https://www.indiehackers.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 30.0


class IndieHackersScraper(BaseScraper):
    name = "indiehackers"

    def __init__(self) -> None:
        super().__init__(rate_limit_seconds=3.0)

    def _fetch_page(self, url: str) -> str:
        self._enforce_rate_limit()
        try:
            with httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.text
        except httpx.HTTPError as exc:
            logger.warning("IndieHackers HTTP error for %s: %s", url, exc)
            return ""
        except Exception as exc:
            logger.warning("IndieHackers unexpected error for %s: %s", url, exc)
            return ""

    def _parse_posts(self, html: str, source_url: str) -> list[dict]:
        if not html:
            return []

        signals: list[dict] = []
        try:
            soup = BeautifulSoup(html, "lxml")

            post_selectors = [
                ("div", {"class": lambda c: c and "story-link" in c}),
                ("a", {"class": lambda c: c and "post" in (c or "")}),
                ("div", {"class": lambda c: c and "feed-item" in (c or "")}),
            ]

            posts = []
            for tag, attrs in post_selectors:
                found = soup.find_all(tag, attrs)
                if found:
                    posts = found
                    break

            if not posts:
                posts = soup.find_all("a", href=lambda h: h and "/post/" in (h or ""))

            seen_urls: set[str] = set()
            for post in posts[:30]:
                title_el = post.find(["h2", "h3", "h4", "strong", "span"])
                title = title_el.get_text(strip=True) if title_el else ""

                if not title and post.name == "a":
                    title = post.get_text(strip=True)[:200]

                href = post.get("href", "") if post.name == "a" else ""
                if not href:
                    link = post.find("a", href=True)
                    href = link["href"] if link else ""

                url = href if href.startswith("http") else f"{IH_BASE_URL}{href}"

                description_el = post.find("p")
                description = description_el.get_text(strip=True) if description_el else ""

                if title and url not in seen_urls and len(title) > 5:
                    seen_urls.add(url)
                    signals.append(
                        self._make_signal(
                            title=title,
                            url=url,
                            content=description,
                            metadata={"source_page": source_url},
                        )
                    )
        except Exception as exc:
            logger.warning("IndieHackers parse error: %s", exc)

        return signals

    def scrape(self) -> list[dict]:
        all_signals: list[dict] = []
        pages = [
            IH_BASE_URL,
            f"{IH_BASE_URL}/posts",
        ]

        for page_url in pages:
            html = self._fetch_page(page_url)
            signals = self._parse_posts(html, page_url)
            logger.info("IndieHackers page=%s: %d signals", page_url, len(signals))
            all_signals.extend(signals)

        seen: set[str] = set()
        unique: list[dict] = []
        for s in all_signals:
            if s["url"] not in seen:
                seen.add(s["url"])
                unique.append(s)

        logger.info("IndieHackers total signals: %d", len(unique))
        return unique
