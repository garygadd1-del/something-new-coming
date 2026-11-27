"""Inner-world sampler loop.

Read-only: performance counters, an existing thermal file, and the Godot alive
file. Outbound reporting pauses when a configured core temperature crosses
Gary's threshold (default 78C). The process keeps running. STOP is a file,
not a delete.
"""

from __future__ import annotations

import argparse
import collections
import os
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

from amd_gpu_sampler.analyze import LEVELS, analyze, explain, felt_line
from amd_gpu_sampler.bridge import start_bridge
from amd_gpu_sampler.chain import Chain, ChainError, now_iso, verify_log
from amd_gpu_sampler.config import SamplerConfig, load_config
from amd_gpu_sampler.counters import GODOT_COUNTERS, SYS_COUNTERS, StaticSource, TypeperfReader
from amd_gpu_sampler.heartbeat import Heartbeat, NullHeartbeat
from amd_gpu_sampler.pipe import PipeFeed, compact_message
from amd_gpu_sampler.process_info import pid_alive
from amd_gpu_sampler.safety import SafetyError, assert_no_traversal, atomic_write_json, jload
from amd_gpu_sampler.sample import build_sample
from amd_gpu_sampler.schema import SCHEMA_SAMPLER, SchemaError, assemble_sampler_state
from amd_gpu_sampler.thermal import decide_pause, fresh_readings


class AlreadyRunning(Exception):
    def __init__(self, pid: int):
        self.pid = pid
        super().__init__(f"already running pid {pid}")


@dataclass
class GodotView:
    pid: int = 0
    age_s: float | None = None


