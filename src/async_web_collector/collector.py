"""Orchestration: fetch, discover, extract and collect records."""

from __future__ import annotations

import asyncio
from urllib.parse import urljoin, urlparse

from async_web_collector.config import Config
from async_web_collector.extract import HtmlDocument
from async_web_collector.fetcher import Fetcher
from async_web_collector.models import FetchResult


class Collector:
    """Drive fetching and extraction over one or many pages."""

    def __init__(self, config: Config, fetcher: Fetcher) -> None:
        self.config = config
        self.fetcher = fetcher

    async def collect(self, urls: list[str]) -> list[dict[str, object]]:
        """Collect records for ``urls``, crawling when configured to."""
        if self.config.crawl.enabled:
            return await self._crawl(urls)
        results = await asyncio.gather(*(self.fetcher.fetch(url) for url in urls))
        rows: list[dict[str, object]] = []
        for result in results:
            rows.extend(self._records(result))
        return rows

    def _records(self, result: FetchResult) -> list[dict[str, object]]:
        if not result.ok or not result.content:
            return []
        document = HtmlDocument(result.body)
        extracted = document.extract_records(self.config.fields, self.config.extract_scope)
        rows: list[dict[str, object]] = []
        for record in extracted:
            row: dict[str, object] = {"url": result.url, "status_code": result.status_code}
            row.update(record)
            rows.append(row)
        return rows

    async def _crawl(self, start_urls: list[str]) -> list[dict[str, object]]:
        crawl = self.config.crawl
        seen: set[str] = set()
        frontier: list[tuple[str, int]] = []
        for url in start_urls:
            if url not in seen:
                seen.add(url)
                frontier.append((url, 0))

        rows: list[dict[str, object]] = []
        while frontier and len(seen) <= crawl.max_pages:
            batch = frontier
            frontier = []
            results = await asyncio.gather(*(self.fetcher.fetch(url) for url, _ in batch))
            for (url, depth), result in zip(batch, results, strict=True):
                rows.extend(self._records(result))
                if depth >= crawl.max_depth or not result.ok:
                    continue
                for link in self._discover_links(result, url):
                    if len(seen) >= crawl.max_pages:
                        break
                    if link in seen:
                        continue
                    if crawl.same_domain and urlparse(link).netloc != urlparse(url).netloc:
                        continue
                    seen.add(link)
                    frontier.append((link, depth + 1))
        return rows

    @staticmethod
    def _discover_links(result: FetchResult, base_url: str) -> list[str]:
        if not result.content:
            return []
        document = HtmlDocument(result.body)
        links: list[str] = []
        for node in document.css_tree.css("a[href]"):
            href = node.attributes.get("href")
            if not href:
                continue
            absolute = urljoin(base_url, href.split("#", 1)[0])
            parsed = urlparse(absolute)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                links.append(absolute)
        return links
