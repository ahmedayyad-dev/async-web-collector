"""Tests for the crawl orchestration."""

from __future__ import annotations

import httpx
import pytest
import respx

from async_web_collector.collector import Collector
from async_web_collector.config import Config, CrawlConfig, FieldSpec
from async_web_collector.fetcher import Fetcher


@pytest.mark.asyncio
async def test_crawl_follows_links() -> None:
    config = Config(
        respect_robots=False,
        rate_limit=0,
        retries=0,
        fields=[FieldSpec(name="title", selector="h1")],
        crawl=CrawlConfig(enabled=True, max_pages=3, max_depth=2, same_domain=True),
    )
    pages = {
        "/": (
            '<html><a href="/a">a</a>'
            '<a href="https://other.example/ext">x</a>'
            '<a href="/b">b</a></html>'
        ),
        "/a": "<h1>A</h1>",
        "/b": "<h1>B</h1>",
    }
    with respx.mock(base_url="https://example.com") as router:
        for path, html in pages.items():
            router.get(path).mock(return_value=httpx.Response(200, text=html))
        async with Fetcher(config) as fetcher:
            rows = await Collector(config, fetcher).collect(["https://example.com/"])

    urls = {row["url"] for row in rows}
    assert "https://example.com/" in urls
    assert "https://example.com/a" in urls
    assert "https://example.com/b" in urls
    assert "https://other.example/ext" not in urls
    titles = {row["title"] for row in rows if row["url"] == "https://example.com/a"}
    assert titles == {"A"}


@pytest.mark.asyncio
async def test_crawl_respects_max_pages() -> None:
    config = Config(
        respect_robots=False,
        rate_limit=0,
        retries=0,
        crawl=CrawlConfig(enabled=True, max_pages=2, max_depth=2, same_domain=True),
    )
    pages = {
        "/": '<html><a href="/a">a</a><a href="/b">b</a></html>',
        "/a": "<p>a</p>",
        "/b": "<p>b</p>",
    }
    with respx.mock(base_url="https://example.com", assert_all_called=False) as router:
        for path, html in pages.items():
            router.get(path).mock(return_value=httpx.Response(200, text=html))
        async with Fetcher(config) as fetcher:
            rows = await Collector(config, fetcher).collect(["https://example.com/"])

    urls = {row["url"] for row in rows}
    assert "https://example.com/" in urls
    assert len(urls) == 2  # only the start page + one more


@pytest.mark.asyncio
async def test_fetch_multiple_urls() -> None:
    config = Config(
        respect_robots=False,
        rate_limit=0,
        retries=0,
        fields=[FieldSpec(name="h", selector="h1")],
    )
    with respx.mock(base_url="https://example.com") as router:
        router.get("/one").mock(return_value=httpx.Response(200, text="<h1>One</h1>"))
        router.get("/missing").mock(return_value=httpx.Response(404))
        async with Fetcher(config) as fetcher:
            rows = await Collector(config, fetcher).collect(
                ["https://example.com/one", "https://example.com/missing"]
            )
    assert len(rows) == 1
    assert rows[0]["h"] == "One"
    assert rows[0]["url"] == "https://example.com/one"