class Sampler:
    def __init__(
        self,
        work_dir: Path | str,
        *,
        config: SamplerConfig | None = None,
        sys_source=None,
        god_source=None,
        heartbeat=None,
        pipe=None,
        clock=None,
        thermal_loader=None,
        godot_loader=None,
        ncpu: int | None = None,
    ):
        self.requested_dir = Path(work_dir)
        self.config = config or SamplerConfig()
        self.sys_source = sys_source if sys_source is not None else StaticSource()
        self.god_source = god_source if god_source is not None else StaticSource()
        self.heartbeat = heartbeat if heartbeat is not None else NullHeartbeat()
        self.pipe = pipe
        self.clock = clock or time.time
        self.thermal_loader = thermal_loader or self._load_thermal
        self.godot_loader = godot_loader or self._load_godot
        self.ncpu = ncpu or os.cpu_count() or 1
        self.root: Path | None = None
        self.stop_path: Path | None = None
        self.chain: Chain | None = None
        self.bridge = None
        self.hist = collections.deque(maxlen=180)
        self.prev_levels: dict = {}
        self.last_alert_t: dict = {}
        self.paused = False
        self.pause_since: str | None = None
        self.godot_pid = 0
        self.last_blackout = None
        self.last_state = None
        self._cpu = time.process_time()
        self._wall = 0.0
        self._pid_owned = False
        self._stop_logged = False
        self._shutdown_done = False

    def run(self, *, duration: float = 0.0, iterations: int | None = None, sleep=time.sleep) -> int:
        try:
            self.startup()
        except AlreadyRunning as exc:
            print(exc)
            return 0
        except Exception:
            self.shutdown()
            raise
        try:
            self._loop(duration=duration, iterations=iterations, sleep=sleep)
            return 0
        finally:
            self.shutdown()

    def startup(self) -> None:
        if self.requested_dir.is_symlink():
            raise SafetyError("work dir must not be a symlink")
        self.root = self.requested_dir.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.stop_path = self.root / "STOP"
        self._rename_stale_stop()
        self._check_pid()
        self._write_pid()
        assert self.root is not None
        self.chain = Chain(self.root / "log")
        self._start_source(self.sys_source)
        self._start_source(self.god_source)
        if isinstance(self.heartbeat, Heartbeat):
            self.heartbeat.start()
        self._wall = self.clock()
        assert self.chain is not None
        self.chain.add(
            "start",
            {
                "pid": os.getpid(),
                "hz": self.config.sample_hz,
                "schema": SCHEMA_SAMPLER,
                "thermal_pause_c": self.config.thermal_pause_celsius,
                "thermal_resume_c": self.config.thermal_resume_celsius,
                "thermal_sensors": list(self.config.thermal_sensors),
                "pipe_feed": bool(self.pipe and self.pipe.enabled),
                "python": sys.version.split()[0],
                "machine": self.config.machine_label,
            },
            self.clock(),
        )
        if self.config.bridge_port:
            self.bridge = start_bridge(lambda: self.last_state, self.config.bridge_port)

    def step(self, now: float, loop_dt: float) -> dict | None:
        assert self.chain is not None
        godot = self.godot_loader()
        if not isinstance(godot, GodotView):
            godot = GodotView()
        if godot.pid != self.godot_pid:
            self.godot_pid = godot.pid
            self.sys_source.request_restart()
            self.god_source.request_restart()
        thermal = self.thermal_loader()
        cols, row, recv = self.sys_source.snapshot()
        godot_cols, godot_row, godot_recv = self.god_source.snapshot()
        sample = build_sample(
            cols=cols,
            row=row,
            recv=recv or 0.0,
            t=now,
            thermal=thermal if isinstance(thermal, dict) else None,
            godot_pid=self.godot_pid,
            godot_cols=godot_cols,
            godot_row=godot_row,
            godot_recv=godot_recv or 0.0,
            vram_total_mb_fallback=self.config.vram_total_mb_fallback,
        )
        sample["loop_dt_s"] = round(loop_dt, 3)
        sample["godot_age_s"] = godot.age_s
        elapsed = now - self._wall
        cpu_now = time.process_time()
        if elapsed <= 0:
            sample["self_cpu_pct"] = 0.0
        else:
            sample["self_cpu_pct"] = round(100.0 * (cpu_now - self._cpu) / elapsed, 2)
        self._cpu = cpu_now
        self._wall = now
        heartbeat = self.heartbeat.stats()
        signals = analyze(self.hist, sample, heartbeat, godot.age_s, ncpu=self.ncpu)
        level = max([item["level"] for item in signals if item["expect"] != "none" or item["level"] >= 2] or [0])
        felt, expect = felt_line(signals, sample)
        readings = fresh_readings(sample, self.config.thermal_sensors, max_age_s=self.config.thermal_max_age_s)
        decision = decide_pause(
            readings,
            threshold_c=self.config.thermal_pause_celsius,
            resume_c=self.config.thermal_resume_celsius,
            currently_paused=self.paused,
        )
        if decision.paused and not self.paused:
            self.pause_since = now_iso(now)
            self.chain.add(
                "thermal_pause",
                {
                    "sensor": decision.sensor,
                    "temp_c": decision.temp_c,
                    "threshold_c": decision.threshold_c,
                    "reason": decision.reason,
                },
                now,
            )
        elif self.paused and not decision.paused:
            self.chain.add(
                "thermal_resume",
                {"sensor": decision.sensor, "temp_c": decision.temp_c, "resume_c": decision.resume_c},
                now,
            )
            self.pause_since = None
        self.paused = decision.paused
        if decision.paused:
            felt = ("Reporting paused (thermal). " + felt)[:200]
            expect = "thermal_pause"
        gaps = list(self.heartbeat.pop_events())
        if loop_dt > 2.5:
            gaps.append({"kind": "main_loop_gap", "at": now, "gap_ms": round(loop_dt * 1000)})
        if gaps:
            worst = max(gaps, key=lambda item: item.get("gap_ms", 0))
            recent = [item for item in self.hist if now - item["t"] <= 12] + [sample]
            causes = explain(worst, recent, godot.age_s, ncpu=self.ncpu)
            self.last_blackout = {
                "ts": now_iso(worst.get("at", now)),
                "gap_ms": worst.get("gap_ms", 0),
                "kind": worst.get("kind", "gap"),
                "top_cause": causes[0]["cause"],
                "why": causes[0]["evidence"][:400],
            }
            self.chain.add("blackout", {"gap": _jsonish(worst), "all_gaps": len(gaps), "causes": causes[:4], "felt": felt}, now)
        alerted = False
        for item in signals:
            old = self.prev_levels.get(item["id"], 0)
            changed = item["level"] != old
            repeat = item["level"] >= 2 and now - self.last_alert_t.get(item["id"], 0) > 60
            if (changed and (item["level"] > 0 or old > 0)) or repeat:
                self.last_alert_t[item["id"]] = now
                alerted = alerted or item["level"] > old
                self.chain.add(
                    "alert",
                    {"id": item["id"], "from": LEVELS[old], "to": LEVELS[item["level"]], "msg": item["msg"], "expect": item["expect"]},
                    now,
                )
            self.prev_levels[item["id"]] = item["level"]
        logged = {key: value for key, value in sample.items() if key != "t"}
        logged["level"] = LEVELS[level]
        logged["reporting"] = "paused" if decision.paused else "active"
        self.chain.add("sample", logged, now)
        if self.pipe is not None:
            self.pipe.active(now)
        meta = {
            "pid": os.getpid(),
            "self_cpu_pct": sample["self_cpu_pct"],
            "pipe_feed": self.pipe.reason if self.pipe is not None else "disabled",
            "pipe_sent": self.pipe.sent if self.pipe is not None else 0,
            "chain_seq": self.chain.seq,
            "chain_hash": self.chain.prev[:16],
            "thermal_pause_c": self.config.thermal_pause_celsius,
            "thermal_resume_c": self.config.thermal_resume_celsius,
        }
        try:
            state = assemble_sampler_state(
                sample=sample,
                signals=signals,
                level=level,
                felt=felt,
                expect=expect,
                godot_pid=self.godot_pid,
                godot_age=godot.age_s,
                heartbeat=heartbeat,
                last_blackout=self.last_blackout,
                pause=decision,
                pause_since=self.pause_since,
                sampler_meta=meta,
                ts=now_iso(now),
                unix=now,
            )
        except SchemaError as exc:
            self.chain.add("error", {"schema": exc.errors[:8]}, now)
            return None
        self.last_state = state
        self._write_state(state)
        level_changed = bool(alerted or (self.hist and self.hist[-1].get("_lv") != level))
        if self.pipe is not None and not decision.paused:
            self.pipe.maybe_send(compact_message(state, alerted), now, level_changed)
        sample["_lv"] = level
        self.hist.append(sample)
        return state

    def shutdown(self) -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True
        if self.chain is not None and not self._stop_logged:
            try:
                rows = getattr(self.sys_source, "rows", 0)
                self.chain.add(
                    "stop",
                    {
                        "pid": os.getpid(),
                        "pipe_sent": self.pipe.sent if self.pipe is not None else 0,
                        "pipe_failed": self.pipe.failed if self.pipe is not None else 0,
                        "typeperf_rows": rows,
                    },
                    self.clock(),
                )
                self._stop_logged = True
            except (ChainError, OSError, SafetyError, ValueError):
                pass
            try:
                self.chain.close()
            except OSError:
                pass
        try:
            self.heartbeat.stop()
        except Exception:  # noqa: BLE001 - shutdown still releases the pid file
            pass
        for source in (self.sys_source, self.god_source):
            stop = getattr(source, "stop", None)
            if callable(stop):
                try:
                    stop()
                except Exception:  # noqa: BLE001
                    pass
        if self.bridge is not None:
            try:
                self.bridge.shutdown()
                self.bridge.server_close()
            except Exception:  # noqa: BLE001
                pass
        self._release_pid()

    def _loop(self, *, duration: float, iterations: int | None, sleep) -> None:
        assert self.stop_path is not None
        started = self.clock()
        nxt = started
        last_loop = started
        completed = 0
        while True:
            now = self.clock()
            if self.stop_path.exists():
                break
            if duration and now - started >= duration:
                break
            if iterations is not None and completed >= iterations:
                break
            if now < nxt:
                sleep(min(0.05, max(0.0, nxt - now)))
                continue
            loop_dt = now - last_loop
            last_loop = now
            period = 1.0 / self.config.sample_hz
            nxt = max(nxt + period, now - 0.5) if loop_dt < 2.5 else now + period
            try:
                self.step(now, loop_dt)
            except Exception:
                if self.chain is not None:
                    self.chain.add("error", {"tb": traceback.format_exc()[-600:]}, now)
                sleep(0.0 if sleep is not time.sleep else 1.0)
            completed += 1

    def _load_thermal(self):
        data = jload(Path(self.config.thermal_file))
        return data if isinstance(data, dict) else None

    def _load_godot(self) -> GodotView:
        alive_path = Path(self.config.godot_link_dir) / "godot_alive.json"
        alive = jload(alive_path)
        pid = 0
        if isinstance(alive, dict):
            try:
                pid = int(alive.get("pid") or 0)
            except (TypeError, ValueError):
                pid = 0
        age = None
        if alive_path.is_file() and not alive_path.is_symlink():
            try:
                age = round(self.clock() - alive_path.stat().st_mtime, 2)
            except OSError:
                age = None
        return GodotView(pid=pid, age_s=age)

    def _rename_stale_stop(self) -> None:
        assert self.stop_path is not None
        if not self.stop_path.exists():
            return
        if self.stop_path.is_symlink() or not self.stop_path.is_file():
            raise SafetyError("STOP must be a regular file")
        stamp = int(self.clock())
        dest = self.stop_path.with_name(f"STOP.{stamp}.done")
        if dest.exists():
            dest = self.stop_path.with_name(f"STOP.{stamp}.{os.getpid()}.done")
        os.replace(self.stop_path, dest)

    def _check_pid(self) -> None:
        assert self.root is not None
        pid_path = self.root / "sampler.pid"
        if not pid_path.exists():
            return
        if pid_path.is_symlink() or not pid_path.is_file():
            raise SafetyError("sampler.pid must be a regular file")
        text = pid_path.read_text(encoding="utf-8")
        token = text.split()[0] if text.split() else ""
        try:
            old = int(token)
        except ValueError:
            return
        if old != os.getpid() and pid_alive(old):
            raise AlreadyRunning(old)

    def _write_pid(self) -> None:
        assert self.root is not None
        pid_path = self.root / "sampler.pid"
        if pid_path.is_symlink():
            raise SafetyError("refusing to write a symlinked pid file")
        pid_path.write_text(f"{os.getpid()} {now_iso(self.clock())}\n", encoding="utf-8")
        self._pid_owned = True

    def _release_pid(self) -> None:
        if not self._pid_owned or self.root is None:
            return
        pid_path = self.root / "sampler.pid"
        self._pid_owned = False
        if not pid_path.is_file() or pid_path.is_symlink():
            return
        dest = self.root / "sampler.pid.stopped"
        if dest.exists():
            dest = self.root / f"sampler.pid.stopped.{int(self.clock())}"
        os.replace(pid_path, dest)

    def _write_state(self, state: dict) -> None:
        assert self.root is not None
        last_error: Exception | None = None
        for _ in range(5):
            try:
                atomic_write_json(self.root, "state.json", state)
                return
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.02)
        if last_error:
            raise last_error

    @staticmethod
    def _start_source(source) -> None:
        start = getattr(source, "start", None)
        if callable(start):
            start()


