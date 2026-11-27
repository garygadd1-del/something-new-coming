"""Trader Scout collector (stub).

Reads a local JSON fixture of P&L figures. Those figures are drill numbers.
This module does not send an order, does not promise a price, and does not
contact a broker. The next wire is a file drop from the scout's own ledger
export, still with no orders from the harness.
"""

from __future__ import annotations

from pathlib import Path

from anomaly_harness.collectors.common import load_document, samples_from_json
from anomaly_harness.errors import HarnessError


def collect_trader(path: Path, bot: str, fmt: str = "auto") -> list[dict]:
    if fmt not in ("auto", "json"):
        raise HarnessError("trader collector reads a JSON fixture; it does not compute live P&L")
    if path.suffix.lower() != ".json" and fmt != "json":
        raise HarnessError("trader collector reads a JSON fixture; it does not compute live P&L")
    return samples_from_json(load_document(path), bot, "trader", path.name)
