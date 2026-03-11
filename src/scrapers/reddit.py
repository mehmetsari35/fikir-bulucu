from __future__ import annotations

import logging

import httpx

from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SUBREDDITS = [
    "startups",
    "SideProject",
    "Entrepreneur",
    "Business_Ideas",
    "SaaS",
    "indiehackers",
]

HEADERS = {
    "User-Agent": "FikirBulucu/1.0 (AI Opportunity Radar; personal research bot)",
    "Accept": "application/json",
}
TIMEOUT = 30.0


class RedditScraper(BaseScraper):
    name = "reddit"

    def __init__(self) -> None:
        super().__init__(rate_limit_seconds=2.0)

    def _fetch_subreddit(self, subreddit: str) -> list[dict]:
        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=25"
        self._enforce_rate_limit()
        try:
            with httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            logger.warning("Reddit HTTP error for r/%s: %s", subreddit, exc)
            return []
        except Exception as exc:
            logger.warning("Reddit unexpected error for r/%s: %s", subreddit, exc)
            return []

        signals: list[dict] = []
        try:
            posts = data.get("data", {}).get("children", [])
            for post in posts:
                post_data = post.get("data", {})
                title = post_data.get("title", "")
                url = post_data.get("url", "")
                selftext = post_data.get("selftext", "") or ""
                score = post_data.get("score", 0)
                num_comments = post_data.get("num_comments", 0)
                permalink = post_data.get("permalink", "")
                is_self = post_data.get("is_self", False)
                flair = post_data.get("link_flair_text", "") or ""

                if not title:
                    continue

                post_url = url if not is_self else f"https://www.reddit.com{permalink}"

                content = selftext[:2000] if selftext else ""

                signals.append(
                    self._make_signal(
                        title=title,
                        url=post_url,
                        content=content,
                        metadata={
                            "subreddit": subreddit,
                            "score": score,
                            "num_comments": num_comments,
                            "flair": flair,
                            "is_self": is_self,
                            "author": post_data.get("author", ""),
                        },
                    )
                )
        except Exception as exc:
            logger.warning("Reddit parse error for r/%s: %s", subreddit, exc)

        return signals

    def scrape(self) -> list[dict]:
        all_signals: list[dict] = []
        for subreddit in SUBREDDITS:
            signals = self._fetch_subreddit(subreddit)
            logger.info("Reddit r/%s: %d signals", subreddit, len(signals))
            all_signals.extend(signals)

        logger.info("Reddit total signals: %d", len(all_signals))
        return all_signals
