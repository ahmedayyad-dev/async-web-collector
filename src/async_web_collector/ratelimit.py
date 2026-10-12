"""Per-host asynchronous rate limiting."""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse


class HostRateLimiter:
    """Enforce a minimum delay between requests to the same host.

    ``rate`` is the maximum number of requests per second allowed per host.
    A value of ``0`` (or less) disables limiting entirely.
    """

    def __init__(self, rate: float) -> None:
        self._min_interval = 0.0 if rate <= 0 else 1.0 / rate
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_seen: dict[str, float] = {}
        self._registry_lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self._min_interval > 0

    async def _lock_for(self, host: str) -> asyncio.Lock:
        async with self._registry_lock:
            lock = self._locks.get(host)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[host] = lock
            return lock

    async def acquire(self, url: str) -> None:
        """Wait until a request to ``url`` is permitted by the rate limit."""
        if not self.enabled:
            return
        host = urlparse(url).netloc
        lock = await self._lock_for(host)
        async with lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            last = self._last_seen.get(host)
            if last is not None:
                wait = self._min_interval - (now - last)
                if wait > 0:
                    await asyncio.sleep(wait)
                    now = loop.time()
            self._last_seen[host] = now
