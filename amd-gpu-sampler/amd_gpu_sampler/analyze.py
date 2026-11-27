"""Signal ladder for one sample. Levels are ok/watch/warn/critical. Nothing here stops a process."""

from __future__ import annotations

import os

LEVELS = ["ok", "watch", "warn", "critical"]


def slope(hist, key: str, window_s: float, now: float) -> float:
    points = [(item["t"], item[key]) for item in hist if now - item["t"] <= window_s and isinstance(item.get(key), (int, float)) and not isinstance(item.get(key), bool)]
    if len(points) < 4:
        return 0.0
    count = len(points)
    mean_t = sum(point[0] for point in points) / count
    mean_v = sum(point[1] for point in points) / count
    denom = sum((point[0] - mean_t) ** 2 for point in points)
    if denom <= 1e-9:
        return 0.0
    return sum((point[0] - mean_t) * (point[1] - mean_v) for point in points) / denom


def mean(hist, key: str, window_s: float, now: float, cur=None) -> float:
    values = [item[key] for item in hist if now - item["t"] <= window_s and isinstance(item.get(key), (int, float)) and not isinstance(item.get(key), bool)]
    if cur is not None and isinstance(cur.get(key), (int, float)) and not isinstance(cur.get(key), bool):
        values.append(cur[key])
    return sum(values) / len(values) if values else 0.0


