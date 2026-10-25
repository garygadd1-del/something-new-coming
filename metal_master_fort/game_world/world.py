"""Game-world job roster.

Hundreds of shift jobs come from trades × streets × shifts. Blank seats stay
blank. A bot's street name is used on shift. A bot's real name is used when
clocked out. This scaffold does not invent either name: the bot picks them.

The 3D world these jobs belong to, and any robot body that would enter Gary's
world, are not built here. See rust_wrappers/LANGUAGES.md.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME_LIMIT = 48


class WorldError(ValueError):
    """A job, a name, or a roster row is not usable."""


def load_spec(path: Path | None = None) -> dict:
    spec_path = path or ROOT / "jobs_spec.json"
    data = json.loads(spec_path.read_text(encoding="utf-8"))
    if data.get("schema") != "agios.metal_master.jobs_spec.v1":
        raise WorldError("jobs spec schema is wrong")
    return data


def slug(text: str) -> str:
    parts = []
    for char in text.lower():
        if char.isascii() and char.isalnum():
            parts.append(char)
        elif char in " -_":
            parts.append("_")
    collapsed = re.sub(r"_+", "_", "".join(parts)).strip("_")
    if not collapsed:
        raise WorldError("street slug is empty")
    return collapsed


def expand_jobs(spec: dict | None = None) -> list[dict]:
    spec = spec or load_spec()
    jobs = []
    for trade in spec["trades"]:
        for street in spec["streets"]:
            for shift in spec["shifts"]:
                jobs.append(
                    {
                        "schema": "agios.metal_master.job.v1",
                        "id": f"{trade['id']}.{slug(street)}.{shift}",
                        "trade": trade["id"],
                        "title": trade["title"],
                        "street_name": f"{street} {shift} {trade['title']}",
                        "street": street,
                        "shift": shift,
                        "seats": 1,
                        "assigned": [],
                        "blank": False,
                    }
                )
    for index in range(1, int(spec["blank_seats"]) + 1):
        jobs.append(
            {
                "schema": "agios.metal_master.job.v1",
                "id": f"blank.{index:03d}",
                "trade": None,
                "title": None,
                "street_name": None,
                "street": None,
                "shift": None,
                "seats": 1,
                "assigned": [],
                "blank": True,
            }
        )
    return jobs


def make_roster(spec: dict | None = None) -> list[dict]:
    spec = spec or load_spec()
    hats = int(spec["max_hats"])
    roster = []
    for index in range(1, int(spec["bot_count"]) + 1):
        roster.append(
            {
                "schema": "agios.metal_master.bot.v1",
                "id": f"bot-{index:02d}",
                "real_name": None,
                "street_name": None,
                "name_picked": False,
                "clocked_in": False,
                "hats": [],
                "max_hats": hats,
            }
        )
    return roster


def pick_name(bot: dict, *, real_name: str | None = None, street_name: str | None = None) -> dict:
    """Record a name the bot chose. Refuses to invent one."""
    if real_name is None and street_name is None:
        raise WorldError("the bot picks the name; the scaffold will not invent one")
    updated = copy.deepcopy(bot)
    if real_name is not None:
        _check_name(real_name)
        updated["real_name"] = real_name
    if street_name is not None:
        _check_name(street_name)
        updated["street_name"] = street_name
    updated["name_picked"] = bool(updated.get("real_name") or updated.get("street_name"))
    return updated


def clock_in(bot: dict) -> dict:
    updated = copy.deepcopy(bot)
    if not updated.get("street_name"):
        raise WorldError("clock-in uses a street name; this bot has not picked one")
    updated["clocked_in"] = True
    return updated


def clock_out(bot: dict) -> dict:
    updated = copy.deepcopy(bot)
    updated["clocked_in"] = False
    return updated


def display_name(bot: dict) -> str:
    """Street name on shift. Real name when clocked out. Id if that name is still blank."""
    if bot.get("clocked_in"):
        return bot.get("street_name") or bot["id"]
    if bot.get("real_name"):
        return bot["real_name"]
    return bot["id"]


def rotate(bots: list[dict], jobs: list[dict], day_index: int) -> dict:
    """Assign up to max_hats distinct trades per bot. Blank jobs stay open.

    The day index rotates which job is first. A job is used once per day.
    """
    if day_index < 0:
        raise WorldError("day_index must be >= 0")
    assignable = [job for job in jobs if not job["blank"]]
    if not assignable:
        raise WorldError("no jobs to rotate")
    offset = day_index % len(assignable)
    ordered = assignable[offset:] + assignable[:offset]
    hat_count = {bot["id"]: 0 for bot in bots}
    trades = {bot["id"]: set() for bot in bots}
    max_hats = {bot["id"]: int(bot["max_hats"]) for bot in bots}
    bot_ids = [bot["id"] for bot in bots]
    assignments = []
    next_bot = 0
    for job in ordered:
        if bot_ids and all(hat_count[bot_id] >= max_hats[bot_id] for bot_id in bot_ids):
            break
        for look in range(len(bot_ids)):
            bot_id = bot_ids[(next_bot + look) % len(bot_ids)]
            if hat_count[bot_id] >= max_hats[bot_id]:
                continue
            if job["trade"] in trades[bot_id]:
                continue
            trades[bot_id].add(job["trade"])
            hat_count[bot_id] += 1
            assignments.append(
                {
                    "bot": bot_id,
                    "job_id": job["id"],
                    "trade": job["trade"],
                    "street_name": job["street_name"],
                }
            )
            next_bot = (bot_ids.index(bot_id) + 1) % len(bot_ids)
            break
    hats_by_bot = {bot_id: sorted(names) for bot_id, names in trades.items()}
    return {
        "schema": "agios.metal_master.rotation.v1",
        "day_index": day_index,
        "assignments": assignments,
        "blank_jobs": sum(1 for job in jobs if job["blank"]),
        "open_jobs": len(assignable) - len(assignments),
        "hats_by_bot": hats_by_bot,
    }


def _check_name(name: str) -> None:
    if not isinstance(name, str) or not name.strip():
        raise WorldError("empty name")
    if name != name.strip() or len(name) > NAME_LIMIT:
        raise WorldError("name refused")
    if "://" in name or any(ord(char) < 32 for char in name):
        raise WorldError("name refused")
