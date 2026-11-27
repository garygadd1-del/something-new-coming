"""Signed loopback feed into Godot.

Messages go out only through `ara_pipe.send(..., via="udp")`. This module does
not open key files, does not choose a host, and does not open a network connection of its own.
The signed client is documented as loopback UDP port 18840. If the client is
missing, sends fail closed.
"""

from __future__ import annotations

import sys
from pathlib import Path

from amd_gpu_sampler.process_info import proc_start_unix
from amd_gpu_sampler.safety import assert_not_secret, jload


class PipeFeed:
    def __init__(self, folder: Path, link_dir: Path, enabled: bool = True, sender=None, proc_start=None, force_active: bool = False):
        self.folder = Path(folder)
        self.link_dir = Path(link_dir)
        self.enabled = enabled
        self.sender = sender
        self.proc_start = proc_start or proc_start_unix
        self.force_active = force_active
        self.last_send = 0.0
        self.sent = 0
        self.failed = 0
        self.reason = "not checked"
        self._checked_at = 0.0
        self._ok = False
        self._mod = None

    def active(self, now: float) -> bool:
        if self.force_active:
            self._ok = True
            self.reason = "forced for test"
            return True
        if self._checked_at and now - self._checked_at < 15:
            return self._ok
        self._checked_at = now
        ok = False
        why = ""
        if not self.enabled:
            why = "disabled on the command line"
        elif (self.folder / "pipe_feed.disable").exists():
            why = "pipe_feed.disable present"
        elif (self.folder / "pipe_feed.force").exists():
            ok, why = True, "pipe_feed.force present"
        else:
            installed = _field(self.folder / "godot_handler_installed.json", "installed_unix")
            alive = jload(self.link_dir / "godot_alive.json")
            pid = _pid(alive)
            started = self.proc_start(pid) if pid else None
            if installed is None:
                why = "Godot inner_world handler not installed: feed off"
            elif started is None:
                why = "Godot not running"
            elif started > installed:
                ok, why = True, f"Godot (pid {pid}) started after the handler patch"
            else:
                why = "running Godot started before the handler patch"
        self._ok = ok
        self.reason = why
        return ok

    def maybe_send(self, payload: dict, now: float, level_changed: bool, force: bool = False):
        if not isinstance(payload, dict):
            return False
        if "host" in payload or "url" in payload:
            self.failed += 1
            self.reason = "refusing a payload that names a host"
            return False
        if not force and not self.active(now):
            return None
        if not force and not level_changed and now - self.last_send < 1.0:
            return None
        try:
            client = self.sender if self.sender is not None else self._load()
            ok = bool(client.send(payload, via="udp"))
        except Exception:  # noqa: BLE001 - a failed pipe must not take the sampler down
            ok = False
        self.last_send = now
        if ok:
            self.sent += 1
        else:
            self.failed += 1
        return ok

    def _load(self):
        if self._mod is not None:
            return self._mod
        link = self.link_dir
        assert_not_secret(link)
        entry = link / "ara_pipe.py"
        if not link.is_dir() or not entry.is_file():
            raise ImportError("signed pipe client is not present")
        assert_not_secret(entry)
        folder = str(link)
        if folder not in sys.path:
            sys.path.insert(0, folder)
        import ara_pipe  # type: ignore

        self._mod = ara_pipe
        return self._mod


def compact_message(state: dict, alert: bool) -> dict:
    gpu = state["gpu"]
    ram = state["ram"]
    cpu = state["cpu"]
    return {
        "action": "inner_world",
        "v": 1,
        "ts": state["ts"],
        "level": state["level"],
        "felt": state["felt"],
        "expect": state["expect"],
        "alert": bool(alert),
        "reporting": state.get("reporting", "active"),
        "gpu": {"util": gpu["util_pct"], "vram_free_mb": gpu["vram_free_mb"], "temp_c": gpu["temp_c"]},
        "ram": {"avail_mb": ram["avail_mb"], "commit_pct": ram["commit_pct"], "hard_faults_s": ram["hard_faults_s"]},
        "cpu": {"util": cpu["util_pct"], "queue": cpu["queue"], "dpc_irq": cpu["dpc_irq_pct"]},
        "godot_age_s": state["godot"]["alive_age_s"],
        "last_blackout": state["last_blackout"],
    }


def _field(path: Path, name: str):
    data = jload(path)
    if not isinstance(data, dict) or name not in data:
        return None
    try:
        return float(data[name])
    except (TypeError, ValueError):
        return None


def _pid(data) -> int | None:
    if not isinstance(data, dict):
        return None
    try:
        pid = int(data.get("pid") or 0)
    except (TypeError, ValueError):
        return None
    return pid or None
