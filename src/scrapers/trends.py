from __future__ import annotations

import logging
from typing import Any

from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class GoogleTrendsScraper(BaseScraper):
    name = "google_trends"

    def __init__(self) -> None:
        super().__init__(rate_limit_seconds=5.0)

    def _fetch_trending(self, geo: str) -> list[dict]:
        self._enforce_rate_limit()
        try:
            from pytrends.request import TrendReq

            pytrends = TrendReq(hl="en-US", tz=180, timeout=(10, 25))
            trending = pytrends.trending_searches(pn=geo)
            topics = trending[0].tolist() if not trending.empty else []
            return topics
        except ImportError:
            logger.warning("pytrends not installed; skipping Google Trends")
            return []
        except Exception as exc:
            logger.warning("Google Trends error for geo=%s: %s", geo, exc)
            return []

    def _fetch_related_queries(self, keyword: str) -> dict[str, Any]:
        self._enforce_rate_limit()
        try:
            from pytrends.request import TrendReq

            pytrends = TrendReq(hl="en-US", tz=180, timeout=(10, 25))
            pytrends.build_payload([keyword], timeframe="now 7-d", geo="")
            related = pytrends.related_queries()
            rising = related.get(keyword, {}).get("rising")
            if rising is not None and not rising.empty:
                return {"rising": rising["query"].tolist()[:10]}
        except ImportError:
            pass
        except Exception as exc:
            logger.warning("Google Trends related queries error for %s: %s", keyword, exc)
        return {}

    def scrape(self) -> list[dict]:
        signals: list[dict] = []

        geo_configs = [
            ("united_states", "US"),
            ("turkey", "TR"),
        ]

        for geo_name, geo_code in geo_configs:
            topics = self._fetch_trending(geo_name)
            logger.info("Google Trends geo=%s: %d topics", geo_name, len(topics))

            for topic in topics[:20]:
                if not topic:
                    continue
                signals.append(
                    self._make_signal(
                        title=f"Trending: {topic}",
                        url=f"https://trends.google.com/trends/explore?q={topic}&geo={geo_code}",
                        content=f"Currently trending search topic in {geo_name.replace('_', ' ').title()}: {topic}",
                        metadata={
                            "geo": geo_code,
                            "geo_name": geo_name,
                            "trend_type": "trending_search",
                            "topic": topic,
                        },
                    )
                )

        logger.info("Google Trends total signals: %d", len(signals))
        return signals