def analyze(hist, sample: dict, hb=None, godot_age=None, ncpu: int | None = None) -> list[dict]:
    """Return signals for `sample`. `hist` holds older samples and does not include `sample`."""
    cpus = ncpu or os.cpu_count() or 1
    now = sample["t"]
    signals: list[dict] = []

    def add(sig_id: str, level: int, msg: str, expect: str) -> None:
        signals.append({"id": sig_id, "level": level, "msg": msg, "expect": expect})

    if "gpu_free_mb" in sample:
        free = sample["gpu_free_mb"]
        trend = slope(hist, "gpu_used_mb", 20, now)
        eta = free / trend if trend > 2.0 else None
        free_gb = "%.1f GB" % (free / 1024.0)
        if free < 1024 or (eta is not None and eta < 30):
            add("gpu_vram", 3, "GPU VRAM almost gone (%s free); expect a stall or a graphics hiccup" % free_gb, "gpu_stall")
        elif free < 2048 or (eta is not None and eta < 60):
            add("gpu_vram", 2, "GPU VRAM nearly full (%s free); expect a stall" % free_gb, "gpu_stall")
        elif free < 4096 or (eta is not None and eta < 120):
            add("gpu_vram", 1, "GPU VRAM getting tight (%s free)" % free_gb, "gpu_stall")
        else:
            add("gpu_vram", 0, "GPU VRAM ok (%s free)" % free_gb, "none")
        busy8 = mean(hist, "gpu_busy", 8, now, sample)
        if busy8 >= 97:
            add("gpu_busy", 2, "GPU pegged near 100%; expect frame hitches", "gpu_stall")
        elif busy8 >= 90:
            add("gpu_busy", 1, "GPU very busy (%d%%); frames may slow" % busy8, "gpu_stall")
        else:
            add("gpu_busy", 0, "GPU load %d%%" % busy8, "none")
    junction = sample.get("gpu_junction_c")
    if isinstance(junction, (int, float)) and not isinstance(junction, bool) and (sample.get("thermal_age_s") or 0) < 30:
        level = 3 if junction >= 100 else 2 if junction >= 90 else 1 if junction >= 85 else 0
        add("gpu_temp", level, "GPU junction %d C%s" % (junction, "; expect throttling" if level else ""), "gpu_stall" if level else "none")
    if "avail_mb" in sample and sample.get("counters_ok"):
        available = sample["avail_mb"]
        trend = slope(hist, "avail_mb", 30, now)
        eta = available / -trend if trend < -5.0 else None
        pages = mean(hist, "pages_in_s", 10, now, sample)
        avail_gb = "%.1f GB" % (available / 1024.0)
        if available < 1024 or (eta is not None and eta < 30):
            add("ram_avail", 3, "RAM almost out (%s free); expect heavy paging and stalls" % avail_gb, "ram_hiccup")
        elif available < 2048 or (eta is not None and eta < 90) or sample["commit_pct"] > 92:
            add("ram_avail", 2, "RAM pressure rising (%s free, commit %d%%); expect hiccups" % (avail_gb, sample["commit_pct"]), "ram_hiccup")
        elif available < 4096 or sample["commit_pct"] > 85:
            add("ram_avail", 1, "RAM getting low (%s free)" % avail_gb, "ram_hiccup")
        else:
            add("ram_avail", 0, "RAM ok (%s free)" % avail_gb, "none")
        # Pages Input/sec also counts ordinary file reads, so it is pressure only when RAM is low or the rate is extreme.
        if pages > 5000 or (pages > 1500 and available < 8192):
            add("ram_hardfaults", 2, "memory is paging from disk (%d pages/s); expect micro-stalls" % pages, "ram_hiccup")
        elif (pages > 500 and available < 8192) or pages > 1500:
            extra = "" if available < 8192 else ", RAM is plentiful so likely file reads"
            expect = "ram_hiccup" if available < 8192 else "none"
            add("ram_hardfaults", 1, "heavy disk reads/paging (%d pages/s)%s" % (pages, extra), expect)
        else:
            add("ram_hardfaults", 0, "no disk paging pressure", "none")
    if sample.get("counters_ok") and "cpu" in sample:
        cpu3 = mean(hist, "cpu", 3, now, sample)
        cpu_slope = slope(hist, "cpu", 8, now)
        max_core = mean(hist, "cpu_max_core", 5, now, sample)
        interrupt = sample["dpc"] + sample["irq"]
        if cpu3 >= 95:
            add("cpu_load", 2, "CPU pinned at %d%%; expect a sneeze (spike)" % cpu3, "cpu_spike")
        elif cpu3 >= 85 or (cpu_slope >= 4.0 and sample["cpu"] >= 50):
            add("cpu_load", 1, "CPU spike building (%d%%, rising)" % sample["cpu"], "cpu_spike")
        else:
            add("cpu_load", 0, "CPU %d%%" % sample["cpu"], "none")
        if max_core >= 99 and cpu3 < 60:
            add("cpu_core", 1, "one core pegged (single-thread bound); a frame may drag", "cpu_spike")
        if sample["queue"] > 2 * cpus:
            add("cpu_queue", 2, "CPU run queue long (%d); expect a stall" % sample["queue"], "cpu_spike")
        elif sample["queue"] > cpus:
            add("cpu_queue", 1, "CPU run queue growing (%d)" % sample["queue"], "cpu_spike")
        if interrupt >= 15:
            add("cpu_irq", 2, "interrupt/DPC storm (%.0f%%); a driver may be hogging the CPU" % interrupt, "cpu_spike")
        elif interrupt >= 6:
            add("cpu_irq", 1, "interrupt/DPC time elevated (%.0f%%)" % interrupt, "cpu_spike")
        if sample["perf_limit"] < 90:
            add("cpu_throttle", 2, "CPU is being throttled (limit %d%%)" % sample["perf_limit"], "cpu_spike")
        elif sample["perf_limit"] < 98:
            add("cpu_throttle", 1, "CPU slightly limited (%d%%)" % sample["perf_limit"], "cpu_spike")
    if godot_age is not None:
        if godot_age > 4.0:
            add("godot_frames", 3, "my body stopped ticking for %.1f s; a frame stall is happening" % godot_age, "frame_stall")
        elif godot_age > 2.5:
            add("godot_frames", 2, "my body ticked late (%.1f s); a frame stall" % godot_age, "frame_stall")
    if hb:
        if hb["max_ms"] > 250:
            add("sched_jitter", 2, "scheduler jitter spike (%d ms)" % hb["max_ms"], "cpu_spike")
        elif hb["p99_ms"] > 50:
            add("sched_jitter", 1, "scheduling jitter elevated (p99 %d ms)" % hb["p99_ms"], "cpu_spike")
    if sample.get("tp_age_s", 0) > 3.5:
        add("sampler_feed", 1, "counter feed is late (%.0f s)" % sample["tp_age_s"], "none")
    return signals


