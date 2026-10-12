"""Tests for robots.txt handling."""

from __future__ import annotations

import httpx
import pytest
import respx

from async_web_collector.config import Config
from async_web_collector.fetcher import Fetcher


def _config() -> Config:
    return Config(
        respect_robots=True,
        rate_limit=0,
        retries=0,
        user_agent="test-agent",
    )


@pytest.mark.asyncio
async def test_allowed_page_is_fetched() -> None:
    config = _config()
    with respx.mock(base_url="https://example.com") as router:
        router.get("/robots.txt").mock(
            return_value=httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
        )
        page = router.get("/public").mock(return_value=httpx.Response(200, content=b"ok"))
        async with Fetcher(config) as fetcher:
            result = await fetcher.fetch("https://example.com/public")
    assert result.ok
    assert page.called


@pytest.mark.asyncio
async def test_disallowed_page_is_blocked() -> None:
    config = _config()
    with respx.mock(base_url="https://example.com", assert_all_called=False) as router:
        router.get("/robots.txt").mock(
            return_value=httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
        )
        page = router.get("/private/secret").mock(return_value=httpx.Response(200, content=b"nope"))
        async with Fetcher(config) as fetcher:
            result = await fetcher.fetch("https://example.com/private/secret")
    assert result.error == "blocked by robots.txt"
    assert page.called is False


@pytest.mark.asyncio
async def test_missing_robots_allows() -> None:
    config = _config()
    with respx.mock(base_url="https://example.com") as router:
        router.get("/robots.txt").mock(return_value=httpx.Response(404))
        page = router.get("/x").mock(return_value=httpx.Response(200, content=b"ok"))
        async with Fetcher(config) as fetcher:
            result = await fetcher.fetch("https://example.com/x")
    assert result.ok
    assert page.called


@pytest.mark.asyncio
async def test_respect_robots_disabled() -> None:
    config = _config()
    config.respect_robots = False
    with respx.mock(base_url="https://example.com", assert_all_called=False) as router:
        router.get("/robots.txt").mock(
            return_value=httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        )
        page = router.get("/secret").mock(return_value=httpx.Response(200, content=b"ok"))
        async with Fetcher(config) as fetcher:
            result = await fetcher.fetch("https://example.com/secret")
    assert result.ok
    assert page.called


@pytest.mark.asyncio
async def test_robots_is_cached() -> None:
    config = _config()
    with respx.mock(base_url="https://example.com") as router:
        robots = router.get("/robots.txt").mock(
            return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
        )
        router.get("/a").mock(return_value=httpx.Response(200, content=b"a"))
        router.get("/b").mock(return_value=httpx.Response(200, content=b"b"))
        async with Fetcher(config) as fetcher:
            await fetcher.fetch("https://example.com/a")
            await fetcher.fetch("https://example.com/b")
    assert robots.call_count == 1
