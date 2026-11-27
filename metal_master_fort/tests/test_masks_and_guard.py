"""Parameter masks, and the Rust wrapper that reroutes a sideways mask."""

import json
from pathlib import Path

import pytest

from house_policy import (
    AUTHORITY_GARY,
    CORE_1650_C,
    CORE_9070_C,
    STANDING_CAPS,
    SWARM,
    XTX_CORE_C,
    XTX_HOTSPOT_C,
    XTX_LOAD_PCT,
)
from parameter_masks.guard import Reroute, commit_mask
from parameter_masks.loader import MaskError, apply_mask, load_brain, load_mask

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "parameter_masks" / "schema" / "masked_brain.schema.json").read_text(encoding="utf-8")
)


def test_mayor_is_the_civic_stack_and_the_thermal_job_upgrades_it():
    brain = load_brain()
    before = json.dumps(brain, sort_keys=True)
    plain = apply_mask(brain, load_mask("mayor"))
    assert json.dumps(brain, sort_keys=True) == before
    assert set(plain["parameters"]) == {
        "governance",
        "diplomacy",
        "resource_allocation",
        "speech",
        "memory",
    }
    assert "combat" in plain["stripped"]
    assert "threat" in plain["stripped"]
    assert plain["emergent"] is False
    assert "thermal_policy" not in plain["parameters"]["resource_allocation"]
    assert plain["parameters"]["resource_allocation"]["swarm"] == list(SWARM)
    assert plain["parameters"]["speech"]["leader_voice"] == "when_called"
    for key in SCHEMA["required"]:
        assert key in plain

    budget = apply_mask(brain, load_mask("mayor"), job="hold_thermal_budget")
    policy = budget["parameters"]["resource_allocation"]["thermal_policy"]
    assert policy["throne_rx_7900_xtx"] == {
        "core_c": XTX_CORE_C,
        "hotspot_c": XTX_HOTSPOT_C,
        "load_pct": XTX_LOAD_PCT,
        "authority": AUTHORITY_GARY,
        "standing_caps": STANDING_CAPS,
    }
    assert policy["selfaware_rx_9070"]["core_c"] == CORE_9070_C
    assert "hotspot_c" not in policy["selfaware_rx_9070"]
    assert "load_pct" not in policy["selfaware_rx_9070"]
    assert policy["selfaware_gtx_1650"]["core_c"] == CORE_1650_C
    assert "hotspot_c" not in policy["selfaware_gtx_1650"]
    assert "fuzzy66_rx_6600_cheap_pass" not in policy
    assert "fuzzy66_rx_7900_gre" not in policy


def test_warrior_is_combat_and_threat_with_the_rest_stripped():
    masked = apply_mask(load_brain(), load_mask("warrior"), job="hold_gate")
    assert set(masked["parameters"]) == {"combat", "threat"}
    assert "governance" in masked["stripped"]
    assert masked["parameters"]["combat"]["doctrine"] == "defense_only"
    assert masked["parameters"]["combat"]["post"] == "fort_gate"
    assert masked["parameters"]["threat"]["scope"] == "house_only"
    assert masked["emergent"] is False


def test_librarian_is_the_little_mask():
    masked = apply_mask(load_brain(), load_mask("librarian"), job="shelve")
    assert set(masked["parameters"]) == {"catalog", "memory"}
    assert masked["emergent"] is True
    assert "combat" in masked["stripped"]
    notes = (ROOT / "parameter_masks" / "masks" / "librarian.json").read_text(encoding="utf-8")
    assert "emergent" in notes
    assert "Little mask" in notes


def test_medic_job_can_upgrade_triage_without_growing_a_parameter():
    masked = apply_mask(load_brain(), load_mask("medic"), job="patch_typo")
    assert masked["parameters"]["triage"]["closes"] == "config_typo"
    assert "combat" not in masked["parameters"]
    escalated = apply_mask(load_brain(), load_mask("medic"), job="escalate_bug")
    assert escalated["parameters"]["triage"]["sends_to"] == "morning_digest"


def test_a_mask_cannot_put_a_stripped_parameter_back_or_change_doctrine():
    mask = load_mask("mayor")
    mask["upgrade"] = {"combat": {"enabled": True}}
    with pytest.raises(MaskError, match="adds parameter"):
        apply_mask(load_brain(), mask)
    warrior = load_mask("warrior")
    warrior["upgrade"] = {"combat": {"doctrine": "raid"}}
    with pytest.raises(MaskError, match="defense_only"):
        apply_mask(load_brain(), warrior)
    with pytest.raises(MaskError, match="not assigned"):
        apply_mask(load_brain(), load_mask("librarian"), job="hold_gate")


def test_wrapper_accepts_every_produced_mask_and_reroutes_sideways(tmp_path, mask_guard):
    masked = apply_mask(load_brain(), load_mask("mayor"), job="hold_thermal_budget")
    dest = tmp_path / "mayor.json"
    commit_mask(masked, dest, mask_guard)
    warrior = apply_mask(load_brain(), load_mask("warrior"))
    good = tmp_path / "warrior.json"
    commit_mask(warrior, good, mask_guard)
    sideways = json.loads(good.read_text(encoding="utf-8"))
    sideways["parameters"]["combat"]["doctrine"] = "raid"
    bad = tmp_path / "raid.json"
    with pytest.raises(Reroute, match="defense_only"):
        commit_mask(sideways, bad, mask_guard)
    missing = tmp_path / "missing-binary"
    with pytest.raises(Reroute, match="binary missing"):
        commit_mask(masked, tmp_path / "held.json", missing)

    brain = load_brain()
    for role in ("mayor", "warrior", "medic", "librarian"):
        mask = load_mask(role)
        plain = apply_mask(brain, mask)
        commit_mask(plain, tmp_path / f"{role}.json", mask_guard)
        for job in mask["jobs"]:
            produced = apply_mask(brain, mask, job=job)
            commit_mask(produced, tmp_path / f"{role}-{job}.json", mask_guard)

    librarian = apply_mask(brain, load_mask("librarian"), job="shelve")
    librarian["parameters"]["combat"] = {"enabled": True, "doctrine": "defense_only"}
    with pytest.raises(Reroute, match="stripped"):
        commit_mask(librarian, tmp_path / "librarian-combat.json", mask_guard)

    loosened = apply_mask(brain, load_mask("mayor"), job="hold_thermal_budget")
    loosened["parameters"]["resource_allocation"]["thermal_policy"]["throne_rx_7900_xtx"][
        "core_c"
    ] = 90
    with pytest.raises(Reroute, match="loosen"):
        commit_mask(loosened, tmp_path / "loosened.json", mask_guard)

    tightened = apply_mask(brain, load_mask("mayor"), job="hold_thermal_budget")
    tightened["parameters"]["resource_allocation"]["thermal_policy"]["throne_rx_7900_xtx"][
        "core_c"
    ] = 75
    commit_mask(tightened, tmp_path / "tightened.json", mask_guard)

    swarm = apply_mask(brain, load_mask("mayor"))
    swarm["parameters"]["resource_allocation"]["swarm"] = ["selfaware", "fuzzy66", "throne"]
    with pytest.raises(Reroute, match="swarm"):
        commit_mask(swarm, tmp_path / "throne.json", mask_guard)
