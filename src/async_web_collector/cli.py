"""Command line interface built with Typer."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated

import httpx
import typer

from async_web_collector import __version__
from async_web_collector.collector import Collector
from async_web_collector.config import (
    DEFAULT_USER_AGENT,
    Config,
    ConfigError,
    FieldSpec,
    load_config,
)
from async_web_collector.exporter import export
from async_web_collector.fetcher import Fetcher
from async_web_collector.robots import RobotsCache

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Responsible asynchronous collection of public web data.",
)

logger = logging.getLogger("async_web_collector")


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )


def _split_attr(token: str) -> tuple[str, str]:
    """Split ``selector@attr`` without tripping on XPath's ``/@`` axis."""
    index = len(token)
    while True:
        index = token.rfind("@", 0, index)
        if index <= 0:
            return token, "text"
        if token[index - 1] != "/":
            return token[:index], token[index + 1 :]


def parse_selectors(spec: str) -> list[FieldSpec]:
    """Parse ``name=selector[@attr];name=...`` into field specifications."""
    fields: list[FieldSpec] = []
    for chunk in spec.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise ConfigError(f"selector must look like name=selector: {chunk!r}")
        name, selector = chunk.split("=", 1)
        selector, attr = _split_attr(selector.strip())
        if not name.strip() or not selector:
            raise ConfigError(f"invalid selector entry: {chunk!r}")
        selector_type = "auto"
        lowered = selector.lower()
        if lowered.startswith("xpath:"):
            selector = selector.split(":", 1)[1].strip()
            selector_type = "xpath"
        elif lowered.startswith("css:"):
            selector = selector.split(":", 1)[1].strip()
            selector_type = "css"
        if not selector:
            raise ConfigError(f"invalid selector entry: {chunk!r}")
        fields.append(
            FieldSpec(name=name.strip(), selector=selector, selector_type=selector_type, attr=attr)
        )
    return fields


def _build_config(
    *,
    config_path: Path | None,
    output: Path | None,
    fmt: str | None,
    concurrency: int | None,
    rate_limit: float | None,
    timeout: float | None,
    retries: int | None,
    selectors: str | None,
    user_agent: str | None,
    no_robots: bool,
    crawl: bool,
    max_pages: int | None,
    max_depth: int | None,
    same_domain: bool,
) -> Config:
    config = load_config(config_path)
    if output is not None:
        config.output.path = str(output)
    if fmt is not None:
        config.output.format = fmt
    if concurrency is not None:
        config.concurrency = concurrency
    if rate_limit is not None:
        config.rate_limit = rate_limit
    if timeout is not None:
        config.timeout = timeout
    if retries is not None:
        config.retries = retries
    if selectors is not None:
        config.fields = parse_selectors(selectors)
    if user_agent is not None:
        config.user_agent = user_agent
    if no_robots:
        config.respect_robots = False
    if crawl:
        config.crawl.enabled = True
    if max_pages is not None:
        config.crawl.max_pages = max_pages
    if max_depth is not None:
        config.crawl.max_depth = max_depth
    config.crawl.same_domain = same_domain
    config.output.__post_init__()
    config.__post_init__()
    return config


async def _run(config: Config, urls: list[str]) -> list[dict[str, object]]:
    async with Fetcher(config) as fetcher:
        collector = Collector(config, fetcher)
        return await collector.collect(urls)


@app.command()
def fetch(
    urls: Annotated[list[str], typer.Argument(help="One or more URLs to collect")],
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to a YAML configuration file"),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output file path"),
    ] = None,
    fmt: Annotated[
        str | None,
        typer.Option("--format", "-f", help="Output format: json or csv"),
    ] = None,
    concurrency: Annotated[
        int | None,
        typer.Option("--concurrency", help="Maximum concurrent requests"),
    ] = None,
    rate_limit: Annotated[
        float | None,
        typer.Option("--rate-limit", help="Requests per second allowed per host"),
    ] = None,
    timeout: Annotated[
        float | None,
        typer.Option("--timeout", help="Request timeout in seconds"),
    ] = None,
    retries: Annotated[
        int | None,
        typer.Option("--retries", help="Retry attempts per request"),
    ] = None,
    selectors: Annotated[
        str | None,
        typer.Option("--selectors", help="Fields as name=selector[@attr];name=..."),
    ] = None,
    user_agent: Annotated[
        str | None,
        typer.Option("--user-agent", help="User-Agent header to send"),
    ] = None,
    no_robots: Annotated[
        bool,
        typer.Option("--no-robots", help="Ignore robots.txt (use responsibly)"),
    ] = False,
    crawl: Annotated[
        bool,
        typer.Option("--crawl", help="Follow links discovered on the pages"),
    ] = False,
    max_pages: Annotated[
        int | None,
        typer.Option("--max-pages", help="Maximum pages to fetch while crawling"),
    ] = None,
    max_depth: Annotated[
        int | None,
        typer.Option("--max-depth", help="Maximum crawl depth"),
    ] = None,
    same_domain: Annotated[
        bool,
        typer.Option("--same-domain/--no-same-domain", help="Stay on the starting host"),
    ] = True,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable debug logging"),
    ] = False,
) -> None:
    """Collect data from one or more URLs."""
    _configure_logging(verbose)
    if not urls:
        raise typer.BadParameter("at least one URL is required")
    try:
        config_obj = _build_config(
            config_path=config,
            output=output,
            fmt=fmt,
            concurrency=concurrency,
            rate_limit=rate_limit,
            timeout=timeout,
            retries=retries,
            selectors=selectors,
            user_agent=user_agent,
            no_robots=no_robots,
            crawl=crawl,
            max_pages=max_pages,
            max_depth=max_depth,
            same_domain=same_domain,
        )
    except ConfigError as exc:
        raise typer.BadParameter(str(exc)) from exc

    rows = asyncio.run(_run(config_obj, urls))
    path = export(rows, config_obj.output.format, config_obj.output.path)
    typer.echo(f"Collected {len(rows)} record(s) -> {path}")


@app.command()
def robots(
    url: Annotated[str, typer.Argument(help="URL to test against robots.txt")],
    user_agent: Annotated[
        str | None,
        typer.Option("--user-agent", help="User-Agent to evaluate rules for"),
    ] = None,
) -> None:
    """Check whether a URL is allowed by its host's robots.txt."""
    agent = user_agent or DEFAULT_USER_AGENT
    allowed = asyncio.run(_check_robots(url, agent))
    verdict = "ALLOWED" if allowed else "DISALLOWED"
    typer.echo(f"{verdict}: {url}")
    if not allowed:
        raise typer.Exit(code=1)


async def _check_robots(url: str, user_agent: str) -> bool:
    async with httpx.AsyncClient(
        headers={"User-Agent": user_agent},
        timeout=20.0,
        follow_redirects=True,
    ) as client:
        cache = RobotsCache(client, user_agent, enabled=True)
        return await cache.allowed(url)


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(f"async-web-collector {__version__}")


if __name__ == "__main__":  # pragma: no cover
    app()
