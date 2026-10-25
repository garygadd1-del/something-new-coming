import json

import pytest

from amd_gpu_sampler.chain import ChainError, verify_log
from amd_gpu_sampler.config import SamplerConfig
from amd_gpu_sampler.counters import StaticSource, parse_typeperf_header, parse_typeperf_row
from amd_gpu_sampler.pipe import PipeFeed
from amd_gpu_sampler.safety import SafetyError
from amd_gpu_sampler.sampler import Sampler, main
from amd_gpu_sampler.schema import validate_sampler_state
from tests.fixture_counters import calm_counter_text


class Clock:
    def __init__(self):
        self.t = 1_760_000_000.0

    def __call__(self):
        return self.t


class RecordingSender:
    def __init__(self):
        self.payloads = []

    def send(self, payload, via="udp"):
        assert via == "udp"
        self.payloads.append(payload)
        return True


def _source(now: float) -> StaticSource:
    header, row = calm_counter_text()
    cols = parse_typeperf_header(header)
    values = parse_typeperf_row(row, cols)
    return StaticSource(cols, values, recv=now)


def _thermal(now: float, edge: float, cpu: float = 40, junction: float = 60):
    return {
        "t": now - 1,
        "gpu": {"edge_c": edge, "junction_c": junction, "power_w": 100, "vram_total_mb": 20480},
        "cpu": {"cores_c": [cpu]},
    }


