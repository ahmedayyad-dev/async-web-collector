"""Tests for per-host rate limiting."""

from __future__ import annotations

import time

import pytest

from async_web_collector.ratelimit import HostRateLimiter


@pytest.mark.asyncio
async def test_same_host_is_spaced() -> None:
    limiter = HostRateLimiter(rate=200)  # 5 ms interval
    start = time.monotonic()
    for _ in range(3):
        await limiter.acquire("https://example.com/a")
    elapsed = time.monotonic() - start
    assert elapsed >= 0.008  # two enforced intervals


@pytest.mark.asyncio
async def test_different_hosts_not_spaced() -> None:
    limiter = HostRateLimiter(rate=200)
    start = time.monotonic()
    await limiter.acquire("https://a.example/x")
    await limiter.acquire("https://b.example/x")
    elapsed = time.monotonic() - start
    assert elapsed < 0.005


def test_zero_rate_disables() -> None:
    limiter = HostRateLimiter(0)
    assert limiter.enabled is False


def test_negative_rate_disables() -> None:
    assert HostRateLimiter(-1).enabled is False
