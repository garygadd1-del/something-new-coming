"""Apply a role mask to the shared brain.

A mask strips parameters and may upgrade the ones it kept, including a
deeper upgrade for one job. It does not add a parameter that was stripped.
Little masks (the librarian is the one marked emergent) leave more of the
shift unspecified on purpose. That unspecified part stays inside the kept
parameters.

The Rust wrapper is the second check. Call ``commit_mask`` so a file that
goes sideways after this loader still reroutes before a task uses it.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BRAIN_SCHEMA = "agios.metal_master.brain.v1"
MASK_SCHEMA = "agios.metal_master.mask.v1"
OUT_SCHEMA = "agios.metal_master.masked_brain.v1"
SLUG = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class MaskError(ValueError):
    """The mask or the brain is not usable. The task should stop."""


def load_brain(path: Path | None = None) -> dict:
    return _read(path or ROOT / "brain.json", "brain")


def load_mask(role: str, path: Path | None = None) -> dict:
    if not SLUG.fullmatch(role or ""):
        raise MaskError(f"unknown role {role}")
    return _read(path or ROOT / "masks" / f"{role}.json", "mask")


def apply_mask(brain: dict, mask: dict, job: str | None = None) -> dict:
    """Return a new masked brain. ``brain`` and ``mask`` are not modified."""
    if brain.get("schema") != BRAIN_SCHEMA:
        raise MaskError("brain schema is wrong")
    if mask.get("schema") != MASK_SCHEMA:
        raise MaskError("mask schema is wrong")
    role = mask.get("role")
    if not isinstance(role, str) or SLUG.fullmatch(role) is None:
        raise MaskError("mask role is not a slug")
    brain_id = brain.get("id")
    if not isinstance(brain_id, str) or SLUG.fullmatch(brain_id) is None:
        raise MaskError("brain id is not a slug")
    parameters = brain.get("parameters")
    if not isinstance(parameters, dict) or not parameters:
        raise MaskError("brain parameters are missing")

    keep = _slug_list(mask.get("keep"), "keep")
    strip = _slug_list(mask.get("strip"), "strip")
    jobs = _slug_list(mask.get("jobs"), "jobs")
    if set(keep) & set(strip):
        raise MaskError("keep and strip overlap")
    if set(keep) | set(strip) != set(parameters):
        raise MaskError("mask must account for every brain parameter")
    if not keep:
        raise MaskError("mask keeps nothing")
    if not isinstance(mask.get("emergent"), bool):
        raise MaskError("emergent must be a boolean")
    if job is not None and job not in jobs:
        raise MaskError(f"job {job} is not assigned to {role}")

    per_job = mask.get("per_job") or {}
    if not isinstance(per_job, dict):
        raise MaskError("per_job must be an object")
    for name in per_job:
        if name not in jobs:
            raise MaskError(f"per_job {name} is not an assigned job")

    kept = {name: copy.deepcopy(parameters[name]) for name in keep}
    _merge_top(kept, mask.get("upgrade") or {}, keep)
    if job is not None:
        block = per_job.get(job) or {}
        if not isinstance(block, dict):
            raise MaskError("per_job entry must be an object")
        _merge_top(kept, block.get("upgrade") or {}, keep)
    _assert_house_rules(kept)

    return {
        "schema": OUT_SCHEMA,
        "brain_id": brain_id,
        "role": role,
        "job": job,
        "emergent": mask["emergent"],
        "jobs": list(jobs),
        "stripped": sorted(strip),
        "parameters": kept,
    }


def _merge_top(kept: dict, upgrade: dict, keep: list[str]) -> None:
    if not isinstance(upgrade, dict):
        raise MaskError("upgrade must be an object")
    for key in upgrade:
        if key not in keep:
            raise MaskError(f"upgrade adds parameter {key}")
        if not isinstance(upgrade[key], dict):
            raise MaskError(f"upgrade for {key} must be an object")
        _merge_into(kept[key], upgrade[key], key)


def _merge_into(param: dict, upgrade: dict, trail: str) -> None:
    if not isinstance(param, dict):
        raise MaskError(f"{trail} is not an object")
    for key, value in upgrade.items():
        if not isinstance(key, str) or KEY.fullmatch(key) is None:
            raise MaskError(f"bad upgrade key at {trail}")
        if isinstance(param.get(key), dict) and isinstance(value, dict):
            _merge_into(param[key], value, f"{trail}.{key}")
        else:
            param[key] = copy.deepcopy(value)


def _assert_house_rules(node) -> None:
    if isinstance(node, dict):
        if "doctrine" in node and node["doctrine"] != "defense_only":
            raise MaskError("doctrine must be defense_only")
        if "leader_voice" in node and node["leader_voice"] != "when_called":
            raise MaskError("leader_voice must be when_called")
        if "enabled" in node and not isinstance(node["enabled"], bool):
            raise MaskError("enabled must be a boolean")
        if "scope" in node and node["scope"] not in ("house", "house_only", "lane"):
            raise MaskError("scope is not a house scope")
        for value in node.values():
            _assert_house_rules(value)
    elif isinstance(node, list):
        for value in node:
            _assert_house_rules(value)


def _slug_list(value, label: str) -> list[str]:
    if not isinstance(value, list):
        raise MaskError(f"{label} must be a list")
    slugs = []
    for item in value:
        if not isinstance(item, str) or SLUG.fullmatch(item) is None:
            raise MaskError(f"{label} entry is not a slug")
        slugs.append(item)
    return slugs


def _read(path: Path, label: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MaskError(f"cannot read {label}: {path.name}") from exc
    if not isinstance(data, dict):
        raise MaskError(f"{label} must be an object")
    return data