def test_active_sample_writes_a_valid_snapshot_and_pipes_it(tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_text("keep", encoding="utf-8")
    clock = Clock()
    sender = RecordingSender()
    pipe = PipeFeed(tmp_path, tmp_path / "link", enabled=True, sender=sender, force_active=True)
    sampler = Sampler(
        tmp_path,
        config=SamplerConfig(),
        sys_source=_source(clock.t),
        pipe=pipe,
        clock=clock,
        thermal_loader=lambda: _thermal(clock.t, edge=40, junction=88),
        ncpu=8,
    )
    assert sampler.run(iterations=1) == 0
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert validate_sampler_state(state) == []
    assert state["reporting"] == "active"
    assert state["gpu"]["temp_c"] == 88
    assert state["gpu"]["vram_free_mb"] == 19456
    assert state["sampler"]["thermal_pause_c"] == 78
    assert verify_log(tmp_path / "log").ok
    assert len(sender.payloads) == 1
    assert sender.payloads[0]["action"] == "inner_world"
    assert "host" not in sender.payloads[0]
    assert notes.read_text(encoding="utf-8") == "keep"
    assert not (tmp_path / "sampler.pid").exists()
    stopped = next(tmp_path.glob("sampler.pid.stopped*"))
    assert str(sampler_pid()) in stopped.read_text(encoding="utf-8")


def sampler_pid():
    import os

    return os.getpid()


def test_hot_core_pauses_reporting_without_stopping(tmp_path):
    clock = Clock()
    sender = RecordingSender()
    pipe = PipeFeed(tmp_path, tmp_path / "link", enabled=True, sender=sender, force_active=True)
    sampler = Sampler(
        tmp_path,
        sys_source=StaticSource(),
        pipe=pipe,
        clock=clock,
        thermal_loader=lambda: _thermal(clock.t, edge=78, cpu=40, junction=86),
        ncpu=8,
    )
    assert sampler.run(iterations=1) == 0
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert validate_sampler_state(state) == []
    assert state["reporting"] == "paused"
    assert state["expect"] == "thermal_pause"
    assert state["pause"]["sensor"] == "gpu_edge_c"
    assert state["pause"]["threshold_c"] == 78
    assert "process left running" in state["pause"]["reason"]
    assert sender.payloads == []
    assert verify_log(tmp_path / "log").ok
    text = "".join(path.read_text(encoding="utf-8") for path in (tmp_path / "log").glob("health_*.jsonl"))
    assert "thermal_pause" in text
    assert "terminate" not in text


def test_stale_temperature_does_not_start_a_pause(tmp_path):
    clock = Clock()

    def thermal():
        data = _thermal(clock.t, edge=90)
        data["t"] = clock.t - 120
        return data

    sampler = Sampler(tmp_path, sys_source=StaticSource(), clock=clock, thermal_loader=thermal, ncpu=8)
    sampler.run(iterations=1)
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["reporting"] == "active"


def test_stop_file_is_kept(tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_text("keep", encoding="utf-8")
    clock = Clock()

    def sleeper(_seconds):
        (tmp_path / "STOP").write_text("please stop\n", encoding="utf-8")

    sampler = Sampler(
        tmp_path,
        sys_source=_source(clock.t),
        clock=clock,
        thermal_loader=lambda: _thermal(clock.t, edge=40),
        ncpu=8,
    )
    assert sampler.run(iterations=5, sleep=sleeper) == 0
    assert (tmp_path / "STOP").read_text(encoding="utf-8") == "please stop\n"
    assert notes.read_text(encoding="utf-8") == "keep"
    assert (tmp_path / "state.json").is_file()


def test_stale_stop_is_renamed_not_deleted(tmp_path):
    (tmp_path / "STOP").write_text("stale\n", encoding="utf-8")
    clock = Clock()
    sampler = Sampler(
        tmp_path,
        sys_source=_source(clock.t),
        clock=clock,
        thermal_loader=lambda: _thermal(clock.t, edge=40),
        ncpu=8,
    )
    sampler.run(iterations=1)
    assert not (tmp_path / "STOP").exists()
    done = next(tmp_path.glob("STOP.*.done"))
    assert done.read_text(encoding="utf-8") == "stale\n"
    assert (tmp_path / "state.json").is_file()


def test_symlinked_work_dir_is_refused(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "keep.txt").write_text("safe", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(SafetyError):
        Sampler(link, clock=Clock(), ncpu=8).run(iterations=1)
    assert (real / "keep.txt").read_text(encoding="utf-8") == "safe"
    assert not (real / "state.json").exists()


def test_symlinked_snapshot_is_not_replaced(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("keep", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    (work / "state.json").symlink_to(outside)
    clock = Clock()
    Sampler(
        work,
        sys_source=_source(clock.t),
        clock=clock,
        thermal_loader=lambda: _thermal(clock.t, edge=40),
        ncpu=8,
    ).run(iterations=1)
    assert outside.read_text(encoding="utf-8") == "keep"


def test_corrupt_log_is_not_rewritten(tmp_path):
    log = tmp_path / "log"
    log.mkdir()
    bad = log / "health_20261009.jsonl"
    bad.write_text("{not json\n", encoding="utf-8")
    with pytest.raises(ChainError):
        Sampler(tmp_path, clock=Clock(), ncpu=8).run(iterations=1)
    assert bad.read_text(encoding="utf-8") == "{not json\n"


def test_already_running_leaves_the_pid_file(tmp_path):
    from amd_gpu_sampler.process_info import pid_alive

    if not pid_alive(1):
        pytest.skip("pid 1 is not visible")
    (tmp_path / "sampler.pid").write_text("1 old\n", encoding="utf-8")
    code = Sampler(tmp_path, clock=Clock(), ncpu=8).run(iterations=1)
    assert code == 0
    assert (tmp_path / "sampler.pid").read_text(encoding="utf-8").startswith("1")
    assert not (tmp_path / "state.json").exists()


def test_verify_cli_and_live_guard(tmp_path):
    clock = Clock()
    Sampler(
        tmp_path,
        sys_source=_source(clock.t),
        clock=clock,
        thermal_loader=lambda: _thermal(clock.t, edge=40),
        ncpu=8,
    ).run(iterations=1)
    assert main(["--verify-log", str(tmp_path / "log")]) == 0
    path = next((tmp_path / "log").glob("health_*.jsonl"))
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[-1])
    record["hash"] = ("0" if record["hash"][0] != "0" else "1") + record["hash"][1:]
    lines[-1] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert main(["--verify-log", str(path)]) == 1
    if __import__("sys").platform != "win32":
        assert main([]) == 2


def test_pipe_does_not_echo_unrelated_fields(tmp_path):
    link = tmp_path / "link"
    link.mkdir()
    (link / "godot_alive.json").write_text(json.dumps({"pid": 4242, "token": "SUPERSECRET"}), encoding="utf-8")
    (tmp_path / "godot_handler_installed.json").write_text(json.dumps({"installed_unix": 10, "token": "SUPERSECRET"}), encoding="utf-8")
    pipe = PipeFeed(tmp_path, link, enabled=True, proc_start=lambda pid: 20)
    assert pipe.active(100) is True
    assert "SUPERSECRET" not in pipe.reason
    assert "4242" in pipe.reason