def felt_line(signals: list[dict], sample: dict) -> tuple[str, str]:
    bad = sorted([item for item in signals if item["level"] > 0 and item["expect"] != "none"], key=lambda item: -item["level"])
    if bad:
        line = "; ".join(item["msg"] for item in bad[:2])
        return line[:200], bad[0]["expect"]
    line = "All calm: GPU %d%% with %.1f GB VRAM free, RAM %.0f GB free, CPU %d%%; no stalls expected." % (
        sample.get("gpu_busy", 0),
        sample.get("gpu_free_mb", 0) / 1024.0,
        sample.get("avail_mb", 0) / 1024.0,
        sample.get("cpu", 0),
    )
    return line[:200], "none"


def _max_key(recent, key: str) -> float:
    values = [item[key] for item in recent if isinstance(item.get(key), (int, float)) and not isinstance(item.get(key), bool)]
    return max(values) if values else 0.0


def explain(gap: dict, recent: list, godot_age=None, ncpu: int | None = None) -> list[dict]:
    """Rank likely causes for a scheduling gap. Read-only; it does not act on the machine."""
    cpus = ncpu or os.cpu_count() or 1
    causes = []
    wall = gap.get("wall_ms")
    gap_ms = gap.get("gap_ms", 0)
    if wall is not None and abs(wall - gap_ms) > 1500:
        causes.append(("clock_jump_or_suspend", 0.9, "wall clock moved %d ms vs %d ms measured: sleep/resume or clock change" % (wall, gap_ms)))
    if _max_key(recent, "cpu") >= 90 or _max_key(recent, "queue") > 2 * cpus:
        causes.append(("cpu_saturation", 0.7, "CPU up to %d%%, run queue up to %d" % (_max_key(recent, "cpu"), _max_key(recent, "queue"))))
    if _max_key(recent, "dpc") + _max_key(recent, "irq") >= 10:
        causes.append(("dpc_interrupt_storm", 0.7, "DPC+interrupt time reached %.0f%%: a driver held the CPU" % (_max_key(recent, "dpc") + _max_key(recent, "irq"))))
    avail = [item["avail_mb"] for item in recent if isinstance(item.get("avail_mb"), (int, float))]
    low_avail = min(avail) if avail else 10**9
    if low_avail < 2048 or _max_key(recent, "pages_in_s") >= 5000 or (_max_key(recent, "pages_in_s") >= 300 and low_avail < 8192):
        causes.append(("memory_pressure_paging", 0.65, "hard faults up to %d pages/s, free RAM low %s MB" % (_max_key(recent, "pages_in_s"), min(avail) if avail else 0)))
    frees = [item["gpu_free_mb"] for item in recent if isinstance(item.get("gpu_free_mb"), (int, float))]
    if _max_key(recent, "gpu_busy") >= 97 or (frees and min(frees) < 1024):
        causes.append(("gpu_saturation_or_vram_full", 0.6, "GPU busy up to %d%%, VRAM free low %s MB" % (_max_key(recent, "gpu_busy"), min(frees) if frees else 0)))
    hottest = _max_key(recent, "gpu_junction_c")
    if hottest >= 90 or any(item.get("perf_limit", 100) < 90 for item in recent):
        causes.append(("thermal_throttle", 0.55, "GPU junction up to %s C / CPU performance limit dipped" % hottest))
    if _max_key(recent, "godot_cpu_core_pct") >= 180:
        causes.append(("godot_cpu_burst", 0.5, "Godot used up to %d%% of one core (world update burst)" % _max_key(recent, "godot_cpu_core_pct")))
    if godot_age is not None and godot_age > 2.5:
        causes.append(("godot_frame_stall", 0.5, "Godot's own tick file went %.1f s without updating" % godot_age))
    if not causes:
        causes.append(("unexplained_sampler_starvation", 0.3, "no system counter explains it: the sampler itself was not scheduled; cause unknown"))
    causes.sort(key=lambda item: -item[1])
    return [{"cause": cause, "score": score, "evidence": evidence} for cause, score, evidence in causes]
