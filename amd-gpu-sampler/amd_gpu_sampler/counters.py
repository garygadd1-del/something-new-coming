"""Windows performance-counter reader.

Live collection shells out to `typeperf` with a fixed argument list and no
shell. Tests feed `StaticSource` instead, so CI does not need an AMD GPU.
"""

from __future__ import annotations

import csv
import re
import subprocess
import sys
import threading
import time

from amd_gpu_sampler.safety import SafetyError

CREATE_NO_WINDOW = 0x08000000
_COL = re.compile(r"^\\\\[^\\]+\\([^\\(]+)(?:\(([^)]*)\))?\\(.+)$")

# Fixed counter paths. They are not taken from config or the network.
SYS_COUNTERS = [
    r"\Memory\Available MBytes",
    r"\Memory\Committed Bytes",
    r"\Memory\% Committed Bytes In Use",
    r"\Memory\Page Faults/sec",
    r"\Memory\Pages Input/sec",
    r"\Memory\Pages/sec",
    r"\Memory\Standby Cache Normal Priority Bytes",
    r"\Memory\Standby Cache Reserve Bytes",
    r"\Memory\Standby Cache Core Bytes",
    r"\Memory\Free & Zero Page List Bytes",
    r"\Memory\Modified Page List Bytes",
    r"\Processor Information(*)\% Processor Utility",
    r"\Processor Information(_Total)\% DPC Time",
    r"\Processor Information(_Total)\% Interrupt Time",
    r"\Processor Information(_Total)\Processor Frequency",
    r"\Processor Information(_Total)\% Processor Performance",
    r"\Processor Information(_Total)\% Performance Limit",
    r"\System\Processor Queue Length",
    r"\System\Context Switches/sec",
    r"\System\System Calls/sec",
    r"\GPU Adapter Memory(*)\Dedicated Usage",
    r"\GPU Engine(*)\Utilization Percentage",
    r"\GPU Process Memory(*)\Dedicated Usage",
]
GODOT_COUNTERS = [
    r"\Process(Godot*)\% Processor Time",
    r"\Process(Godot*)\Working Set",
    r"\Process(Godot*)\Page Faults/sec",
]


def typeperf_argv(counters: list[str]) -> list[str]:
    if not counters:
        raise SafetyError("typeperf needs at least one counter")
    for counter in counters:
        if not isinstance(counter, str) or not counter.startswith("\\"):
            raise SafetyError("counter path must be a PDH path")
        if counter.startswith("-") or "\n" in counter or "\r" in counter or "\x00" in counter:
            raise SafetyError("refusing counter path")
    return ["typeperf", *counters, "-si", "1"]


def parse_typeperf_header(line: str) -> list[tuple[str, str, str]] | None:
    if not line.startswith('"(PDH-CSV'):
        return None
    header = next(csv.reader([line]))
    parsed: list[tuple[str, str, str]] = []
    for column in header[1:]:
        match = _COL.match(column)
        if match:
            parsed.append((match.group(1).lower(), (match.group(2) or "").lower(), match.group(3).lower()))
        else:
            parsed.append(("?", "", column.lower()))
    return parsed


def parse_typeperf_row(line: str, header: list[tuple[str, str, str]]) -> list[str] | None:
    if not line.startswith('"'):
        return None
    values = next(csv.reader([line]))
    if len(values) != len(header) + 1:
        return None
    return values


class StaticSource:
    """In-memory counter snapshot used by tests and by anything that is not Windows."""

    def __init__(self, cols=None, row=None, recv: float = 0.0):
        self.cols = cols
        self.row = row
        self.recv = recv
        self.rows = 0
        self.restarts = 0

    def snapshot(self):
        return self.cols, self.row, self.recv

    def request_restart(self) -> None:
        self.restarts += 1

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None


class TypeperfReader(threading.Thread):
    """Read `typeperf` CSV rows until stopped. Windows only."""

    def __init__(self, name: str, counters: list[str], restart_s: float = 900):
        if sys.platform != "win32":
            raise SafetyError("typeperf is Windows-only")
        super().__init__(daemon=True, name=f"tp-{name}")
        self.counters = list(counters)
        self.restart_s = restart_s
        self.stop_ev = threading.Event()
        self.restart_ev = threading.Event()
        self.lock = threading.Lock()
        self.cols = None
        self.row = None
        self.row_recv = 0.0
        self.rows = 0
        self.restarts = 0
        self.err = ""
        self.proc = None

    def snapshot(self):
        with self.lock:
            return self.cols, self.row, self.row_recv

    def request_restart(self) -> None:
        self.restart_ev.set()

    def run(self) -> None:
        while not self.stop_ev.is_set():
            try:
                self._once()
            except Exception as exc:  # noqa: BLE001 - reader must keep trying
                self.err = repr(exc)
            self.stop_ev.wait(3.0)

    def _once(self) -> None:
        argv = typeperf_argv(self.counters)
        flags = CREATE_NO_WINDOW if sys.platform == "win32" else 0
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
        )
        self.proc = proc
        self.restarts += 1
        started = time.time()
        header = None
        try:
            assert proc.stdout is not None
            while not self.stop_ev.is_set() and not self.restart_ev.is_set():
                raw = proc.stdout.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                if line.startswith('"(PDH-CSV'):
                    header = parse_typeperf_header(line)
                    continue
                if header is None:
                    continue
                values = parse_typeperf_row(line, header)
                if values is None:
                    continue
                with self.lock:
                    self.cols = header
                    self.row = values
                    self.row_recv = time.time()
                    self.rows += 1
                if time.time() - started > self.restart_s:
                    break
        finally:
            self.restart_ev.clear()
            _end_process(proc)
            self.proc = None

    def stop(self) -> None:
        self.stop_ev.set()
        _end_process(self.proc)
        self.proc = None


def _end_process(proc) -> None:
    if proc is None:
        return
    try:
        proc.kill()
    except OSError:
        return
