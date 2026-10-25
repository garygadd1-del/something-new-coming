"""JSON shapes for the inner-world snapshot and the GPU_Pipes poller file.

Validators are intentionally small and dependency-free so CI can run them
without an AMD GPU. `assemble_sampler_state` is what the sampler writes.
"""

from __future__ import annotations

import math
import re

from amd_gpu_sampler.thermal import PauseDecision

SCHEMA_SAMPLER = "inner_world/1"
SCHEMA_GPU_STATE = "gpu_state/1"
LEVELS = ("ok", "watch", "warn", "critical")
MACHINE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
ROLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _+./-]{0,79}$")
_HEX16 = re.compile(r"^[0-9a-f]{16}$")


class SchemaError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _req(errors: list[str], obj: dict, key: str, prefix: str) -> bool:
    if not isinstance(obj, dict) or key not in obj:
        errors.append(f"{prefix}{key} is missing")
        return False
    return True


def _check_num(errors, obj, key, prefix, lo, hi, *, allow_none=False) -> None:
    label = f"{prefix}{key}"
    if not _req(errors, obj, key, prefix):
        return
    value = obj[key]
    if value is None and allow_none:
        return
    if not _num(value) or not lo <= float(value) <= hi:
        errors.append(f"{label} is out of range")


def _check_str(errors, obj, key, prefix, limit: int, *, allow_none=False) -> None:
    label = f"{prefix}{key}"
    if not _req(errors, obj, key, prefix):
        return
    value = obj[key]
    if value is None and allow_none:
        return
    if not isinstance(value, str) or not value or len(value) > limit:
        errors.append(f"{label} must be a short string")


