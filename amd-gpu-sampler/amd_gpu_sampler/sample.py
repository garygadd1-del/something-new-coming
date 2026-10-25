"""Build one health sample from counter rows and an optional thermal file.

This module only interprets numbers. It does not start processes or open sockets.
"""

from __future__ import annotations

import collections
import math
import re


def fnum(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def finite_or_none(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _group(cols, row) -> dict:
    grouped: dict = {}
    for spec, raw in zip(cols, row[1:]):
        obj, inst, ctr = spec
        grouped.setdefault((obj, ctr), []).append((inst, fnum(raw)))
    return grouped


def _one(grouped, obj: str, ctr: str, inst: str | None = "_total", default: float = 0.0) -> float:
    for name, value in grouped.get((obj, ctr), []):
        if inst is None or name == inst:
            return value
    return default


def _blank(t: float, recv: float) -> dict:
    age = round(t - recv, 2) if recv else 99.0
    return {
        "t": t,
        "tp_age_s": age,
        "avail_mb": 0,
        "commit_gb": 0.0,
        "commit_pct": 0.0,
        "pf_s": 0,
        "pages_in_s": 0.0,
        "pages_s": 0.0,
        "standby_mb": 0,
        "free_mb": 0,
        "modified_mb": 0,
        "cpu": 0.0,
        "cores": [],
        "cpu_max_core": 0,
        "dpc": 0.0,
        "irq": 0.0,
        "freq_mhz": 0,
        "perf_pct": 0.0,
        "perf_limit": 100.0,
        "queue": 0,
        "ctx_s": 0,
        "sysc_s": 0,
        "gpu_used_mb": 0,
        "gpu_total_mb": 0,
        "gpu_3d": 0.0,
        "gpu_compute": 0.0,
        "gpu_copy": 0.0,
        "gpu_busy": 0.0,
        "godot_gpu": 0.0,
        "godot_vram_mb": 0,
        "godot_cpu_core_pct": 0.0,
        "godot_ws_mb": 0,
        "godot_pf_s": 0,
        "gpu_edge_c": None,
        "gpu_junction_c": None,
        "gpu_power_w": None,
        "gpu_fan_rpm": None,
        "cpu_core_c": None,
        "thermal_age_s": None,
        "counters_ok": False,
    }


def _apply_thermal_temps(sample: dict, thermal: dict | None, t: float) -> None:
    if not isinstance(thermal, dict):
        return
    gpu = thermal.get("gpu") if isinstance(thermal.get("gpu"), dict) else {}
    sample["gpu_edge_c"] = finite_or_none(gpu.get("edge_c"))
    sample["gpu_junction_c"] = finite_or_none(gpu.get("junction_c"))
    sample["gpu_power_w"] = finite_or_none(gpu.get("power_w"))
    sample["gpu_fan_rpm"] = finite_or_none(gpu.get("fan_rpm"))
    cpu = thermal.get("cpu") if isinstance(thermal.get("cpu"), dict) else {}
    cores = cpu.get("cores_c")
    numbers = []
    if isinstance(cores, list):
        numbers = [float(item) for item in cores if finite_or_none(item) is not None]
    if numbers:
        sample["cpu_core_c"] = max(numbers)
    else:
        sample["cpu_core_c"] = finite_or_none(cpu.get("core_c"))
    stamped = finite_or_none(thermal.get("t"))
    sample["thermal_age_s"] = round(t - stamped, 1) if stamped is not None else None


def _engine_max(engines: dict, kind: str) -> float:
    values = [min(100.0, value) for key, value in engines.items() if str(key).endswith("engtype_" + kind)]
    return max(values) if values else 0.0


def build_sample(
    *,
    cols,
    row,
    recv: float,
    t: float,
    thermal: dict | None,
    godot_pid: int,
    godot_cols,
    godot_row,
    godot_recv: float,
    vram_total_mb_fallback: int,
) -> dict:
    """Return a flat sample. `gpu_free_mb` is present only when a counter row exists.

    Missing VRAM is omitted on purpose: a zero would look like a full GPU.
    Temperatures are still copied when counters are down, so the pause rule can see them.
    """
    sample = _blank(t, recv)
    _apply_thermal_temps(sample, thermal, t)
    if not cols or not row:
        return sample
    grouped = _group(cols, row)
    sample["counters_ok"] = True
    sample["avail_mb"] = round(_one(grouped, "memory", "available mbytes", None))
    sample["commit_gb"] = round(_one(grouped, "memory", "committed bytes", None) / 2**30, 2)
    sample["commit_pct"] = round(_one(grouped, "memory", "% committed bytes in use", None), 1)
    sample["pf_s"] = round(_one(grouped, "memory", "page faults/sec", None))
    sample["pages_in_s"] = round(_one(grouped, "memory", "pages input/sec", None), 1)
    sample["pages_s"] = round(_one(grouped, "memory", "pages/sec", None), 1)
    standby = sum(
        _one(grouped, "memory", name, None)
        for name in (
            "standby cache normal priority bytes",
            "standby cache reserve bytes",
            "standby cache core bytes",
        )
    )
    sample["standby_mb"] = round(standby / 2**20)
    sample["free_mb"] = round(_one(grouped, "memory", "free & zero page list bytes", None) / 2**20)
    sample["modified_mb"] = round(_one(grouped, "memory", "modified page list bytes", None) / 2**20)
    utilities = grouped.get(("processor information", "% processor utility"), [])
    cores = [value for inst, value in utilities if re.fullmatch(r"\d+,\d+", inst)]
    sample["cpu"] = round(min(100.0, max(0.0, _one(grouped, "processor information", "% processor utility"))), 1)
    sample["cores"] = [int(min(100, max(0, round(value)))) for value in cores[:256]]
    sample["cpu_max_core"] = max(sample["cores"]) if sample["cores"] else 0
    sample["dpc"] = round(max(0.0, _one(grouped, "processor information", "% dpc time")), 2)
    sample["irq"] = round(max(0.0, _one(grouped, "processor information", "% interrupt time")), 2)
    sample["freq_mhz"] = round(max(0.0, _one(grouped, "processor information", "processor frequency")))
    sample["perf_pct"] = round(max(0.0, _one(grouped, "processor information", "% processor performance")), 1)
    sample["perf_limit"] = round(_one(grouped, "processor information", "% performance limit", default=100.0), 1)
    sample["queue"] = round(max(0.0, _one(grouped, "system", "processor queue length", None)))
    sample["ctx_s"] = round(max(0.0, _one(grouped, "system", "context switches/sec", None)))
    sample["sysc_s"] = round(max(0.0, _one(grouped, "system", "system calls/sec", None)))

    adapters = grouped.get(("gpu adapter memory", "dedicated usage"), [])
    luid = ""
    used = 0.0
    for inst, value in adapters:
        if value >= used:
            used, luid = value, inst
    key = re.sub(r"_phys_\d+$", "", luid)
    sample["gpu_used_mb"] = round(max(0.0, used) / 2**20)
    gpu = thermal.get("gpu") if isinstance(thermal, dict) else None
    if not isinstance(gpu, dict):
        gpu = {}
    total = finite_or_none(gpu.get("vram_total_mb"))
    sample["gpu_total_mb"] = int(total) if total and total > 0 else int(vram_total_mb_fallback)
    sample["gpu_free_mb"] = max(0, sample["gpu_total_mb"] - sample["gpu_used_mb"])

    # Same engine node is summed across processes, then the busiest node of each type is kept.
    engines: dict[str, float] = collections.defaultdict(float)
    godot_engines: dict[str, float] = collections.defaultdict(float)
    for inst, value in grouped.get(("gpu engine", "utilization percentage"), []):
        if key and key not in inst:
            continue
        match = re.search(r"pid_(\d+)_.*?(phys_\d+_eng_\d+_engtype_\w+)$", inst)
        if not match:
            continue
        engines[match.group(2)] += value
        if godot_pid and int(match.group(1)) == godot_pid:
            godot_engines[match.group(2)] += value
    sample["gpu_3d"] = round(_engine_max(engines, "3d"), 1)
    sample["gpu_compute"] = round(_engine_max(engines, "compute"), 1)
    sample["gpu_copy"] = round(_engine_max(engines, "copy"), 1)
    capped = [min(100.0, value) for value in engines.values()]
    sample["gpu_busy"] = round(max(capped) if capped else 0.0, 1)
    godot_capped = [min(100.0, value) for value in godot_engines.values()]
    sample["godot_gpu"] = round(max(godot_capped) if godot_capped else 0.0, 1)
    vram = 0.0
    for inst, value in grouped.get(("gpu process memory", "dedicated usage"), []):
        if godot_pid and f"pid_{godot_pid}_" in inst and (not key or key in inst):
            vram += value
    sample["godot_vram_mb"] = round(max(0.0, vram) / 2**20)

    if godot_cols and godot_row and godot_recv and t - godot_recv < 5:
        cpu_pct = 0.0
        working = 0.0
        faults = 0.0
        for (obj, inst, ctr), raw in zip(godot_cols, godot_row[1:]):
            del obj, inst
            value = fnum(raw)
            if ctr == "% processor time":
                cpu_pct += value
            elif ctr == "working set":
                working += value
            elif ctr == "page faults/sec":
                faults += value
        sample["godot_cpu_core_pct"] = round(max(0.0, cpu_pct), 1)
        sample["godot_ws_mb"] = round(max(0.0, working) / 2**20)
        sample["godot_pf_s"] = round(max(0.0, faults))
    return sample
