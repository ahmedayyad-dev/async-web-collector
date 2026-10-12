"""Tests for JSON/CSV exporters."""

from __future__ import annotations

import csv
import json

from async_web_collector.exporter import export


def test_json_export(tmp_path) -> None:
    rows = [
        {"url": "https://example.com/a", "status_code": 200, "title": "العربية (UTF-8)"},
    ]
    path = export(rows, "json", tmp_path / "nested" / "out.json")
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data[0]["title"] == "العربية (UTF-8)"


def test_csv_export(tmp_path) -> None:
    rows = [
        {"url": "https://example.com/a", "status_code": 200, "tags": ["a", "b"]},
        {"url": "https://example.com/b", "status_code": 200},
    ]
    path = export(rows, "csv", tmp_path / "out.csv")
    assert path.exists()
    with path.open(encoding="utf-8", newline="") as handle:
        parsed = list(csv.DictReader(handle))
    assert len(parsed) == 2
    assert parsed[0]["url"] == "https://example.com/a"
    assert parsed[0]["tags"] == '["a", "b"]'
    assert parsed[1]["tags"] in (None, "")


def test_export_unknown_format(tmp_path) -> None:
    import pytest

    with pytest.raises(ValueError):
        export([], "xml", tmp_path / "out.xml")