def validate_sampler_state(state: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(state, dict):
        return ["state must be an object"]
    if state.get("schema") != SCHEMA_SAMPLER:
        errors.append("schema must be inner_world/1")
    _check_str(errors, state, "ts", "", 40)
    _check_num(errors, state, "unix", "", 0, 10**11)
    if state.get("level") not in LEVELS:
        errors.append("level is not a known severity")
    _check_str(errors, state, "felt", "", 200)
    _check_str(errors, state, "expect", "", 64)
    if state.get("reporting") not in ("active", "paused"):
        errors.append("reporting must be active or paused")
    signals = state.get("signals")
    if not isinstance(signals, list) or len(signals) > 8:
        errors.append("signals must be a short list")
    else:
        for index, item in enumerate(signals):
            if not isinstance(item, dict):
                errors.append(f"signals[{index}] must be an object")
                continue
            _check_str(errors, item, "id", f"signals[{index}].", 64)
            if item.get("level") not in LEVELS:
                errors.append(f"signals[{index}].level is not a known severity")
            _check_str(errors, item, "msg", f"signals[{index}].", 300)
    gpu = state.get("gpu") if isinstance(state.get("gpu"), dict) else None
    if gpu is None:
        errors.append("gpu is missing")
    else:
        _check_num(errors, gpu, "util_pct", "gpu.", 0, 100)
        _check_num(errors, gpu, "vram_used_mb", "gpu.", 0, 10**7)
        _check_num(errors, gpu, "vram_total_mb", "gpu.", 0, 10**7)
        _check_num(errors, gpu, "vram_free_mb", "gpu.", 0, 10**7)
        _check_num(errors, gpu, "temp_c", "gpu.", -40, 150, allow_none=True)
        _check_num(errors, gpu, "power_w", "gpu.", 0, 2000, allow_none=True)
        if _num(gpu.get("vram_used_mb")) and _num(gpu.get("vram_total_mb")) and _num(gpu.get("vram_free_mb")):
            expected = max(0, int(gpu["vram_total_mb"]) - int(gpu["vram_used_mb"]))
            if int(gpu["vram_free_mb"]) != expected:
                errors.append("gpu.vram_free_mb does not match total minus used")
    ram = state.get("ram") if isinstance(state.get("ram"), dict) else None
    if ram is None:
        errors.append("ram is missing")
    else:
        _check_num(errors, ram, "avail_mb", "ram.", 0, 10**8)
        _check_num(errors, ram, "commit_pct", "ram.", 0, 100)
        _check_num(errors, ram, "hard_faults_s", "ram.", 0, 10**9)
        _check_num(errors, ram, "page_faults_s", "ram.", 0, 10**9)
    cpu = state.get("cpu") if isinstance(state.get("cpu"), dict) else None
    if cpu is None:
        errors.append("cpu is missing")
    else:
        _check_num(errors, cpu, "util_pct", "cpu.", 0, 100)
        _check_num(errors, cpu, "max_core_pct", "cpu.", 0, 100)
        _check_num(errors, cpu, "queue", "cpu.", 0, 10**7)
        _check_num(errors, cpu, "dpc_irq_pct", "cpu.", 0, 1000)
        _check_num(errors, cpu, "freq_mhz", "cpu.", 0, 20000)
        _check_num(errors, cpu, "perf_limit_pct", "cpu.", 0, 100)
    godot = state.get("godot") if isinstance(state.get("godot"), dict) else None
    if godot is None:
        errors.append("godot is missing")
    else:
        _check_num(errors, godot, "pid", "godot.", 0, 2**31)
        _check_num(errors, godot, "alive_age_s", "godot.", 0, 10**7, allow_none=True)
        _check_num(errors, godot, "cpu_core_pct", "godot.", 0, 100000)
        _check_num(errors, godot, "ws_mb", "godot.", 0, 10**7)
        _check_num(errors, godot, "gpu_pct", "godot.", 0, 100)
        if not isinstance(godot.get("stalled"), bool):
            errors.append("godot.stalled must be a boolean")
    jitter = state.get("jitter") if isinstance(state.get("jitter"), dict) else None
    if jitter is None:
        errors.append("jitter is missing")
    else:
        _check_num(errors, jitter, "p99_ms", "jitter.", 0, 10**7)
        _check_num(errors, jitter, "max_ms_60s", "jitter.", 0, 10**7)
    blackout = state.get("last_blackout")
    if blackout is not None:
        if not isinstance(blackout, dict):
            errors.append("last_blackout must be an object or null")
        else:
            _check_str(errors, blackout, "ts", "last_blackout.", 40)
            _check_num(errors, blackout, "gap_ms", "last_blackout.", 0, 10**10)
            _check_str(errors, blackout, "kind", "last_blackout.", 64)
            _check_str(errors, blackout, "top_cause", "last_blackout.", 64)
            _check_str(errors, blackout, "why", "last_blackout.", 400)
    meta = state.get("sampler") if isinstance(state.get("sampler"), dict) else None
    if meta is None:
        errors.append("sampler is missing")
    else:
        _check_num(errors, meta, "pid", "sampler.", 0, 2**31)
        _check_num(errors, meta, "self_cpu_pct", "sampler.", 0, 100000)
        _check_str(errors, meta, "pipe_feed", "sampler.", 240)
        _check_num(errors, meta, "pipe_sent", "sampler.", 0, 10**12)
        _check_num(errors, meta, "chain_seq", "sampler.", 0, 10**12)
        if not _req(errors, meta, "chain_hash", "sampler."):
            pass
        elif not isinstance(meta.get("chain_hash"), str) or not _HEX16.fullmatch(meta["chain_hash"]):
            errors.append("sampler.chain_hash must be 16 hex characters")
        _check_num(errors, meta, "thermal_pause_c", "sampler.", 0, 120)
        _check_num(errors, meta, "thermal_resume_c", "sampler.", 0, 120)
    pause = state.get("pause", "missing")
    if pause == "missing":
        errors.append("pause is missing")
    elif state.get("reporting") == "active":
        if pause is not None:
            errors.append("pause must be null while reporting is active")
    elif state.get("reporting") == "paused":
        if not isinstance(pause, dict):
            errors.append("pause must explain a paused report")
        else:
            _check_str(errors, pause, "reason", "pause.", 300)
            if pause.get("sensor") is not None and not isinstance(pause.get("sensor"), str):
                errors.append("pause.sensor must be a string or null")
            _check_num(errors, pause, "temp_c", "pause.", -40, 150, allow_none=True)
            _check_num(errors, pause, "threshold_c", "pause.", 0, 120)
            _check_num(errors, pause, "resume_below_c", "pause.", 0, 120)
            _check_str(errors, pause, "since", "pause.", 40)
    return errors


def _clamp(value, lo: float, hi: float, default: float = 0.0) -> float:
    if not _num(value):
        return default
    return max(lo, min(hi, float(value)))


def _itemp(value):
    if not _num(value):
        return None
    number = float(value)
    if not -40 <= number <= 150:
        return None
    return round(number, 1)


def assemble_sampler_state(
    *,
    sample: dict,
    signals: list[dict],
    level: int,
    felt: str,
    expect: str,
    godot_pid: int,
    godot_age,
    heartbeat: dict,
    last_blackout,
    pause: PauseDecision,
    pause_since: str | None,
    sampler_meta: dict,
    ts: str,
    unix: float,
) -> dict:
    ranked = [item for item in sorted(signals, key=lambda item: -item["level"]) if item["level"] > 0][:4]
    used = int(round(_clamp(sample.get("gpu_used_mb"), 0, 10**7)))
    total = int(round(_clamp(sample.get("gpu_total_mb"), 0, 10**7)))
    free = max(0, total - used)
    age = godot_age if _num(godot_age) and float(godot_age) >= 0 else None
    state = {
        "schema": SCHEMA_SAMPLER,
        "ts": ts,
        "unix": round(float(unix), 1),
        "level": LEVELS[level] if 0 <= level < len(LEVELS) else "ok",
        "felt": (felt or "")[:200] or "quiet",
        "expect": (expect or "none")[:64],
        "reporting": "paused" if pause.paused else "active",
        "pause": None
        if not pause.paused
        else {
            "reason": (pause.reason or "reporting paused")[:300],
            "sensor": pause.sensor,
            "temp_c": None if pause.temp_c is None else round(float(pause.temp_c), 1),
            "threshold_c": pause.threshold_c,
            "resume_below_c": pause.resume_c,
            "since": pause_since or ts,
        },
        "signals": [{"id": item["id"][:64], "level": LEVELS[item["level"]], "msg": item["msg"][:300]} for item in ranked],
        "gpu": {
            "util_pct": round(_clamp(sample.get("gpu_busy"), 0, 100), 1),
            "vram_used_mb": used,
            "vram_total_mb": total,
            "vram_free_mb": free,
            "temp_c": _itemp(sample.get("gpu_junction_c")),
            "power_w": round(float(sample["gpu_power_w"]), 1) if _num(sample.get("gpu_power_w")) and 0 <= float(sample["gpu_power_w"]) <= 2000 else None,
        },
        "ram": {
            "avail_mb": int(round(_clamp(sample.get("avail_mb"), 0, 10**8))),
            "commit_pct": round(_clamp(sample.get("commit_pct"), 0, 100), 1),
            "hard_faults_s": round(_clamp(sample.get("pages_in_s"), 0, 10**9), 1),
            "page_faults_s": int(round(_clamp(sample.get("pf_s"), 0, 10**9))),
        },
        "cpu": {
            "util_pct": round(_clamp(sample.get("cpu"), 0, 100), 1),
            "max_core_pct": int(round(_clamp(sample.get("cpu_max_core"), 0, 100))),
            "queue": int(round(_clamp(sample.get("queue"), 0, 10**7))),
            "dpc_irq_pct": round(_clamp(sample.get("dpc", 0) + sample.get("irq", 0), 0, 1000), 2),
            "freq_mhz": int(round(_clamp(sample.get("freq_mhz"), 0, 20000))),
            "perf_limit_pct": round(_clamp(sample.get("perf_limit"), 0, 100, default=100.0), 1),
        },
        "godot": {
            "pid": int(_clamp(godot_pid, 0, 2**31)),
            "alive_age_s": None if age is None else round(float(age), 2),
            "cpu_core_pct": round(_clamp(sample.get("godot_cpu_core_pct"), 0, 100000), 1),
            "ws_mb": int(round(_clamp(sample.get("godot_ws_mb"), 0, 10**7))),
            "gpu_pct": round(_clamp(sample.get("godot_gpu"), 0, 100), 1),
            "stalled": bool(age is not None and age > 4.0),
        },
        "jitter": {
            "p99_ms": round(_clamp(heartbeat.get("p99_ms"), 0, 10**7), 1),
            "max_ms_60s": round(_clamp(heartbeat.get("max_ms"), 0, 10**7), 1),
        },
        "last_blackout": last_blackout,
        "sampler": {
            "pid": int(sampler_meta["pid"]),
            "self_cpu_pct": round(_clamp(sampler_meta.get("self_cpu_pct"), 0, 100000), 2),
            "pipe_feed": str(sampler_meta.get("pipe_feed") or "not checked")[:240],
            "pipe_sent": int(_clamp(sampler_meta.get("pipe_sent"), 0, 10**12)),
            "chain_seq": int(_clamp(sampler_meta.get("chain_seq"), 0, 10**12)),
            "chain_hash": str(sampler_meta.get("chain_hash") or "0" * 16)[:16],
            "thermal_pause_c": float(sampler_meta["thermal_pause_c"]),
            "thermal_resume_c": float(sampler_meta["thermal_resume_c"]),
        },
    }
    errors = validate_sampler_state(state)
    if errors:
        raise SchemaError(errors)
    return state


def validate_gpu_state(state: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(state, dict):
        return ["gpu state must be an object"]
    if state.get("schema") != SCHEMA_GPU_STATE:
        errors.append("schema must be gpu_state/1")
    if not isinstance(state.get("machine"), str) or not MACHINE_RE.fullmatch(state.get("machine", "")):
        errors.append("machine must be a short hostname label")
    _check_str(errors, state, "gpu", "", 40)
    if not isinstance(state.get("role"), str) or not ROLE_RE.fullmatch(state.get("role", "")):
        errors.append("role must be a single short line")
    _check_num(errors, state, "util_pct", "", 0, 100)
    _check_num(errors, state, "vram_used_gb", "", 0, 1024)
    _check_num(errors, state, "vram_used_mb", "", 0, 1024 * 1024)
    _check_num(errors, state, "temp_c", "", -40, 150, allow_none=True)
    _check_num(errors, state, "core_temp_c", "", -40, 150, allow_none=True)
    if state.get("temp_source") not in ("LibreHardwareMonitor", "unavailable"):
        errors.append("temp_source is not recognized")
    if not isinstance(state.get("reporting_paused"), bool):
        errors.append("reporting_paused must be a boolean")
    if state.get("reporting_paused") is True:
        _check_str(errors, state, "pause_reason", "", 300)
    elif state.get("pause_reason") is not None:
        errors.append("pause_reason must be null while reporting")
    _check_num(errors, state, "thermal_pause_c", "", 0, 120)
    _check_num(errors, state, "thermal_resume_c", "", 0, 120)
    if state.get("job") is not None and (not isinstance(state.get("job"), str) or len(state["job"]) > 80 or "\n" in state["job"]):
        errors.append("job must be a short string or null")
    _check_str(errors, state, "ts", "", 40)
    if state.get("source") != "win-perfcounters":
        errors.append("source must be win-perfcounters")
    return errors
