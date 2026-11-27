from pathlib import Path

import pytest

from amd_gpu_sampler.analyze import analyze, explain
from amd_gpu_sampler.config import DEFAULT_SENSORS, DEFAULT_THERMAL_PAUSE_CELSIUS, SamplerConfig, load_config
from amd_gpu_sampler.counters import StaticSource, TypeperfReader, parse_typeperf_header, parse_typeperf_row, typeperf_argv
from amd_gpu_sampler.safety import SafetyError, jload
from amd_gpu_sampler.sample import build_sample
from amd_gpu_sampler.thermal import PauseDecision, decide_pause, fresh_readings
from tests.fixture_counters import calm_counter_text

ROOT = Path(__file__).resolve().parents[1]


def _parsed():
    header, row = calm_counter_text()
    cols = parse_typeperf_header(header)
    assert cols
    values = parse_typeperf_row(row, cols)
    assert values
    return cols, values


def test_mock_counters_select_the_busiest_adapter():
    cols, values = _parsed()
    sample = build_sample(
        cols=cols,
        row=values,
        recv=1_760_000_000,
        t=1_760_000_000,
        thermal={
            "t": 1_760_000_000 - 1,
            "gpu": {"edge_c": 70, "junction_c": 88, "power_w": 140, "vram_total_mb": 20480},
            "cpu": {"cores_c": [60, 77]},
        },
        godot_pid=4242,
        godot_cols=None,
        godot_row=None,
        godot_recv=0,
        vram_total_mb_fallback=24560,
    )
    assert sample["counters_ok"] is True
    assert sample["avail_mb"] == 16384
    assert sample["cpu"] == 12.5
    assert sample["cores"] == [20]
    assert sample["gpu_used_mb"] == 1024
    assert sample["gpu_total_mb"] == 20480
    assert sample["gpu_free_mb"] == 19456
    assert sample["gpu_3d"] == 40
    assert sample["gpu_compute"] == 10
    assert sample["gpu_busy"] == 40
    assert sample["godot_gpu"] == 40
    assert sample["godot_vram_mb"] == 256
    assert sample["gpu_edge_c"] == 70
    assert sample["cpu_core_c"] == 77
    assert sample["gpu_junction_c"] == 88
    source = StaticSource(cols, values, recv=1_760_000_000)
    assert source.snapshot()[0] == cols


def test_temperatures_survive_when_counters_are_down():
    sample = build_sample(
        cols=None,
        row=None,
        recv=0,
        t=100,
        thermal={"t": 99, "gpu": {"edge_c": 78, "junction_c": 90}, "cpu": {"core_c": 40}},
        godot_pid=0,
        godot_cols=None,
        godot_row=None,
        godot_recv=0,
        vram_total_mb_fallback=24560,
    )
    assert "gpu_free_mb" not in sample
    assert sample["gpu_edge_c"] == 78
    assert sample["thermal_age_s"] == 1


def test_vram_full_is_visible_when_free_is_zero():
    causes = explain({"kind": "gap", "gap_ms": 3000}, [{"gpu_free_mb": 0, "gpu_busy": 10}], ncpu=8)
    assert causes[0]["cause"] == "gpu_saturation_or_vram_full"


