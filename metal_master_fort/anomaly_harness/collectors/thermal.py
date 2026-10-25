"""Thermal collector.

Reads a local CSV or JSON fixture. A live sensor log on selfaware can be
dropped in the same shape later. This module does not read a device, and it
does not talk to any host.
"""

from __future__ import annotations

from pathlib import Path

from anomaly_harness.collectors.common import load_document, samples_from_csv, samples_from_json
from anomaly_harness.errors import HarnessError


def collect_thermal(path: Path, bot: str, fmt: str = "auto") -> list[dict]:
    kind = fmt
    if kind == "auto":
        suffix = path.suffix.lower()
        if suffix == ".csv":
            kind = "csv"
        elif suffix == ".json":
            kind = "json"
        else:
            raise HarnessError(f"{path.name}: pass --format csv or json")
    if kind == "csv":
        return samples_from_csv(path, bot, "thermal")
    if kind == "json":
        return samples_from_json(load_document(path), bot, "thermal", path.name)
    raise HarnessError(f"unknown thermal format: {kind}")
