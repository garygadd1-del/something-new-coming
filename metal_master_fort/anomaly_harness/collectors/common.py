"""Shared fixture readers for the collectors.

A collector turns a local file into samples. It does not reach the network,
and it does not guess a reading that was not in the file.
"""

from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path

from anomaly_harness.errors import HarnessError

TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
SAMPLE_SCHEMA = "agios.metal_master.sample.v1"


def reject_remote(source: str) -> None:
    if "://" in source:
        raise HarnessError("collector source must be a local file")


def load_document(path: Path):
    reject_remote(str(path))
    if not path.is_file():
        raise HarnessError(f"no such file: {path.name}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HarnessError(
            f"invalid json in {path.name}: {exc.msg}"
        ) from exc


def check_timestamp(value, where: str) -> str:
    if not isinstance(value, str) or TIMESTAMP.fullmatch(value) is None:
        raise HarnessError(f"{where}: timestamp must look like 2026-10-25T06:00:00Z")
    return value


def check_value(value, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HarnessError(f"{where}: value is not a number")
    number = float(value)
    if not math.isfinite(number):
        raise HarnessError(f"{where}: value is not finite")
    return number


def sample(bot: str, metric: str, value: float, timestamp: str, collector: str, source: str) -> dict:
    if not isinstance(metric, str) or not metric:
        raise HarnessError("metric name is empty")
    return {
        "schema": SAMPLE_SCHEMA,
        "bot": bot,
        "metric": metric,
        "value": value,
        "timestamp": timestamp,
        "collector": collector,
        "source": source,
    }


def require_bot(found: str, expected: str, where: str) -> None:
    if found != expected:
        raise HarnessError(f"{where}: sample bot is {found}, collect asked for {expected}")


def samples_from_json(document, bot: str, collector: str, source_name: str) -> list[dict]:
    if isinstance(document, list):
        items = document
    elif isinstance(document, dict) and isinstance(document.get("samples"), list):
        items = []
        for item in document["samples"]:
            if isinstance(item, dict) and "bot" not in item and "bot" in document:
                item = dict(item)
                item["bot"] = document["bot"]
            items.append(item)
    elif isinstance(document, dict) and "readings" in document:
        items = [document]
    else:
        raise HarnessError(
            f"{source_name}: JSON must be a sample list, a readings object, or a samples object"
        )
    rows: list[dict] = []
    for index, item in enumerate(items):
        rows.extend(_one_json_item(item, bot, collector, source_name, index))
    if not rows:
        raise HarnessError(f"{source_name}: no samples")
    return rows


def _one_json_item(item, bot: str, collector: str, source_name: str, index: int) -> list[dict]:
    where = f"{source_name}[{index}]"
    if not isinstance(item, dict):
        raise HarnessError(f"{where}: sample is not an object")
    found_bot = item.get("bot", bot)
    if not isinstance(found_bot, str):
        raise HarnessError(f"{where}: bot is not a string")
    require_bot(found_bot, bot, where)
    if "readings" in item:
        timestamp = check_timestamp(item.get("timestamp"), where)
        readings = item["readings"]
        if not isinstance(readings, dict) or not readings:
            raise HarnessError(f"{where}: readings must be a non-empty object")
        out = []
        for metric, value in readings.items():
            out.append(
                sample(
                    bot,
                    metric,
                    check_value(value, f"{where}.{metric}"),
                    timestamp,
                    collector,
                    source_name,
                )
            )
        return out
    timestamp = check_timestamp(item.get("timestamp"), where)
    metric = item.get("metric")
    if not isinstance(metric, str):
        raise HarnessError(f"{where}: metric is missing")
    return [
        sample(
            bot,
            metric,
            check_value(item.get("value"), where),
            timestamp,
            collector,
            source_name,
        )
    ]


def samples_from_csv(path: Path, bot: str, collector: str) -> list[dict]:
    reject_remote(str(path))
    if not path.is_file():
        raise HarnessError(f"no such file: {path.name}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HarnessError(f"cannot read {path.name}: {exc.strerror}") from exc
    reader = csv.DictReader(line for line in text.splitlines() if line.strip())
    if reader.fieldnames is None:
        raise HarnessError(f"{path.name}: CSV header is missing")
    fields = [name.strip() for name in reader.fieldnames]
    needed = {"timestamp", "bot", "metric", "value"}
    if not needed.issubset(set(fields)):
        raise HarnessError(f"{path.name}: CSV header must include timestamp,bot,metric,value")
    rows = []
    for index, raw in enumerate(reader, start=1):
        item = {key.strip(): (value.strip() if isinstance(value, str) else value) for key, value in raw.items() if key}
        where = f"{path.name}:{index}"
        found = item.get("bot") or ""
        require_bot(found, bot, where)
        try:
            value = float(item.get("value", ""))
        except (TypeError, ValueError) as exc:
            raise HarnessError(f"{where}: value is not a number") from exc
        rows.append(
            sample(
                bot,
                item.get("metric") or "",
                check_value(value, where),
                check_timestamp(item.get("timestamp"), where),
                collector,
                path.name,
            )
        )
    if not rows:
        raise HarnessError(f"{path.name}: no samples")
    return rows
