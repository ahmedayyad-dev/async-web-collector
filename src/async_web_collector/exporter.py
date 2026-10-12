"""Result exporters for JSON and CSV."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def _serialize_cell(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


def export(rows: list[dict[str, Any]], fmt: str, path: str | Path) -> Path:
    """Write ``rows`` to ``path`` as ``json`` or ``csv`` and return the path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fmt = fmt.lower()
    if fmt == "json":
        _export_json(rows, target)
    elif fmt == "csv":
        _export_csv(rows, target)
    else:
        raise ValueError(f"unsupported export format: {fmt!r}")
    return target


def _export_json(rows: list[dict[str, Any]], path: Path) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _export_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        if not fieldnames:
            return
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _serialize_cell(value) for key, value in row.items()})
