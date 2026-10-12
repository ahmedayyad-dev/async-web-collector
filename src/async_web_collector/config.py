"""Configuration model loaded from YAML (or built from CLI flags)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_USER_AGENT = "async-web-collector/0.1 (+https://github.com/ahmedayyad/async-web-collector)"

VALID_SELECTOR_TYPES = ("auto", "css", "xpath")
VALID_OUTPUT_FORMATS = ("json", "csv")


class ConfigError(ValueError):
    """Raised when a configuration file or value is invalid."""


def _as_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


@dataclass(slots=True)
class FieldSpec:
    """Describes how to extract one value from a page."""

    name: str
    selector: str
    selector_type: str = "auto"
    attr: str = "text"
    all: bool = False
    separator: str = " "
    strip: bool = True

    def __post_init__(self) -> None:
        self.selector_type = self.selector_type.lower()
        if self.selector_type not in VALID_SELECTOR_TYPES:
            raise ConfigError(
                f"field {self.name!r}: selector type must be one of {VALID_SELECTOR_TYPES}"
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FieldSpec:
        """Build a field from a mapping such as ``{name: title, css: h2}``."""
        name = data.get("name")
        if not name:
            raise ConfigError("each extract field requires a 'name'")
        if "css" in data:
            selector = data["css"]
            selector_type = "css"
        elif "xpath" in data:
            selector = data["xpath"]
            selector_type = "xpath"
        elif "selector" in data:
            selector = data["selector"]
            selector_type = str(data.get("type", "auto"))
        else:
            raise ConfigError(f"field {name!r} requires a 'css', 'xpath' or 'selector' key")
        return cls(
            name=str(name),
            selector=str(selector),
            selector_type=selector_type,
            attr=str(data.get("attr", "text")),
            all=_as_bool(data.get("all"), default=False),
            separator=str(data.get("separator", " ")),
            strip=_as_bool(data.get("strip"), default=True),
        )


@dataclass(slots=True)
class CrawlConfig:
    """Options controlling multi-page discovery."""

    enabled: bool = False
    max_pages: int = 50
    max_depth: int = 2
    same_domain: bool = True


@dataclass(slots=True)
class OutputConfig:
    """Where and how results are written."""

    format: str = "json"
    path: str = "out/results.json"

    def __post_init__(self) -> None:
        self.format = self.format.lower()
        if self.format not in VALID_OUTPUT_FORMATS:
            raise ConfigError(f"output format must be one of {VALID_OUTPUT_FORMATS}")


@dataclass(slots=True)
class Config:
    """Top-level configuration for a collection run."""

    concurrency: int = 8
    timeout: float = 20.0
    retries: int = 3
    backoff_factor: float = 0.5
    max_backoff: float = 30.0
    rate_limit: float = 2.0
    respect_robots: bool = True
    user_agent: str = DEFAULT_USER_AGENT
    headers: dict[str, str] = field(default_factory=dict)
    follow_redirects: bool = True
    http2: bool = False
    verify: bool = True
    extract_scope: str | None = None
    fields: list[FieldSpec] = field(default_factory=list)
    crawl: CrawlConfig = field(default_factory=CrawlConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    def __post_init__(self) -> None:
        if self.concurrency < 1:
            raise ConfigError("concurrency must be >= 1")
        if self.timeout <= 0:
            raise ConfigError("timeout must be > 0")
        if self.retries < 0:
            raise ConfigError("retries must be >= 0")
        if self.backoff_factor < 0:
            raise ConfigError("backoff_factor must be >= 0")
        if self.rate_limit < 0:
            raise ConfigError("rate_limit must be >= 0")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        """Build a configuration from a parsed YAML mapping."""
        if not isinstance(data, dict):
            raise ConfigError("configuration root must be a mapping")

        extract = data.get("extract", {}) or {}
        if not isinstance(extract, dict):
            raise ConfigError("'extract' must be a mapping")

        raw_fields = extract.get("fields", data.get("fields", [])) or []
        if not isinstance(raw_fields, list):
            raise ConfigError("'fields' must be a list")

        crawl_data = data.get("crawl", {}) or {}
        if not isinstance(crawl_data, dict):
            raise ConfigError("'crawl' must be a mapping")

        output_data = data.get("output", {}) or {}
        if not isinstance(output_data, dict):
            raise ConfigError("'output' must be a mapping")

        return cls(
            concurrency=int(data.get("concurrency", 8)),
            timeout=float(data.get("timeout", 20.0)),
            retries=int(data.get("retries", 3)),
            backoff_factor=float(data.get("backoff_factor", 0.5)),
            max_backoff=float(data.get("max_backoff", 30.0)),
            rate_limit=float(data.get("rate_limit", 2.0)),
            respect_robots=_as_bool(data.get("respect_robots"), default=True),
            user_agent=str(data.get("user_agent", DEFAULT_USER_AGENT)),
            headers={str(k): str(v) for k, v in (data.get("headers") or {}).items()},
            follow_redirects=_as_bool(data.get("follow_redirects"), default=True),
            http2=_as_bool(data.get("http2"), default=False),
            verify=_as_bool(data.get("verify"), default=True),
            extract_scope=extract.get("scope", data.get("scope")),
            fields=[FieldSpec.from_dict(item) for item in raw_fields],
            crawl=CrawlConfig(
                enabled=_as_bool(crawl_data.get("enabled"), default=False),
                max_pages=int(crawl_data.get("max_pages", 50)),
                max_depth=int(crawl_data.get("max_depth", 2)),
                same_domain=_as_bool(crawl_data.get("same_domain"), default=True),
            ),
            output=OutputConfig(
                format=str(output_data.get("format", "json")),
                path=str(output_data.get("path", "out/results.json")),
            ),
        )


def load_config(path: str | Path | None) -> Config:
    """Load configuration from ``path`` or return defaults when ``None``."""
    if path is None:
        return Config()
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"configuration file not found: {config_path}")
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        raise ConfigError(f"invalid YAML in {config_path}: {exc}") from exc
    return Config.from_dict(data or {})
