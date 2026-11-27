"""Sampler configuration.

Gary's 78C pause rule lives here as data. Crossing the threshold pauses outbound
reporting. It does not stop the process and it does not kill a workload.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from amd_gpu_sampler.safety import SafetyError, assert_no_traversal

# Hottest GPU-core / CPU-core temperature at which outbound reporting pauses.
# Junction/hotspot is intentionally not in the default set: a 7900-class junction
# runs hotter than the core and would pause a healthy card.
DEFAULT_THERMAL_PAUSE_CELSIUS = 78.0
DEFAULT_THERMAL_RESUME_CELSIUS = 75.0
DEFAULT_THERMAL_MAX_AGE_S = 30.0
DEFAULT_VRAM_TOTAL_MB = 24560

ALLOWED_SENSORS = ("gpu_edge_c", "gpu_junction_c", "cpu_core_c")
DEFAULT_SENSORS = ("gpu_edge_c", "cpu_core_c")

_ALLOWED_KEYS = {
    "sample_hz",
    "thermal_pause_celsius",
    "thermal_resume_celsius",
    "thermal_max_age_s",
    "thermal_sensors",
    "vram_total_mb_fallback",
    "godot_link_dir",
    "thermal_file",
    "pipe_enabled",
    "bridge_port",
    "work_dir",
    "machine_label",
}


def _as_float(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SafetyError(f"{name} must be a number")
    return float(value)


def _as_bool(value, name: str) -> bool:
    if not isinstance(value, bool):
        raise SafetyError(f"{name} must be a boolean")
    return value


@dataclass
class SamplerConfig:
    sample_hz: float = 1.0
    thermal_pause_celsius: float = DEFAULT_THERMAL_PAUSE_CELSIUS
    thermal_resume_celsius: float = DEFAULT_THERMAL_RESUME_CELSIUS
    thermal_max_age_s: float = DEFAULT_THERMAL_MAX_AGE_S
    thermal_sensors: tuple[str, ...] = DEFAULT_SENSORS
    vram_total_mb_fallback: int = DEFAULT_VRAM_TOTAL_MB
    godot_link_dir: str = r"C:\AGIOS\ara_body\link"
    thermal_file: str = r"C:\AGIOS\Ara_Brain\state\ara_thermal.json"
    pipe_enabled: bool = True
    bridge_port: int = 0
    work_dir: str = ""
    machine_label: str = ""

    def __post_init__(self) -> None:
        self.sample_hz = _as_float(self.sample_hz, "sample_hz")
        self.thermal_pause_celsius = _as_float(self.thermal_pause_celsius, "thermal_pause_celsius")
        self.thermal_resume_celsius = _as_float(self.thermal_resume_celsius, "thermal_resume_celsius")
        self.thermal_max_age_s = _as_float(self.thermal_max_age_s, "thermal_max_age_s")
        if isinstance(self.vram_total_mb_fallback, bool) or not isinstance(self.vram_total_mb_fallback, int):
            raise SafetyError("vram_total_mb_fallback must be an integer")
        if isinstance(self.bridge_port, bool) or not isinstance(self.bridge_port, int):
            raise SafetyError("bridge_port must be an integer")
        self.pipe_enabled = _as_bool(self.pipe_enabled, "pipe_enabled")
        if isinstance(self.thermal_sensors, str) or not isinstance(self.thermal_sensors, (list, tuple)):
            raise SafetyError("thermal_sensors must be a list")
        self.thermal_sensors = tuple(self.thermal_sensors)
        self._validate()

    def _validate(self) -> None:
        if not 0.1 <= self.sample_hz <= 5:
            raise SafetyError("sample_hz must be between 0.1 and 5")
        if not 0 <= self.thermal_resume_celsius < self.thermal_pause_celsius <= 120:
            raise SafetyError("thermal_resume_celsius must be lower than thermal_pause_celsius, and pause must be <= 120")
        if not 1 <= self.thermal_max_age_s <= 300:
            raise SafetyError("thermal_max_age_s must be between 1 and 300")
        if not self.thermal_sensors:
            raise SafetyError("thermal_sensors must name at least one sensor")
        unknown = [name for name in self.thermal_sensors if name not in ALLOWED_SENSORS]
        if unknown:
            raise SafetyError(f"unknown thermal sensor: {unknown[0]}")
        if not 256 <= self.vram_total_mb_fallback <= 131072:
            raise SafetyError("vram_total_mb_fallback is out of range")
        if self.bridge_port != 0 and not 1 <= self.bridge_port <= 65535:
            raise SafetyError("bridge_port must be 0 (off) or a TCP port")
        if self.thermal_file:
            path = assert_no_traversal(self.thermal_file)
            if path.suffix.lower() != ".json":
                raise SafetyError("thermal_file must be a .json path")
        if self.godot_link_dir:
            assert_no_traversal(self.godot_link_dir)
        if self.work_dir:
            assert_no_traversal(self.work_dir)
        if self.machine_label and not _machine_ok(self.machine_label):
            raise SafetyError("machine_label has unsupported characters")


def _machine_ok(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}", value))


def load_config(path: Path | None, overrides: dict | None = None) -> SamplerConfig:
    """Load JSON config. Unknown keys are rejected so a misspelled threshold cannot fall back silently."""
    data: dict = {}
    if path is not None:
        assert_no_traversal(str(path))
        with open(path, encoding="utf-8-sig") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, dict):
            raise SafetyError("config must be a JSON object")
        unexpected = sorted(set(loaded) - _ALLOWED_KEYS)
        if unexpected:
            raise SafetyError(f"unknown config key: {unexpected[0]}")
        data.update(loaded)
    if overrides:
        unexpected = sorted(set(overrides) - _ALLOWED_KEYS)
        if unexpected:
            raise SafetyError(f"unknown config key: {unexpected[0]}")
        data.update({key: value for key, value in overrides.items() if value is not None})
    return SamplerConfig(**data)
