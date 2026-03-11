from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Optional


class BaseScraper(ABC):
    name: str = "base"
    _last_request_time: float = 0.0
    _min_request_interval: float = 1.0  # seconds between requests

    def __init__(self, rate_limit_seconds: float = 1.0) -> None:
        self._min_request_interval = rate_limit_seconds

    def _enforce_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.monotonic()

    async def _async_enforce_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.monotonic()

    @abstractmethod
    def scrape(self) -> list[dict]:
        """
        Fetch signals from the source.

        Returns a list of dicts with keys:
            title (str), url (str), content (str), metadata (dict)
        """
        ...

    def _make_signal(
        self,
        title: str,
        url: str = "",
        content: str = "",
        metadata: Optional[dict] = None,
    ) -> dict:
        return {
            "title": title,
            "url": url,
            "content": content,
            "metadata": metadata or {},
        }