def test_signal_ladder_uses_mocked_numbers():
    tight = {"t": 100, "gpu_free_mb": 500, "gpu_busy": 1, "gpu_used_mb": 1, "tp_age_s": 0}
    assert any(item["id"] == "gpu_vram" and item["level"] == 3 for item in analyze([], tight, ncpu=4))
    hot = {"t": 100, "gpu_junction_c": 90, "thermal_age_s": 1, "tp_age_s": 0}
    assert any(item["id"] == "gpu_temp" and item["level"] == 2 for item in analyze([], hot, ncpu=4))
    stale = {"t": 100, "gpu_junction_c": 90, "thermal_age_s": 40, "tp_age_s": 0}
    assert all(item["id"] != "gpu_temp" for item in analyze([], stale, ncpu=4))
    queued = {
        "t": 100,
        "counters_ok": True,
        "cpu": 10,
        "cpu_max_core": 10,
        "dpc": 0,
        "irq": 0,
        "queue": 9,
        "perf_limit": 100,
        "avail_mb": 20000,
        "commit_pct": 10,
        "pages_in_s": 0,
        "tp_age_s": 0,
    }
    levels = {item["id"]: item["level"] for item in analyze([], queued, ncpu=4)}
    assert levels["cpu_queue"] == 2
    reading = dict(queued)
    reading["pages_in_s"] = 2000
    faults = {item["id"]: item for item in analyze([], reading, ncpu=4)}
    assert faults["ram_hardfaults"]["level"] == 1
    assert faults["ram_hardfaults"]["expect"] == "none"


def test_pause_rule_defaults_and_hysteresis():
    assert DEFAULT_THERMAL_PAUSE_CELSIUS == 78.0
    sample = {"thermal_age_s": 1.0, "gpu_edge_c": 40.0, "gpu_junction_c": 95.0, "cpu_core_c": 50.0}
    readings = fresh_readings(sample, DEFAULT_SENSORS, max_age_s=30)
    assert [name for name, _ in readings] == ["gpu_edge_c", "cpu_core_c"]
    assert decide_pause(readings, threshold_c=78, resume_c=75, currently_paused=False).action == "report"
    sample["gpu_edge_c"] = 78
    hot = fresh_readings(sample, DEFAULT_SENSORS, max_age_s=30)
    decision = decide_pause(hot, threshold_c=78, resume_c=75, currently_paused=False)
    assert decision.action == "pause_reporting"
    assert decision.sensor == "gpu_edge_c"
    assert decide_pause([("gpu_edge_c", 77.9)], threshold_c=78, resume_c=75, currently_paused=False).action == "report"
    assert decide_pause([("cpu_core_c", 75.0)], threshold_c=78, resume_c=75, currently_paused=True).action == "report"
    assert decide_pause([("cpu_core_c", 75.1)], threshold_c=78, resume_c=75, currently_paused=True).paused
    assert fresh_readings({"thermal_age_s": 30.1, "gpu_edge_c": 90}, DEFAULT_SENSORS, max_age_s=30) == []
    assert fresh_readings({"thermal_age_s": 30, "gpu_edge_c": 90}, DEFAULT_SENSORS, max_age_s=30)
    held = decide_pause([], threshold_c=78, resume_c=75, currently_paused=True)
    assert held.action == "pause_reporting"
    with pytest.raises(ValueError):
        PauseDecision("terminate", None, None, 78, 75, None)
    with pytest.raises(ValueError):
        decide_pause([], threshold_c=78, resume_c=78, currently_paused=False)


def test_example_config_is_the_78c_rule():
    config = load_config(ROOT / "sampler_config.example.json")
    assert config.thermal_pause_celsius == 78
    assert config.thermal_resume_celsius == 75
    assert config.thermal_sensors == ("gpu_edge_c", "cpu_core_c")
    with pytest.raises(SafetyError):
        SamplerConfig(thermal_pause_celsius=78, thermal_resume_celsius=78)


def test_typeperf_argv_is_fixed_and_windows_only():
    assert typeperf_argv([r"\Memory\Available MBytes"]) == ["typeperf", r"\Memory\Available MBytes", "-si", "1"]
    with pytest.raises(SafetyError):
        typeperf_argv(["-si"])
    if __import__("sys").platform != "win32":
        with pytest.raises(SafetyError):
            TypeperfReader("sys", [r"\Memory\Available MBytes"])


def test_secret_filename_is_not_opened(tmp_path):
    path = tmp_path / "api_key.json"
    path.write_text('{"token": "keep"}', encoding="utf-8")
    with pytest.raises(SafetyError):
        jload(path)
    assert path.read_text(encoding="utf-8") == '{"token": "keep"}'
