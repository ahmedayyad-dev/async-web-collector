"""Tests for configuration parsing and validation."""

from __future__ import annotations

import pytest

from async_web_collector.config import Config, ConfigError, FieldSpec, load_config


def test_defaults() -> None:
    config = Config()
    assert config.concurrency == 8
    assert config.rate_limit == 2.0
    assert config.respect_robots is True
    assert config.crawl.enabled is False
    assert config.output.format == "json"


def test_load_config(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
concurrency: 3
rate_limit: 0
extract:
  scope: article
  fields:
    - {name: title, css: "h2"}
output:
  format: csv
  path: out/data.csv
""",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.concurrency == 3
    assert config.rate_limit == 0.0
    assert config.extract_scope == "article"
    assert config.fields == [FieldSpec(name="title", selector="h2", selector_type="css")]
    assert config.output.format == "csv"
    assert config.output.path == "out/data.csv"


def test_field_xpath_selector() -> None:
    field = FieldSpec.from_dict({"name": "sku", "xpath": ".//span/@data-sku"})
    assert field.selector == ".//span/@data-sku"
    assert field.selector_type == "xpath"


def test_field_missing_name() -> None:
    with pytest.raises(ConfigError):
        FieldSpec.from_dict({"css": "h1"})


def test_field_missing_selector() -> None:
    with pytest.raises(ConfigError):
        FieldSpec.from_dict({"name": "title"})


def test_invalid_rate_limit() -> None:
    with pytest.raises(ConfigError):
        Config.from_dict({"rate_limit": -1})


def test_invalid_output_format() -> None:
    with pytest.raises(ConfigError):
        Config.from_dict({"output": {"format": "xml"}})


def test_missing_config_file() -> None:
    with pytest.raises(ConfigError):
        load_config("does/not/exist.yaml")


def test_auto_selector_type() -> None:
    assert FieldSpec(name="a", selector="/html/body").selector_type == "auto"
    config = Config(fields=[FieldSpec(name="a", selector="//h1")])
    assert config.fields[0].selector_type == "auto"
