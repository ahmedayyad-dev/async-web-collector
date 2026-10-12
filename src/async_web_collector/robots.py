"""robots.txt fetching, parsing and caching."""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx


class RobotsCache:
    """Fetch and cache ``robots.txt`` files, one parser per origin."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        user_agent: str,
        *,
        enabled: bool = True,
    ) -> None:
        self._client = client
        self._user_agent = user_agent
        self._enabled = enabled
        self._parsers: dict[str, RobotFileParser | None] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._registry_lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def _lock_for(self, origin: str) -> asyncio.Lock:
        async with self._registry_lock:
            lock = self._locks.get(origin)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[origin] = lock
            return lock

    async def _load(self, origin: str) -> RobotFileParser | None:
        try:
            response = await self._client.get(f"{origin}/robots.txt")
        except httpx.HTTPError:
            return None
        if response.status_code >= 400:
            return None
        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser

    async def _parser_for(self, origin: str) -> RobotFileParser | None:
        if origin in self._parsers:
            return self._parsers[origin]
        lock = await self._lock_for(origin)
        async with lock:
            if origin not in self._parsers:
                self._parsers[origin] = await self._load(origin)
            return self._parsers[origin]

    async def allowed(self, url: str) -> bool:
        """Return whether ``url`` may be fetched under robots.txt rules."""
        if not self._enabled:
            return True
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return True
        origin = f"{parsed.scheme}://{parsed.netloc}"
        parser = await self._parser_for(origin)
        if parser is None:
            return True
        return parser.can_fetch(self._user_agent, url)
