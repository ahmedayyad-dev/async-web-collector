"""Tests for the fetch layer: retries, backoff, status handling."""

from __future__ import annotations

import httpx
import pytest
import respx

from async_web_collector.config import Config
from async_web_collector.fetcher import Fetcher


def _config(**overrides: object) -> Config:
    defaults: dict[str, object] = {
        "respect_robots": False,
        "rate_limit": 0,
        "retries": 2,
        "backoff_factor": 0,
    }
    defaults.update(overrides)
    return Config.from_dict(defaults)


@pytest.mark.asyncio
async def test_successful_fetch() -> None:
    config = _config()
    with respx.mock(base_url="https://example.com") as router:
        router.get("/page").mock(return_value=httpx.Response(200, content="مرحبا".encode()))
        async with Fetcher(config) as fetcher:
            result = await fetcher.fetch("https://example.com/page")
    assert result.ok
    assert result.status_code == 200
    assert result.body == "مرحبا"
    assert result.attempts == 1


@pytest.mark.asyncio
async def test_retry_then_success() -> None:
    config = _config()  # retries=2, backoff_factor=0
    with respx.mock(base_url="https://example.com") as router:
        router.get("/page").mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, content=b"ok"),
            ]
        )
        async with Fetcher(config) as fetcher:
            result = await fetcher.fetch("https://example.com/page")
    assert result.ok
    assert result.attempts == 2


@pytest.mark.asyncio
async def test_retries_exhausted() -> None:
    config = _config(retries=2)
    with respx.mock(base_url="https://example.com") as router:
        router.get("/dead").mock(
            side_effect=[httpx.Response(500), httpx.Response(500), httpx.Response(500)]
        )
        async with Fetcher(config) as fetcher:
            result = await fetcher.fetch("https://example.com/dead")
    assert result.ok is False
    assert result.error == "HTTP 500"
    assert result.attempts == 3


@pytest.mark.asyncio
async def test_network_error_retry() -> None:
    config = _config()
    with respx.mock(base_url="https://example.com") as router:
        router.get("/page").mock(
            side_effect=[
                httpx.ConnectError("connection refused"),
                httpx.Response(200, content=b"ok"),
            ]
        )
        async with Fetcher(config) as fetcher:
            result = await fetcher.fetch("https://example.com/page")
    assert result.ok
    assert result.attempts == 2


@pytest.mark.asyncio
async def test_network_error_exhausted() -> None:
    config = _config(retries=1)
    with respx.mock(base_url="https://example.com") as router:
        router.get("/bad").mock(
            side_effect=[
                httpx.ConnectError("boom"),
                httpx.ConnectError("boom"),
            ]
        )
        async with Fetcher(config) as fetcher:
            result = await fetcher.fetch("https://example.com/bad")
    assert result.ok is False
    assert "ConnectError" in (result.error or "")
    assert result.attempts == 2


@pytest.mark.asyncio
async def test_retry_after_respected() -> None:
    config = _config(backoff_factor=0, max_backoff=0.5)
    with respx.mock(base_url="https://example.com") as router:
        router.get("/page").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "0.05"}),
                httpx.Response(200, content=b"ok"),
            ]
        )
        async with Fetcher(config) as fetcher:
            result = await fetcher.fetch("https://example.com/page")
    assert result.ok
    assert result.attempts == 2
    assert result.elapsed >= 0.04


@pytest.mark.asyncio
async def test_client_error_not_retried() -> None:
    config = _config()
    with respx.mock(base_url="https://example.com") as router:
        page = router.get("/404").mock(return_value=httpx.Response(404))
        async with Fetcher(config) as fetcher:
            result = await fetcher.fetch("https://example.com/404")
    assert result.ok is False
    assert result.error == "HTTP 404"
    assert page.call_count == 1
