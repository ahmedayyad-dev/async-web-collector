# async-web-collector

**Responsible asynchronous collection of public web data.**

`async-web-collector` is a small, dependency-light toolkit for fetching and
extracting public web data politely and predictably. It is built on
[`httpx.AsyncClient`](https://www.python-httpx.org/async/) with bounded
concurrency, per-host rate limiting, retries with exponential backoff, and
robots.txt compliance. HTML is parsed with the fast
[`selectolax`](https://github.com/rushter/selectolax) engine for CSS selectors
and [`lxml`](https://lxml.de/) for XPath. Results are exported to JSON or CSV.

> Use this tool responsibly. Always respect `robots.txt`, the target site's
> terms of service, and applicable law. Prefer official APIs when they exist.

## Features

- Async fetching with a single pooled `httpx.AsyncClient`.
- Bounded concurrency via an `asyncio.Semaphore`.
- Retries with exponential backoff + jitter, honouring `Retry-After`.
- Per-host rate limiting (requests per second).
- `robots.txt` fetching, parsing, caching and enforcement.
- Extraction with **CSS selectors** (selectolax) and **XPath** (lxml).
- Optional crawling with `max_pages`, `max_depth` and same-domain restriction.
- JSON and CSV export.
- YAML configuration plus a full CLI (Typer).
- Typed, tested with pytest + respx.

## Installation

Requires Python 3.12+.

```bash
uv add async-web-collector
# or, with HTTP/2 support:
uv add "async-web-collector[http2]"
```

For local development:

```bash
uv sync
uv run pytest
```

## Quick start

```bash
uv run async-web-collector fetch https://example.com \
    --selectors "title=h1@text;links=a[href]@href" \
    --output out/example.json
```

XPath fields are detected automatically (a selector starting with `/`, `(`,
`./` or `../` is treated as XPath):

```bash
uv run async-web-collector fetch https://example.com/products \
    --selectors "name=xpath://h2[@class='title']/text();link=//a@href"
```

Only selectors starting with `/`, `(`, `./` or `../` are treated as XPath; you
may force a kind with the `css:` or `xpath:` prefix. For structured extraction
that repeats on many pages, prefer a YAML config file (below).

The recommended way to define non-trivial extraction is a YAML config file:

```bash
uv run async-web-collector fetch https://example.com/shop -c config.yaml
```

## Configuration

See [`config.example.yaml`](config.example.yaml). Supported keys:

| Key | Default | Description |
| --- | --- | --- |
| `concurrency` | `8` | Maximum concurrent requests. |
| `timeout` | `20` | Per-request timeout in seconds. |
| `retries` | `3` | Retry attempts for failures/retryable statuses. |
| `backoff_factor` | `0.5` | Base delay for exponential backoff. |
| `max_backoff` | `30` | Upper bound on backoff delay (seconds). |
| `rate_limit` | `2` | Requests per second per host (`0` disables). |
| `respect_robots` | `true` | Enforce robots.txt. |
| `user_agent` | `async-web-collector/0.1 …` | User-Agent header. |
| `headers` | `{}` | Extra request headers. |
| `follow_redirects` | `true` | Follow HTTP redirects. |
| `http2` | `false` | Enable HTTP/2 (needs the `http2` extra). |
| `verify` | `true` | Verify TLS certificates. |
| `extract.scope` | `null` | Container selector; one record per match. |
| `extract.fields` | `[]` | Field specifications (see below). |
| `crawl` | disabled | `enabled`, `max_pages`, `max_depth`, `same_domain`. |
| `output` | `json` | `format` (`json`/`csv`) and `path`. |

### Field specifications

Each field is a mapping with a `name` and either a `css` or `xpath` selector,
plus optional `attr`, `all`, `separator` and `strip`:

```yaml
extract:
  scope: "article.product"        # CSS or XPath container
  fields:
    - {name: title, css: "h2.title", attr: text}
    - {name: price, css: "span.price", attr: text}
    - {name: link,  css: "a", attr: href}
    - {name: tags,  css: "ul.tags li", all: true}
    - {name: sku,   xpath: ".//span[@class='sku']/text()"}
```

`attr` may be `text` (default), `html`, or any attribute name. `all: true`
returns a list; otherwise the first match is returned.

## CLI reference

```
async-web-collector fetch URL... [OPTIONS]
  -c, --config PATH        YAML configuration file
  -o, --output PATH        Output file path
  -f, --format TEXT        json or csv
      --concurrency INT    Maximum concurrent requests
      --rate-limit FLOAT   Requests per second per host
      --timeout FLOAT      Request timeout (seconds)
      --retries INT        Retry attempts per request
      --selectors TEXT     name=selector[@attr];name=...
      --user-agent TEXT    User-Agent header
      --no-robots          Ignore robots.txt (use responsibly)
      --crawl              Follow discovered links
      --max-pages INT      Maximum pages while crawling
      --max-depth INT      Maximum crawl depth
      --same-domain / --no-same-domain
  -v, --verbose            Debug logging

async-web-collector robots URL [--user-agent TEXT]
async-web-collector version
```

`--selectors` uses `;` between fields and `=` between name and selector, with
an optional `@attr` suffix (e.g. `link=a@href`). XPath selectors are detected
automatically.

## Python API

```python
import asyncio
from async_web_collector.config import Config, FieldSpec
from async_web_collector.collector import Collector
from async_web_collector.fetcher import Fetcher
from async_web_collector.exporter import export

config = Config(
    fields=[
        FieldSpec(name="title", selector="h1"),
        FieldSpec(name="link", selector="a", attr="href"),
    ],
)


async def main() -> None:
    async with Fetcher(config) as fetcher:
        rows = await Collector(config, fetcher).collect(["https://example.com"])
    export(rows, "json", "out/results.json")
    print(rows)


asyncio.run(main())
```

## Development

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

## License

MIT — see [LICENSE](LICENSE).