def _jsonish(value: dict) -> dict:
    clean = {}
    for key, item in value.items():
        if isinstance(item, (str, int, float)) and not isinstance(item, bool):
            clean[key] = item
        elif isinstance(item, bool):
            clean[key] = item
    return clean


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only AGIOS inner-world health sampler")
    parser.add_argument("--dir", help="work directory for state.json, log/, STOP, and sampler.pid")
    parser.add_argument("--config", help="JSON config file. Thresholds live here.")
    parser.add_argument("--hz", type=float, default=None)
    parser.add_argument("--duration", type=float, default=0, help="seconds; 0 runs until STOP")
    parser.add_argument("--no-pipe", action="store_true", help="do not push samples to Godot")
    parser.add_argument("--bridge-port", type=int, default=None, help="optional 127.0.0.1 port for /api/body/derived")
    parser.add_argument("--machine", default=None, help="label stored in the start record")
    parser.add_argument("--verify-log", help="verify a log directory or health JSONL file, then exit")
    return parser


def _verify(path_text: str) -> int:
    try:
        assert_no_traversal(path_text)
        report = verify_log(Path(path_text))
    except (OSError, ChainError, SafetyError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if report.ok:
        print(f"ok records={report.records} head={report.head_hash}")
        return 0
    print("\n".join(report.errors), file=sys.stderr)
    return 1


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    if args.verify_log:
        return _verify(args.verify_log)
    if sys.platform != "win32":
        print("live counters require Windows typeperf", file=sys.stderr)
        return 2
    overrides = {
        "sample_hz": args.hz,
        "work_dir": args.dir,
        "bridge_port": args.bridge_port,
        "machine_label": args.machine,
    }
    if args.no_pipe:
        overrides["pipe_enabled"] = False
    try:
        config = load_config(Path(args.config) if args.config else None, overrides)
    except (OSError, SafetyError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    work = config.work_dir or (args.dir or "")
    if not work:
        print("pass --dir for the work directory", file=sys.stderr)
        return 2
    pipe = PipeFeed(Path(work), Path(config.godot_link_dir), enabled=True) if config.pipe_enabled else None
    sampler = Sampler(
        work,
        config=config,
        sys_source=TypeperfReader("sys", SYS_COUNTERS),
        god_source=TypeperfReader("godot", GODOT_COUNTERS),
        heartbeat=Heartbeat(),
        pipe=pipe,
    )
    try:
        return sampler.run(duration=args.duration)
    except KeyboardInterrupt:
        return 0
    except (ChainError, SafetyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
