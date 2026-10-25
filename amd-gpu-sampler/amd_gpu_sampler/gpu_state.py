"""GPU_Pipes snapshot shared with poller.ps1.

The PowerShell poller is what runs on the Windows machines. This builder is the
tested specification for the same JSON object: utilization, VRAM, temperature,
and the 78C pause flag.
"""

from __future__ import annotations

import math
import re
import time

from amd_gpu_sampler.chain import now_iso
from amd_gpu_sampler.config import DEFAULT_THERMAL_PAUSE_CELSIUS, DEFAULT_THERMAL_RESUME_CELSIUS
from amd_gpu_sampler.schema import SchemaError, validate_gpu_state
from amd_gpu_sampler.thermal import decide_pause

_GPU_NUM = re.compile(r"(\d{4})")


def short_gpu_name(name: str | None) -> str:
    """Label a Radeon name the way the poller does: 'RX 7900 XTX' -> 'RX 79xx'."""
    if not name:
        return "GPU"
    match = _GPU_NUM.search(name)
    if not match:
        return "GPU"
    return f"RX {match.group(1)[:2]}xx"


def _temp(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def build_gpu_state(
    *,
    machine: str,
    role: str,
    gpu_name: str | None,
    util_3d: float,
    util_compute: float,
    vram_bytes: float,
    gpu_core_c: float | None = None,
    gpu_junction_c: float | None = None,
    cpu_core_c: float | None = None,
    include_junction: bool = False,
    currently_paused: bool = False,
    thermal_pause_c: float = DEFAULT_THERMAL_PAUSE_CELSIUS,
    thermal_resume_c: float = DEFAULT_THERMAL_RESUME_CELSIUS,
    job: str | None = None,
    temp_source: str | None = None,
    now: float | None = None,
    ts: str | None = None,
) -> dict:
    """Build a `gpu_state/1` object.

    Pause inputs are GPU core and CPU core. Junction/hotspot is shown in
    `temp_c` when it is the only GPU temperature, and it does not pause
    reporting unless `include_junction` is set.
    """
    core = _temp(gpu_core_c)
    junction = _temp(gpu_junction_c)
    cpu = _temp(cpu_core_c)
    display = core if core is not None else junction
    pause_inputs: list[tuple[str, float]] = []
    if core is not None:
        pause_inputs.append(("gpu_core_c", core))
    if cpu is not None:
        pause_inputs.append(("cpu_core_c", cpu))
    if include_junction and junction is not None:
        pause_inputs.append(("gpu_junction_c", junction))
    decision = decide_pause(
        pause_inputs,
        threshold_c=thermal_pause_c,
        resume_c=thermal_resume_c,
        currently_paused=currently_paused,
    )
    hottest_core = max((value for _, value in pause_inputs), default=None)
    if temp_source is None:
        temp_source = "LibreHardwareMonitor" if any(item is not None for item in (core, junction, cpu)) else "unavailable"
    vram = max(0.0, float(vram_bytes))
    state = {
        "schema": "gpu_state/1",
        "machine": machine,
        "gpu": short_gpu_name(gpu_name),
        "role": role,
        "util_pct": round(min(100.0, max(float(util_3d), float(util_compute), 0.0)), 1),
        "vram_used_gb": round(vram / float(1024**3), 1),
        "vram_used_mb": int(round(vram / float(1024**2))),
        "temp_c": None if display is None else round(display, 1),
        "core_temp_c": None if hottest_core is None else round(hottest_core, 1),
        "temp_source": temp_source,
        "reporting_paused": decision.paused,
        "pause_reason": decision.reason if decision.paused else None,
        "thermal_pause_c": float(thermal_pause_c),
        "thermal_resume_c": float(thermal_resume_c),
        "job": job,
        "ts": ts or now_iso(now if now is not None else time.time()),
        "source": "win-perfcounters",
    }
    errors = validate_gpu_state(state)
    if errors:
        raise SchemaError(errors)
    return state
