"""Smoke for the medic, the morning digest, and the game-world roster."""

import json
import subprocess
from pathlib import Path

import pytest

from daily_standup.digest import (
    APPROVAL_NOTE,
    build_digest,
    load_incidents,
    log_incident,
    render_markdown,
)
from daily_standup.__main__ import main as digest_main
from game_world.__main__ import main as world_main
from game_world.world import (
    WorldError,
    clock_in,
    clock_out,
    display_name,
    expand_jobs,
    load_spec,
    make_roster,
    pick_name,
    rotate,
)
from house_policy import (
    FUZZY_CHEAP_PASS_CORE_C,
    FUZZY_CHEAP_PASS_HOTSPOT_C,
    XTX_CORE_C,
    XTX_HOTSPOT_C,
)
from medic_bot.__main__ import main as medic_main
from medic_bot.triage import apply_proposal, incident_from_ticket, triage

ROOT = Path(__file__).resolve().parents[1]
TICKET_SCHEMA = json.loads(
    (ROOT / "medic_bot" / "schema" / "triage_ticket.schema.json").read_text(encoding="utf-8")
)
DIGEST_SCHEMA = json.loads(
    (ROOT / "daily_standup" / "schema" / "digest.schema.json").read_text(encoding="utf-8")
)
JOB_SCHEMA = json.loads((ROOT / "game_world" / "schema" / "job.schema.json").read_text(encoding="utf-8"))


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_medic_sorts_typo_crash_and_real_bug():
    typo = triage(_load(ROOT / "medic_bot" / "fixtures" / "config_typo.json"))
    crash = triage(_load(ROOT / "medic_bot" / "fixtures" / "crash.json"))
    bug = triage(_load(ROOT / "medic_bot" / "fixtures" / "real_bug.json"))
    for ticket in (typo, crash, bug):
        for key in TICKET_SCHEMA["required"]:
            assert key in ticket
        assert ticket["forward_to_harness"] is False
        assert ticket["stops_snowball"] is True
    assert typo["class"] == "config_typo"
    assert typo["closed_here"] is True
    assert typo["escalate"] is False
    assert typo["patch"]["to"] == "core_c"
    renamed = apply_proposal({"coreC": 81, "hotspot_c": 70}, typo["patch"])
    assert renamed == {"core_c": 81, "hotspot_c": 70}
    assert crash["class"] == "crash"
    assert crash["escalate"] is True
    assert crash["patch"] is None
    assert bug["class"] == "real_bug"
    assert bug["escalate"] is True
    assert bug["closed_here"] is False
    rerouted = triage(
        {
            "bot": "warrior",
            "lane": "defense",
            "message": "mask_guard: doctrine must be defense_only",
        }
    )
    assert rerouted["class"] == "config_typo"
    assert rerouted["patch"] is None
    assert rerouted["escalate"] is True
    assert rerouted["forward_to_harness"] is False


def test_digest_is_lane_tied_and_does_not_grant_approval(tmp_path):
    cards = _load(ROOT / "daily_standup" / "fixtures" / "cards.json")
    roll = _load(ROOT / "daily_standup" / "fixtures" / "roll_call.json")
    incidents = load_incidents(ROOT / "daily_standup" / "fixtures" / "incidents.jsonl")
    digest = build_digest(cards, roll, incidents)
    for key in DIGEST_SCHEMA["required"]:
        assert key in digest
    assert digest["morning"] == "2026-10-25"
    assert digest["present"] == ["fuzzy66_thermal", "thermal_gate", "trader_scout"]
    assert digest["absent"] == ["network_master"]
    assert digest["incomplete"] == ["trader_scout"]
    assert digest["approval_gate"]["grants"] == []
    assert digest["approval_gate"]["note"] == APPROVAL_NOTE
    assert set(digest["lanes"]) == {"thermal", "trader"}
    text = render_markdown(digest)
    assert "Approval Gate:" in text
    assert "grants: none" in text
    assert "network_master" in text
    roll["approval_gate"]["grants"] = ["not-a-real-grant"]
    shown = build_digest(cards, roll, [])
    assert shown["approval_gate"]["grants"] == ["not-a-real-grant"]
    shown["approval_gate"]["grants"].append("added-by-caller")
    assert roll["approval_gate"]["grants"] == ["not-a-real-grant"]
    ticket = triage(_load(ROOT / "medic_bot" / "fixtures" / "crash.json"))
    incident = incident_from_ticket(ticket, "2026-10-25")
    path = tmp_path / "incidents.jsonl"
    log_incident(path, incident)
    logged = load_incidents(path)
    assert logged[0]["class"] == "crash"
    assert "segmentation fault" in logged[0]["summary"]


