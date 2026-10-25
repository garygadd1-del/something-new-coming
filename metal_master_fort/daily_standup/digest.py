"""Daily standup stub.

Each bot card answers three things, tied to a lane: goal hit, problem solved,
thing improved. Roll call records who is present. Presence is not an Approval
Gate grant. Incidents are listed; this module does not close them.
"""

from __future__ import annotations

APPROVAL_NOTE = (
    "Presence is not approval. The Approval Gate is a human door. "
    "A bot marked present has answered roll call. "
    "It has not been granted a human-gate action."
)

ANSWERS = ("goal_hit", "problem_solved", "thing_improved")


class DigestError(ValueError):
    """The cards or the roll call are not usable."""


def build_digest(cards, roll_call, incidents, morning: str | None = None) -> dict:
    if not isinstance(roll_call, dict):
        raise DigestError("roll call must be an object")
    roster = roll_call.get("roster")
    if not isinstance(roster, list) or not roster:
        raise DigestError("roll call roster is missing")
    day = morning or roll_call.get("morning")
    if not isinstance(day, str) or not day.strip():
        raise DigestError("morning is missing")
    gate = roll_call.get("approval_gate") if isinstance(roll_call.get("approval_gate"), dict) else {}
    note = gate.get("note") or APPROVAL_NOTE
    grants = list(gate.get("grants") or [])
    by_bot = {}
    for entry in roster:
        if not isinstance(entry, dict) or not entry.get("bot"):
            raise DigestError("roster entry is missing bot")
        by_bot[entry["bot"]] = entry
    present = sorted(entry["bot"] for entry in roster if entry.get("present"))
    absent = sorted(entry["bot"] for entry in roster if not entry.get("present"))
    lanes: dict[str, list] = {}
    incomplete = []
    off_roster = []
    answered_while_absent = []
    seen = set()
    for card in cards:
        if not isinstance(card, dict) or not card.get("bot"):
            raise DigestError("card is missing bot")
        bot = card["bot"]
        seen.add(bot)
        lane = card.get("lane") or "untied"
        if not isinstance(lane, str) or not lane.strip():
            lane = "untied"
        entry = by_bot.get(bot)
        if entry is None:
            off_roster.append(bot)
        elif not entry.get("present"):
            answered_while_absent.append(bot)
        complete = all(str(card.get(field) or "").strip() for field in ANSWERS)
        if not complete:
            incomplete.append(bot)
        lanes.setdefault(lane, []).append(
            {
                "bot": bot,
                "goal_hit": card.get("goal_hit") or "",
                "problem_solved": card.get("problem_solved") or "",
                "thing_improved": card.get("thing_improved") or "",
                "complete": complete,
            }
        )
    for bot in present:
        if bot not in seen:
            incomplete.append(bot)
    for lane in lanes:
        lanes[lane] = sorted(lanes[lane], key=lambda row: row["bot"])
    return {
        "schema": "agios.metal_master.digest.v1",
        "morning": day,
        "approval_gate": {"note": note, "grants": grants},
        "present": present,
        "absent": absent,
        "lanes": {lane: lanes[lane] for lane in sorted(lanes)},
        "incomplete": sorted(set(incomplete)),
        "off_roster": sorted(off_roster),
        "answered_while_absent": sorted(answered_while_absent),
        "incidents": list(incidents),
    }


def render_markdown(digest: dict) -> str:
    gate = digest["approval_gate"]
    grants = gate["grants"]
    grant_line = "grants: none" if not grants else "grants recorded: " + ", ".join(str(item) for item in grants)
    lines = [
        f"# Morning digest {digest['morning']}",
        "",
        "## Roll call",
        "present: " + (", ".join(digest["present"]) if digest["present"] else "none"),
        "absent: " + (", ".join(digest["absent"]) if digest["absent"] else "none"),
        f"Approval Gate: {gate['note']}",
        grant_line,
        "",
        "## Lanes",
    ]
    if not digest["lanes"]:
        lines.append("No cards.")
    for lane, rows in digest["lanes"].items():
        lines.append(f"### {lane}")
        for row in rows:
            mark = "complete" if row["complete"] else "incomplete"
            lines.append(
                f"- {row['bot']} ({mark}): "
                f"goal hit: {row['goal_hit'] or '—'}; "
                f"problem solved: {row['problem_solved'] or '—'}; "
                f"thing improved: {row['thing_improved'] or '—'}"
            )
    if digest["incomplete"]:
        lines.append("")
        lines.append("incomplete: " + ", ".join(digest["incomplete"]))
    lines.append("")
    lines.append("## Incidents")
    if not digest["incidents"]:
        lines.append("none")
    for incident in digest["incidents"]:
        lines.append(
            f"- {incident.get('bot')} [{incident.get('class')}]: {incident.get('summary')}"
        )
    return "\n".join(lines) + "\n"


def log_incident(path, incident: dict) -> None:
    import json
    from pathlib import Path

    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(incident) + "\n")


def load_incidents(path) -> list[dict]:
    import json
    from pathlib import Path

    dest = Path(path)
    if not dest.exists():
        return []
    rows = []
    for line in dest.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows
