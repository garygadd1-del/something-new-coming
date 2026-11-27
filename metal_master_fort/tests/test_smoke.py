"""Smoke for the five local modules. The anomaly harness is not exercised here."""

import json
import subprocess
from pathlib import Path

import pytest

from daily_standup.digest import (
    DigestError,
    build_digest,
    load_cards,
    load_incidents,
    render_markdown,
)
from game_world.world import (
    BLANK_MINUTES_CAP,
    WorldError,
    blank_seat_lines,
    expand_jobs,
    load_spec,
    make_roster,
    pick_name,
)
from house_policy import AUTHORITY_GARY, GARY_CAPS, STANDING_CAPS, SWARM
from medic_bot.triage import RenameLedger, triage, triage_log
from parameter_masks.guard import commit_mask
from parameter_masks.loader import apply_mask, load_brain, load_mask

ROOT = Path(__file__).resolve().parents[1]


def test_smoke_parameter_masks_keep_four_roles_and_job_upgrades():
    brain = load_brain()
    mayor = apply_mask(brain, load_mask("mayor"), job="hold_thermal_budget")
    assert set(mayor["parameters"]) == {
        "governance",
        "diplomacy",
        "resource_allocation",
        "speech",
        "memory",
    }
    assert "thermal_policy" in mayor["parameters"]["resource_allocation"]
    assert "combat" in mayor["stripped"]
    warrior = apply_mask(brain, load_mask("warrior"), job="hold_gate")
    assert set(warrior["parameters"]) == {"combat", "threat"}
    assert warrior["parameters"]["combat"]["doctrine"] == "defense_only"
    assert warrior["parameters"]["combat"]["post"] == "fort_gate"
    medic = apply_mask(brain, load_mask("medic"), job="patch_typo")
    assert medic["parameters"]["triage"]["closes"] == "config_typo"
    librarian = apply_mask(brain, load_mask("librarian"), job="lend")
    assert librarian["emergent"] is True
    assert set(librarian["parameters"]) == {"catalog", "memory"}


def test_smoke_mask_guard_accepts_a_produced_librarian(tmp_path, mask_guard):
    masked = apply_mask(load_brain(), load_mask("librarian"), job="shelve")
    commit_mask(masked, tmp_path / "librarian.json", mask_guard)


def test_smoke_medic_classifies_logs_and_keeps_renames_in_memory(tmp_path):
    typo_path = ROOT / "medic_bot" / "fixtures" / "config_typo.log"
    before = typo_path.read_bytes()
    typo = triage_log(typo_path.read_text(encoding="utf-8"))
    crash = triage_log((ROOT / "medic_bot" / "fixtures" / "crash.log").read_text(encoding="utf-8"))
    bug = triage_log((ROOT / "medic_bot" / "fixtures" / "real_bug.log").read_text(encoding="utf-8"))
    assert typo["class"] == "config_typo"
    assert typo["closed_here"] is True
    assert typo["patch"]["from"] == "coreC"
    assert typo["patch"]["to"] == "core_c"
    assert crash["class"] == "crash"
    assert crash["escalate"] is True
    assert crash["patch"] is None
    assert bug["class"] == "real_bug"
    assert bug["escalate"] is True
    assert bug["closed_here"] is False
    for ticket in (typo, crash, bug):
        assert ticket["forward_to_harness"] is False
        assert ticket["stops_snowball"] is True
    forced = json.loads((ROOT / "medic_bot" / "fixtures" / "crash.json").read_text(encoding="utf-8"))
    forced["forward_to_harness"] = True
    assert triage(forced)["forward_to_harness"] is False
    memory = triage_log("bot: librarian\nlane: catalog\nMemoryError\n")
    assert memory["class"] == "crash"
    ledger = RenameLedger()
    ledger.record(typo)
    ledger.record(crash)
    original = {"coreC": 81, "hotspot_c": 70}
    renamed = ledger.apply(original)
    assert original == {"coreC": 81, "hotspot_c": 70}
    assert renamed == {"core_c": 81, "hotspot_c": 70}
    assert len(ledger.proposals) == 1
    assert typo_path.read_bytes() == before
    assert list(tmp_path.iterdir()) == []


def test_smoke_standup_reads_the_outbox_and_does_not_grant(tmp_path):
    outbox = ROOT / "daily_standup" / "fixtures" / "outbox"
    roll = json.loads(
        (ROOT / "daily_standup" / "fixtures" / "roll_call.json").read_text(encoding="utf-8")
    )
    incidents = load_incidents(ROOT / "daily_standup" / "fixtures" / "incidents.jsonl")
    from_dir = build_digest(load_cards(outbox), roll, incidents)
    from_file = build_digest(
        load_cards(ROOT / "daily_standup" / "fixtures" / "cards.json"), roll, incidents
    )
    assert from_dir == from_file
    assert from_dir["morning"] == "2026-10-25"
    assert from_dir["approval_gate"]["grants"] == []
    assert from_dir["present"]
    for bot in from_dir["present"]:
        assert bot not in from_dir["approval_gate"]["grants"]
    text = render_markdown(from_dir)
    assert "Approval Gate:" in text
    assert "grants: none" in text
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(DigestError, match="no cards"):
        load_cards(tmp_path)


def test_smoke_scheduler_assigns_minutes_to_blank_seats_without_names(tmp_path):
    spec = load_spec()
    jobs = expand_jobs(spec)
    roster = make_roster(spec)
    blanks = [job for job in jobs if job["blank"]]
    assert len(blanks) == 24
    assert all(job["street_name"] is None and job["title"] is None and job["trade"] is None for job in blanks)
    assert all(bot["real_name"] is None and bot["street_name"] is None for bot in roster)
    with pytest.raises(WorldError, match="will not invent"):
        pick_name(roster[0])
    lines = blank_seat_lines(jobs, 15)
    assert len(lines) == 24
    assert all(line.startswith("seat blank.") and line.endswith(" 15") for line in lines)
    assert all(len(line.split()) == 3 for line in lines)
    with pytest.raises(WorldError, match="example cap"):
        blank_seat_lines(jobs, BLANK_MINUTES_CAP + 1)

    source = (ROOT / "game_world" / "schedule.c").read_text(encoding="utf-8")
    assert f"#define BLANK_MINUTES_CAP {BLANK_MINUTES_CAP}" in source
    binary = tmp_path / "schedule"
    subprocess.check_call(
        [
            "gcc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-o",
            str(binary),
            str(ROOT / "game_world" / "schedule.c"),
        ]
    )
    clean = tmp_path / "blank.txt"
    clean.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ran = subprocess.run([str(binary), str(clean)], check=False, capture_output=True, text=True)
    assert ran.returncode == 0, ran.stdout
    assert ran.stdout.count("name=") == 24
    assert "SUMMARY ok=24 reroute=0" in ran.stdout
    assert "Kiln" not in ran.stdout

    mixed = subprocess.run(
        [str(binary), str(ROOT / "game_world" / "fixtures" / "blank_seats.txt")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert mixed.returncode == 3, mixed.stdout
    assert "OK seat=blank.001 minutes=15 name=" in mixed.stdout
    assert "OK seat=blank.002 minutes=15 name=" in mixed.stdout
    assert "blank seat names stay blank" in mixed.stdout
    assert "Kiln" not in mixed.stdout

    too_many = tmp_path / "too_many.txt"
    too_many.write_text("seat blank.001 46\n", encoding="utf-8")
    refused = subprocess.run([str(binary), str(too_many)], check=False, capture_output=True, text=True)
    assert refused.returncode == 2
    assert "blank seat minutes refused" in refused.stdout
    assert "OK " not in refused.stdout


def test_smoke_readme_hardware_table_matches_the_owner():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "| Throne | RX 7900 XTX |" in text
    assert "86 C core / 88 C hotspot / 80% load" in text
    assert "85 C core" in text
    assert "80 C core" in text
    assert "RX 7900 GRE only" in text
    assert "loosens" in text
    assert "tighter" in text
    assert "| selfaware | RX 7900 XTX |" not in text
    assert "older cards the owner did not name" not in text
    by_gpu = {(row["machine"], row["gpu"]): row for row in GARY_CAPS}
    throne = by_gpu[("throne", "rx_7900_xtx")]
    assert throne["core_c"] == 86
    assert throne["hotspot_c"] == 88
    assert throne["load_pct"] == 80
    assert throne["authority"] == AUTHORITY_GARY
    assert throne["standing_caps"] == STANDING_CAPS
    card_9070 = by_gpu[("selfaware", "rx_9070")]
    assert card_9070["core_c"] == 85
    assert card_9070["hotspot_c"] is None
    assert card_9070["load_pct"] is None
    card_1650 = by_gpu[("selfaware", "gtx_1650")]
    assert card_1650["core_c"] == 80
    assert card_1650["hotspot_c"] is None
    assert card_1650["load_pct"] is None
    gre = by_gpu[("fuzzy66", "rx_7900_gre")]
    assert gre["core_c"] is None
    assert gre["hotspot_c"] is None
    assert gre["load_pct"] is None
    assert "also" not in gre
    assert "throne" not in SWARM