def test_roster_leaves_names_blank_and_rotates_hats():
    spec = load_spec()
    jobs = expand_jobs(spec)
    roster = make_roster(spec)
    blanks = [job for job in jobs if job["blank"]]
    filled = [job for job in jobs if not job["blank"]]
    assert len(spec["trades"]) == 11
    assert len(spec["streets"]) == 15
    assert len(spec["shifts"]) == 5
    assert len(filled) == 11 * 15 * 5
    assert len(filled) >= 200
    assert len(blanks) == 24
    assert len(roster) == 50
    assert all(bot["real_name"] is None and bot["street_name"] is None for bot in roster)
    assert all(bot["name_picked"] is False and bot["clocked_in"] is False for bot in roster)
    for key in JOB_SCHEMA["required"]:
        assert key in jobs[0]
        assert key in blanks[0]
    assert blanks[0]["trade"] is None

    bot = roster[0]
    with pytest.raises(WorldError, match="will not invent"):
        pick_name(bot)
    street_only = pick_name(bot, street_name="Kiln Wren")
    assert display_name(street_only) == "bot-01"
    assert display_name(clock_in(street_only)) == "Kiln Wren"
    named = pick_name(bot, street_name="Kiln Wren", real_name="Quarry Ada")
    assert display_name(named) == "Quarry Ada"
    assert display_name(clock_in(named)) == "Kiln Wren"
    assert display_name(clock_out(clock_in(named))) == "Quarry Ada"
    with pytest.raises(WorldError):
        clock_in(bot)

    day0 = rotate(roster, jobs, 0)
    day1 = rotate(roster, jobs, 1)
    assert day0["blank_jobs"] == 24
    assert len(day0["assignments"]) == 50 * 3
    assert day0["open_jobs"] == len(filled) - len(day0["assignments"])
    ids = [row["job_id"] for row in day0["assignments"]]
    assert len(ids) == len(set(ids))
    assert all(not job_id.startswith("blank.") for job_id in ids)
    for bot_id, hats in day0["hats_by_bot"].items():
        assert len(hats) == 3
        assert len(set(hats)) == 3
    first0 = next(row["job_id"] for row in day0["assignments"] if row["bot"] == "bot-01")
    first1 = next(row["job_id"] for row in day1["assignments"] if row["bot"] == "bot-01")
    assert first0 != first1


def test_c_scheduler_gives_game_dev_thermal_slots(tmp_path):
    source = (ROOT / "game_world" / "schedule.c").read_text(encoding="utf-8")
    assert f"#define XTX_CORE_C {XTX_CORE_C}" in source
    assert f"#define XTX_HOTSPOT_C {XTX_HOTSPOT_C}" in source
    assert f"#define FUZZY_CORE_C {FUZZY_CHEAP_PASS_CORE_C}" in source
    assert f"#define FUZZY_HOTSPOT_C {FUZZY_CHEAP_PASS_HOTSPOT_C}" in source
    binary = tmp_path / "schedule"
    subprocess.check_call(
        ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(binary), str(ROOT / "game_world" / "schedule.c")]
    )
    fixtures = ROOT / "game_world" / "fixtures"

    def schedule(name: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(binary), str(fixtures / name)],
            check=False,
            capture_output=True,
            text=True,
        )

    now = schedule("rendering_now.txt")
    assert now.returncode == 0, now.stdout
    assert "minutes=40" in now.stdout
    assert "window=thermal_selfaware" in now.stdout
    assert "note=rx7900xtx_core80_hotspot88" in now.stdout
    assert "minutes=20" in now.stdout
    assert "window=cheap_pass" in now.stdout
    assert "note=rx6600_cheap_pass_core70_hotspot80" in now.stdout
    assert "role=mayor" in now.stdout and "minutes=30" in now.stdout
    assert "SUMMARY ok=3 reroute=0" in now.stdout

    loose = schedule("loosened_ceiling.txt")
    assert loose.returncode == 2
    assert "cannot loosen" in loose.stdout
    assert "OK " not in loose.stdout

    outside = schedule("outside_swarm.txt")
    assert outside.returncode == 2
    assert "outside the swarm" in outside.stdout

    tailor = schedule("tailor_rendering.txt")
    assert tailor.returncode == 2
    assert "game_dev only" in tailor.stdout

    mixed = schedule("mixed.txt")
    assert mixed.returncode == 3
    assert mixed.stdout.count("OK ") == 1
    assert "game_dev only" in mixed.stdout

    tight = tmp_path / "tight.txt"
    tight.write_text(
        "thermal selfaware 75 80 primary\nbot bot-07 game_dev rendering selfaware\n",
        encoding="utf-8",
    )
    tightened = subprocess.run([str(binary), str(tight)], check=False, capture_output=True, text=True)
    assert tightened.returncode == 0, tightened.stdout
    assert "note=rx7900xtx_core75_hotspot80" in tightened.stdout


def test_stub_entrypoints_run():
    assert medic_main([]) == 0
    assert digest_main([]) == 0
    assert world_main([]) == 0
