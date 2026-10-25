"""Thermal pause policy.

The action is `pause_reporting` or `report`. There is no terminate action.
A hot reading pauses outbound reports and leaves the process running.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PauseDecision:
    action: str
    sensor: str | None
    temp_c: float | None
    threshold_c: float
    resume_c: float
    reason: str | None

    def __post_init__(self) -> None:
        if self.action not in ("report", "pause_reporting"):
            raise ValueError("pause action must be report or pause_reporting")

    @property
    def paused(self) -> bool:
        return self.action == "pause_reporting"


def _finite(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def decide_pause(
    readings: list[tuple[str, float]],
    *,
    threshold_c: float,
    resume_c: float,
    currently_paused: bool,
) -> PauseDecision:
    """Decide whether outbound reporting should pause.

    Pause when the hottest reading is >= `threshold_c`. Resume when it is
    <= `resume_c`. With no reading, an active reporter stays active and a
    paused reporter stays paused until a real reading cools off.
    """
    if resume_c >= threshold_c:
        raise ValueError("resume temperature must be lower than the pause threshold")
    clean: list[tuple[str, float]] = []
    for name, value in readings:
        number = _finite(value)
        if number is None:
            continue
        clean.append((str(name), number))
    if not clean:
        if currently_paused:
            return PauseDecision(
                "pause_reporting",
                None,
                None,
                threshold_c,
                resume_c,
                "temperature sensor unavailable; reporting stays paused; process left running",
            )
        return PauseDecision("report", None, None, threshold_c, resume_c, None)
    sensor, temp = max(clean, key=lambda item: item[1])
    if currently_paused:
        if temp <= resume_c:
            return PauseDecision("report", sensor, temp, threshold_c, resume_c, None)
        return PauseDecision(
            "pause_reporting",
            sensor,
            temp,
            threshold_c,
            resume_c,
            f"{sensor} {temp:.1f} C still above resume {resume_c:.1f} C; reporting paused; process left running",
        )
    if temp >= threshold_c:
        return PauseDecision(
            "pause_reporting",
            sensor,
            temp,
            threshold_c,
            resume_c,
            f"{sensor} {temp:.1f} C >= pause {threshold_c:.1f} C; reporting paused; process left running",
        )
    return PauseDecision("report", sensor, temp, threshold_c, resume_c, None)


def fresh_readings(sample: dict, sensors: tuple[str, ...] | list[str], *, max_age_s: float) -> list[tuple[str, float]]:
    """Readings eligible for the pause rule. Undated or stale temperatures are ignored."""
    age = _finite(sample.get("thermal_age_s"))
    if age is None or age < 0 or age > max_age_s:
        return []
    found: list[tuple[str, float]] = []
    for name in sensors:
        number = _finite(sample.get(name))
        if number is None:
            continue
        found.append((name, number))
    return found
