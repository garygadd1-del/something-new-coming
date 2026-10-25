"""Parameter masks, and the Rust wrapper that reroutes a sideways mask."""

import json
import subprocess
from pathlib import Path

import pytest

from house_policy import (
    FUZZY_CHEAP_PASS_CORE_C,
    FUZZY_CHEAP_PASS_HOTSPOT_C,
    SWARM,
    XTX_CORE_C,
    XTX_HOTSPOT_C,
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
    assert policy["selfaware_rx_7900_xtx"] == {"core_c": XTX_CORE_C, "hotspot_c": XTX_HOTSPOT_C}
    cheap = policy["fuzzy66_rx_6600_cheap_pass"]
    assert cheap["core_c"] == FUZZY_CHEAP_PASS_CORE_C
    assert cheap["hotspot_c"] == FUZZY_CHEAP_PASS_HOTSPOT_C
    assert cheap["lane"] == "cheap_pass"


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


@pytest.fixture(scope="session")
def mask_guard() -> Path:
    manifest = ROOT / "rust_wrappers" / "Cargo.toml"
    subprocess.check_call(
        ["cargo", "test", "--manifest-path", str(manifest), "--offline", "--quiet"],
    )
    subprocess.check_call(
        ["cargo", "build", "--manifest-path", str(manifest), "--offline", "--quiet"],
    )
    binary = ROOT / "rust_wrappers" / "target" / "debug" / "mask_guard"
    assert binary.is_file()
    return binary


def test_wrapper_accepts_a_real_mask_and_reroutes_a_sideways_one(tmp_path, mask_guard):
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
