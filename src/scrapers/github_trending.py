from __future__ import annotations

import logging

import httpx
from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

GITHUB_TRENDING_URL = "https://github.com/trending"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 30.0


class GitHubTrendingScraper(BaseScraper):
    name = "github_trending"

    def __init__(self) -> None:
        super().__init__(rate_limit_seconds=2.0)

    def _parse_stars(self, text: str) -> int:
        if not text:
            return 0
        text = text.strip().replace(",", "").replace("k", "000").replace("K", "000")
        digits = "".join(c for c in text if c.isdigit())
        return int(digits) if digits else 0

    def scrape(self) -> list[dict]:
        self._enforce_rate_limit()
        try:
            with httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
                response = client.get(GITHUB_TRENDING_URL)
                response.raise_for_status()
                html = response.text
        except httpx.HTTPError as exc:
            logger.warning("GitHub Trending HTTP error: %s", exc)
            return []
        except Exception as exc:
            logger.warning("GitHub Trending unexpected error: %s", exc)
            return []

        signals: list[dict] = []
        try:
            soup = BeautifulSoup(html, "lxml")
            repo_articles = soup.find_all("article", class_=lambda c: c and "Box-row" in (c or ""))

            if not repo_articles:
                repo_articles = soup.find_all("article")

            for article in repo_articles[:30]:
                h2 = article.find("h2")
                if not h2:
                    continue

                repo_link = h2.find("a", href=True)
                if not repo_link:
                    continue

                repo_path = repo_link.get("href", "").strip().lstrip("/")
                repo_url = f"https://github.com/{repo_path}"

                parts = repo_path.split("/")
                repo_name = "/".join(parts[:2]) if len(parts) >= 2 else repo_path

                description_el = article.find("p")
                description = description_el.get_text(strip=True) if description_el else ""

                language_el = article.find("span", attrs={"itemprop": "programmingLanguage"})
                language = language_el.get_text(strip=True) if language_el else ""

                stars_el = article.find("a", href=lambda h: h and "/stargazers" in (h or ""))
                total_stars = self._parse_stars(stars_el.get_text()) if stars_el else 0

                stars_today_el = article.find("span", class_=lambda c: c and "d-inline-block" in (c or ""))
                stars_today_text = stars_today_el.get_text(strip=True) if stars_today_el else ""
                stars_today = self._parse_stars(stars_today_text)

                if repo_name:
                    title = f"{repo_name}: {description}" if description else repo_name
                    signals.append(
                        self._make_signal(
                            title=title[:500],
                            url=repo_url,
                            content=description,
                            metadata={
                                "repo_name": repo_name,
                                "language": language,
                                "total_stars": total_stars,
                                "stars_today": stars_today,
                            },
                        )
                    )
        except Exception as exc:
            logger.warning("GitHub Trending parse error: %s", exc)

        logger.info("GitHub Trending total signals: %d", len(signals))
        return signals
