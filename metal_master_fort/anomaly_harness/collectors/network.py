"""Network Master collector (stub).

Reads a local JSON fixture that already contains an uptime ratio. This module
does not open a socket, does not ping, and does not scan. The next wire is a
file drop of a ratio the network master computed for itself.
"""

from __future__ import annotations

from pathlib import Path

from anomaly_harness.collectors.common import load_document, samples_from_json
from anomaly_harness.errors import HarnessError


def collect_network(path: Path, bot: str, fmt: str = "auto") -> list[dict]:
    if fmt not in ("auto", "json"):
        raise HarnessError("network collector reads a JSON fixture; it does not scan")
    if path.suffix.lower() != ".json" and fmt != "json":
        raise HarnessError("network collector reads a JSON fixture; it does not scan")
    return samples_from_json(load_document(path), bot, "network", path.name)
