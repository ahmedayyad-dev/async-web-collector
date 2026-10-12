"""Asynchronous fetch layer: one client, bounded concurrency, retries, backoff."""

from __future__ import annotations

import asyncio
import random
import time
from email.utils import parsedate_to_datetime

import httpx

from async_web_collector.config import Config
from async_web_collector.models import FetchResult
from async_web_collector.ratelimit import HostRateLimiter
from async_web_collector.robots import RobotsCache

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class Fetcher:
    """Fetch URLs responsibly: robots-aware, rate-limited, concurrency-bounded."""

    def __init__(
        self,
        config: Config,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self._semaphore = asyncio.Semaphore(config.concurrency)
        self._limiter = HostRateLimiter(config.rate_limit)
        self._client = httpx.AsyncClient(
            headers={"User-Agent": config.user_agent, **config.headers},
            timeout=httpx.Timeout(config.timeout, pool=max(config.timeout * 2, 30.0)),
            limits=httpx.Limits(
                max_connections=config.concurrency,
                max_keepalive_connections=config.concurrency,
            ),
            follow_redirects=config.follow_redirects,
            verify=config.verify,
            http2=config.http2,
            transport=transport,
        )
        self._robots = RobotsCache(
            self._client,
            config.user_agent,
            enabled=config.respect_robots,
        )

    @property
    def client(self) -> httpx.AsyncClient:
        """The underlying HTTP client (used by the robots cache and tests)."""
        return self._client

    async def __aenter__(self) -> Fetcher:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP client and its connection pool."""
        await self._client.aclose()

    async def fetch(self, url: str) -> FetchResult:
        """Fetch ``url``, honouring robots.txt and the concurrency limit."""
        if not await self._robots.allowed(url):
            return FetchResult(url=url, error="blocked by robots.txt")
        async with self._semaphore:
            return await self._fetch_with_retries(url)

    async def _fetch_with_retries(self, url: str) -> FetchResult:
        start = time.monotonic()
        last_error = "unknown error"
        for attempt in range(self.config.retries + 1):
            await self._limiter.acquire(url)
            try:
                response = await self._client.get(url)
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < self.config.retries:
                    await self._backoff(attempt, retry_after=None)
                    continue
                return FetchResult(
                    url=url,
                    error=last_error,
                    attempts=attempt + 1,
                    elapsed=time.monotonic() - start,
                )

            if response.status_code in RETRYABLE_STATUS and attempt < self.config.retries:
                await self._backoff(
                    attempt,
                    retry_after=response.headers.get("Retry-After"),
                )
                continue

            error = None if response.is_success else f"HTTP {response.status_code}"
            return FetchResult(
                url=url,
                status_code=response.status_code,
                content=response.content,
                headers=dict(response.headers),
                error=error,
                attempts=attempt + 1,
                elapsed=time.monotonic() - start,
            )

        return FetchResult(  # pragma: no cover - loop always returns
            url=url,
            error=last_error,
            attempts=self.config.retries + 1,
            elapsed=time.monotonic() - start,
        )

    async def _backoff(self, attempt: int, *, retry_after: str | None) -> None:
        delay = self.config.backoff_factor * (2**attempt)
        parsed = self._parse_retry_after(retry_after)
        if parsed is not None:
            delay = max(delay, parsed)
        delay += random.uniform(0, self.config.backoff_factor)
        delay = min(delay, self.config.max_backoff)
        if delay > 0:
            await asyncio.sleep(delay)

    @staticmethod
    def _parse_retry_after(value: str | None) -> float | None:
        if not value:
            return None
        value = value.strip()
        try:
            return max(0.0, float(value))
        except ValueError:
            pass
        try:
            when = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        import datetime as _dt

        now = _dt.datetime.now(tz=when.tzinfo) if when.tzinfo else _dt.datetime.now()
        return max(0.0, (when - now).total_seconds())
