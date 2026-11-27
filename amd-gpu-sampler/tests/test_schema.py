import pytest

from amd_gpu_sampler.gpu_state import build_gpu_state, short_gpu_name
from amd_gpu_sampler.schema import SchemaError, validate_gpu_state, validate_sampler_state
from amd_gpu_sampler.thermal import PauseDecision


def _pause(paused: bool) -> PauseDecision:
    if not paused:
        return PauseDecision("report", "gpu_edge_c", 40.0, 78.0, 75.0, None)
    return PauseDecision(
        "pause_reporting",
        "gpu_edge_c",
        78.0,
        78.0,
        75.0,
        "gpu_edge_c 78.0 C >= pause 78.0 C; reporting paused; process left running",
    )


def _state(paused: bool = False) -> dict:
    from amd_gpu_sampler.schema import assemble_sampler_state

    return assemble_sampler_state(
        sample={
            "gpu_busy": 12.5,
            "gpu_used_mb": 1024,
            "gpu_total_mb": 20480,
            "gpu_junction_c": 60,
            "gpu_power_w": 120,
            "avail_mb": 16384,
            "commit_pct": 20,
            "pages_in_s": 4,
            "pf_s": 10,
            "cpu": 15,
            "cpu_max_core": 20,
            "queue": 1,
            "dpc": 0.2,
            "irq": 0.1,
            "freq_mhz": 4200,
            "perf_limit": 100,
            "godot_cpu_core_pct": 3,
            "godot_ws_mb": 800,
            "godot_gpu": 5,
        },
        signals=[],
        level=0,
        felt="All calm",
        expect="none",
        godot_pid=4242,
        godot_age=0.2,
        heartbeat={"p99_ms": 1.0, "max_ms": 2.0},
        last_blackout=None,
        pause=_pause(paused),
        pause_since="2026-10-25T00:00:00.000+00:00" if paused else None,
        sampler_meta={
            "pid": 10,
            "self_cpu_pct": 0.1,
            "pipe_feed": "disabled",
            "pipe_sent": 0,
            "chain_seq": 2,
            "chain_hash": "ab" * 8,
            "thermal_pause_c": 78,
            "thermal_resume_c": 75,
        },
        ts="2026-10-25T00:00:01.000+00:00",
        unix=1_760_000_001,
    )


def test_sampler_snapshot_schema_accepts_assembled_state():
    state = _state()
    assert validate_sampler_state(state) == []
    assert state["schema"] == "inner_world/1"
    assert state["reporting"] == "active"
    assert state["pause"] is None
    assert state["gpu"]["vram_free_mb"] == 20480 - 1024
    assert state["sampler"]["thermal_pause_c"] == 78


def test_paused_snapshot_carries_the_threshold():
    state = _state(paused=True)
    assert state["reporting"] == "paused"
    assert state["pause"]["threshold_c"] == 78
    assert state["pause"]["resume_below_c"] == 75
    assert validate_sampler_state(state) == []


def test_sampler_schema_rejects_a_broken_snapshot():
    state = _state()
    state["gpu"]["util_pct"] = 140
    assert any("util_pct" in error for error in validate_sampler_state(state))
    del state["gpu"]
    state["gpu"] = {"util_pct": 1}
    assert any("vram_used_mb" in error for error in validate_sampler_state(state))
    active = _state()
    active["pause"] = {"reason": "no"}
    assert any("pause must be null" in error for error in validate_sampler_state(active))
    paused = _state(True)
    paused["pause"] = None
    assert any("pause must explain" in error for error in validate_sampler_state(paused))


def test_gpu_state_schema_and_pause_rule():
    assert short_gpu_name("AMD Radeon RX 7900 XTX") == "RX 79xx"
    assert short_gpu_name("Basic Display") == "GPU"
    calm = build_gpu_state(
        machine="selfaware",
        role="traces+spectral",
        gpu_name="AMD Radeon RX 7900 XTX",
        util_3d=40,
        util_compute=150,
        vram_bytes=1.5 * 1024**3,
        gpu_core_c=60,
        gpu_junction_c=90,
        cpu_core_c=50,
        now=1_760_000_000,
    )
    assert validate_gpu_state(calm) == []
    assert calm["schema"] == "gpu_state/1"
    assert calm["gpu"] == "RX 79xx"
    assert calm["util_pct"] == 100.0
    assert calm["vram_used_gb"] == 1.5
    assert calm["temp_c"] == 60
    assert calm["core_temp_c"] == 60
    assert calm["reporting_paused"] is False
    assert calm["source"] == "win-perfcounters"

    hot = build_gpu_state(
        machine="fuzzy66",
        role="body",
        gpu_name="AMD Radeon RX 7900 XTX",
        util_3d=10,
        util_compute=10,
        vram_bytes=1024**3,
        gpu_core_c=78,
        gpu_junction_c=90,
        cpu_core_c=40,
        now=1_760_000_000,
    )
    assert hot["reporting_paused"] is True
    assert "process left running" in hot["pause_reason"]
    assert hot["thermal_pause_c"] == 78

    junction_only = build_gpu_state(
        machine="fuzzy66",
        role="body",
        gpu_name=None,
        util_3d=1,
        util_compute=1,
        vram_bytes=0,
        gpu_junction_c=95,
        now=1_760_000_000,
    )
    assert junction_only["reporting_paused"] is False
    assert junction_only["temp_c"] == 95
    assert junction_only["core_temp_c"] is None

    held = build_gpu_state(
        machine="fuzzy66",
        role="body",
        gpu_name="AMD Radeon RX 7900 XTX",
        util_3d=1,
        util_compute=1,
        vram_bytes=0,
        gpu_core_c=76,
        currently_paused=True,
        now=1_760_000_000,
    )
    assert held["reporting_paused"] is True
    resumed = build_gpu_state(
        machine="fuzzy66",
        role="body",
        gpu_name="AMD Radeon RX 7900 XTX",
        util_3d=1,
        util_compute=1,
        vram_bytes=0,
        gpu_core_c=75,
        currently_paused=True,
        now=1_760_000_000,
    )
    assert resumed["reporting_paused"] is False
    missing = build_gpu_state(
        machine="fuzzy66",
        role="body",
        gpu_name=None,
        util_3d=0,
        util_compute=0,
        vram_bytes=0,
        currently_paused=True,
        now=1_760_000_000,
    )
    assert missing["reporting_paused"] is True
    assert missing["temp_source"] == "unavailable"

    forced = build_gpu_state(
        machine="fuzzy66",
        role="body",
        gpu_name=None,
        util_3d=1,
        util_compute=1,
        vram_bytes=0,
        gpu_junction_c=80,
        include_junction=True,
        now=1_760_000_000,
    )
    assert forced["reporting_paused"] is True


def test_gpu_state_rejects_a_path_like_machine():
    with pytest.raises(SchemaError):
        build_gpu_state(
            machine="../selfaware",
            role="body",
            gpu_name=None,
            util_3d=0,
            util_compute=0,
            vram_bytes=0,
            now=1_760_000_000,
        )
