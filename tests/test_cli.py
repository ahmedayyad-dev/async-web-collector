"""Tests for the CLI."""

from __future__ import annotations

import json

import httpx
import respx
from typer.testing import CliRunner

from async_web_collector.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_fetch_single_page(tmp_path) -> None:
    output = tmp_path / "results.json"
    with respx.mock(base_url="https://example.com") as router:
        router.get("/robots.txt").mock(
            return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
        )
        router.get("/page").mock(
            return_value=httpx.Response(
                200,
                content=b"<html><body><h1>Hello</h1></body></html>",
            )
        )
        result = runner.invoke(
            app,
            [
                "fetch",
                "https://example.com/page",
                "--selectors",
                "title=h1",
                "--output",
                str(output),
                "--rate-limit",
                "0",
            ],
        )
    assert result.exit_code == 0, result.output
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data[0]["title"] == "Hello"
    assert data[0]["url"] == "https://example.com/page"
    assert "Collected 1 record(s)" in result.stdout


def test_fetch_requires_urls() -> None:
    result = runner.invoke(app, ["fetch"])
    assert result.exit_code != 0


def test_robots_allowed() -> None:
    with respx.mock(base_url="https://example.com") as router:
        router.get("/robots.txt").mock(
            return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
        )
        result = runner.invoke(app, ["robots", "https://example.com/page"])
    assert result.exit_code == 0
    assert "ALLOWED" in result.stdout


def test_robots_disallowed() -> None:
    with respx.mock(base_url="https://example.com") as router:
        router.get("/robots.txt").mock(
            return_value=httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        )
        result = runner.invoke(app, ["robots", "https://example.com/page"])
    assert result.exit_code == 1
    assert "DISALLOWED" in result.stdout


def test_parse_selectors() -> None:
    from async_web_collector.cli import parse_selectors

    fields = parse_selectors("title=h1;link=a@href;sku=xpath://span/@data-sku")
    assert [field.name for field in fields] == ["title", "link", "sku"]
    assert fields[1].attr == "href"
    assert fields[2].selector_type == "xpath"
    assert fields[2].selector == "//span/@data-sku"


def test_bad_config_file() -> None:
    result = runner.invoke(
        app,
        ["fetch", "https://example.com", "--config", "missing.yaml"],
    )
    assert result.exit_code == 2
    assert "configuration file not found" in result.output
