"""Medic bot stub.

Classifies one error as a crash, a config typo, or a real bug.
A config typo with a close field name gets an in-memory rename proposal.
Nothing here writes a config file. Escalated tickets are for the morning
digest. No ticket is forwarded to the anomaly harness: that is the snowball stop.
"""

from __future__ import annotations

import copy
import re

from medic_bot.errors import MedicError

TICKET_SCHEMA = "agios.metal_master.triage_ticket.v1"
INCIDENT_SCHEMA = "agios.metal_master.incident.v1"

KNOWN_FIELDS = (
    "core_c",
    "hotspot_c",
    "pnl_usd",
    "uptime_ratio",
    "bot",
    "metric",
    "value",
    "timestamp",
    "host",
    "lane",
    "schema",
    "warn",
    "direction",
    "baseline",
    "policy",
)

CRASH_EXITS = {134, 136, 137, 139}
CRASH_TYPES = {"MemoryError", "RecursionError", "SystemError"}
CRASH_MSG = re.compile(r"segmentation fault|abort trap|stack overflow|\bpanic\b", re.IGNORECASE)
CONFIG_TYPES = {
    "JSONDecodeError",
    "json.decoder.JSONDecodeError",
    "json.JSONDecodeError",
    "KeyError",
    "FileNotFoundError",
}
CONFIG_MSG = re.compile(
    r"unknown (?:metric|field|key)|invalid json|expecting value|did you mean|no such file",
    re.IGNORECASE,
)
BUG_TYPES = {"AssertionError", "NotImplementedError"}
BUG_MSG = re.compile(r"\bassertion\b|\breal bug\b", re.IGNORECASE)
FIELD_TOKEN = re.compile(
    r"unknown (?:metric|field|key) ['\"]?([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


def triage(report: dict) -> dict:
    if not isinstance(report, dict):
        raise MedicError("error report must be an object")
    bot = report.get("bot")
    if not isinstance(bot, str) or not bot.strip():
        raise MedicError("error report is missing bot")
    lane = report.get("lane") or "untied"
    if not isinstance(lane, str):
        raise MedicError("lane must be a string")
    message = str(report.get("message") or "")
    exception_type = str(report.get("exception_type") or "")
    exit_code = report.get("exit_code")
    kind = _classify(message, exception_type, exit_code)
    patch = _propose(kind, message)
    closed_here = patch is not None
    summary = _summary(kind, message)
    return {
        "schema": TICKET_SCHEMA,
        "bot": bot,
        "lane": lane,
        "class": kind,
        "summary": summary,
        "patch": patch,
        "escalate": not closed_here,
        "forward_to_harness": False,
        "closed_here": closed_here,
        "stops_snowball": True,
    }


def apply_proposal(document: dict, patch: dict) -> dict:
    """Return a renamed copy. This stub does not write the copy anywhere."""
    if not isinstance(patch, dict) or patch.get("op") != "rename_key":
        raise MedicError("only a rename_key patch can be applied in this stub")
    root = copy.deepcopy(document)
    path = patch.get("path") or []
    if not isinstance(path, list):
        raise MedicError("patch path must be a list")
    node = root
    for key in path:
        if not isinstance(node, dict) or key not in node:
            raise MedicError("patch path does not exist")
        node = node[key]
    src = patch.get("from")
    dst = patch.get("to")
    if not isinstance(node, dict) or src not in node:
        raise MedicError("from key is missing")
    if dst in node:
        raise MedicError("to key already exists")
    rebuilt = {}
    for key, value in node.items():
        rebuilt[dst if key == src else key] = value
    if not path:
        return rebuilt
    parent = root
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = rebuilt
    return root


def incident_from_ticket(ticket: dict, morning: str) -> dict:
    return {
        "schema": INCIDENT_SCHEMA,
        "morning": morning,
        "bot": ticket["bot"],
        "lane": ticket["lane"],
        "class": ticket["class"],
        "summary": ticket["summary"],
    }


def _classify(message: str, exception_type: str, exit_code) -> str:
    if exit_code in CRASH_EXITS or CRASH_MSG.search(message):
        return "crash"
    config = exception_type in CONFIG_TYPES or CONFIG_MSG.search(message) or "mask_guard" in message
    if config or message.startswith("REROUTE"):
        return "config_typo"
    if exception_type in BUG_TYPES or BUG_MSG.search(message):
        return "real_bug"
    if exception_type in CRASH_TYPES:
        return "crash"
    return "unknown"


def _propose(kind: str, message: str) -> dict | None:
    if kind != "config_typo":
        return None
    found = FIELD_TOKEN.search(message)
    if found is None:
        return None
    token = found.group(1)
    target = suggest_field(token)
    if target is None:
        return None
    return {
        "op": "rename_key",
        "path": [],
        "from": token,
        "to": target,
        "reason": f"close to known field {target}",
    }


def suggest_field(token: str) -> str | None:
    folded = token.replace("_", "").lower()
    normalized = [field for field in KNOWN_FIELDS if field.replace("_", "").lower() == folded]
    if len(normalized) == 1 and normalized[0] != token:
        return normalized[0]
    close = []
    for field in KNOWN_FIELDS:
        field_folded = field.replace("_", "").lower()
        if field_folded == folded:
            continue
        if field_folded.startswith(folded) or folded.startswith(field_folded):
            if abs(len(field_folded) - len(folded)) <= 2:
                close.append(field)
    if len(close) == 1:
        return close[0]
    return None


def _summary(kind: str, message: str) -> str:
    text = " ".join(message.split())
    if len(text) > 240:
        text = text[:237] + "..."
    if not text:
        return kind
    return f"{kind}: {text}"
