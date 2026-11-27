"""Scheduling heartbeat. It measures how late this process woke up. It does not change priority."""

from __future__ import annotations

import collections
import threading
import time


class Heartbeat(threading.Thread):
    def __init__(self, period: float = 0.1, gap_s: float = 0.5):
        super().__init__(daemon=True, name="heartbeat")
        self.period = period
        self.gap_s = gap_s
        self.ring = collections.deque(maxlen=600)
        self.events = collections.deque(maxlen=50)
        self.stop_ev = threading.Event()

    def run(self) -> None:
        last = time.perf_counter()
        last_wall = time.time()
        while not self.stop_ev.is_set():
            self.stop_ev.wait(self.period)
            now = time.perf_counter()
            wall = time.time()
            delta = now - last
            self.ring.append((wall, (delta - self.period) * 1000.0))
            if delta > self.gap_s:
                self.events.append(
                    {
                        "kind": "heartbeat_gap",
                        "at": wall,
                        "gap_ms": round(delta * 1000.0),
                        "wall_ms": round((wall - last_wall) * 1000.0),
                    }
                )
            last = now
            last_wall = wall

    def stats(self) -> dict:
        values = sorted(overshoot for _, overshoot in list(self.ring))
        if not values:
            return {"p99_ms": 0.0, "max_ms": 0.0, "mean_ms": 0.0}
        index = int(len(values) * 0.99) - 1 if len(values) > 1 else 0
        index = max(0, index)
        return {
            "p99_ms": round(max(0.0, values[index]), 1),
            "max_ms": round(max(0.0, values[-1]), 1),
            "mean_ms": round(max(0.0, sum(values) / len(values)), 2),
        }

    def pop_events(self) -> list:
        found = list(self.events)
        self.events.clear()
        return found

    def stop(self) -> None:
        self.stop_ev.set()


class NullHeartbeat:
    """Stand-in for tests so they do not start a thread."""

    def stats(self) -> dict:
        return {"p99_ms": 0.0, "max_ms": 0.0, "mean_ms": 0.0}

    def pop_events(self) -> list:
        return []

    def stop(self) -> None:
        return None
