"""Anomaly harness CLI.

Commands: baseline-init, collect, check, report.

The baseline is a planted post. ``collect`` only records readings.
``check`` compares new readings to that post. The first drift is a lasso
(catch it, pull it back). The third drift in a row is strike-three, which
is the alarm this harness is meant to get ahead of.

Nothing here reads a live GPU, a broker, or a network interface.
Trader figures are drill numbers. Network uptime is a ratio already in a file.

Run from ``metal_master_fort``::

    python -m anomaly_harness baseline-init
    python -m anomaly_harness collect --bot thermal_gate --source anomaly_harness/fixtures/thermal_steady.csv
    python -m anomaly_harness check
    python -m anomaly_harness report
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from anomaly_harness.collectors import COLLECTORS
from anomaly_harness.drift import apply_streak, judge, pullback
from anomaly_harness.errors import HarnessError
from house_policy import (
    FUZZY66,
    FUZZY_CHEAP_PASS_CORE_C,
    FUZZY_CHEAP_PASS_HOTSPOT_C,
    FUZZY_GPU,
    FUZZY_LANE,
    POLICY_NOTE,
    PolicyError,
    SELF_AWARE,
    SWARM,
    XTX_CORE_C,
    XTX_GPU,
    XTX_HOTSPOT_C,
    XTX_LANE,
    assert_swarm,
)

CONFIG_SCHEMA = "agios.metal_master.harness_config.v1"
BASELINE_SCHEMA = "agios.metal_master.baselines.v1"
EVENT_SCHEMA = "agios.metal_master.anomaly_event.v1"
STREAK_SCHEMA = "agios.metal_master.streaks.v1"
SAMPLE_SCHEMA = "agios.metal_master.sample.v1"

REQUIRED_BOTS = ("thermal_gate", "fuzzy66_thermal", "trader_scout", "network_master")
PACKAGE_ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except PolicyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="anomaly_harness")
    parser.add_argument(
        "--root",
        type=Path,
        default=PACKAGE_ROOT,
        help="harness directory (config.json, baselines.json, events/)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("baseline-init", help="plant baselines from policy, or from samples")
    init.add_argument("--from-samples", action="store_true")
    init.set_defaults(func=cmd_init)

    collect = commands.add_parser("collect", help="append local fixture readings to the sample log")
    collect.add_argument("--bot", required=True)
    collect.add_argument("--source", required=True)
    collect.add_argument("--format", choices=("auto", "csv", "json"), default="auto")
    collect.set_defaults(func=cmd_collect)

    check = commands.add_parser("check", help="lasso drift before strike-three")
    check.add_argument("--bot", default=None, help="display filter; exit code still sees every bot")
    check.add_argument("--json", action="store_true")
    check.add_argument("--from-start", action="store_true", help="rewind the sample cursor")
    check.set_defaults(func=cmd_check)

    report = commands.add_parser("report", help="show baselines, open lassos, and strikes")
    report.add_argument("--json", action="store_true")
    report.set_defaults(func=cmd_report)
    return parser


def cmd_init(args) -> int:
    root = args.root
    config = load_config(root / "config.json")
    samples = load_samples(root / "events" / "samples.jsonl") if args.from_samples else []
    baselines = build_baselines(config, samples if args.from_samples else None)
    write_json(root / "baselines.json", baselines)
    source = baselines["source"]
    print(f"baselines planted ({source})")
    return 0


def cmd_collect(args) -> int:
    root = args.root
    config = load_config(root / "config.json")
    if args.bot not in config["bots"]:
        raise HarnessError(f"unknown bot {args.bot}")
    if "://" in args.source:
        raise HarnessError("collector source must be a local file")
    source = Path(args.source)
    bot = config["bots"][args.bot]
    collector = COLLECTORS[bot["collector"]]
    rows = collector(source, args.bot, args.format)
    for row in rows:
        if row["collector"] != bot["collector"]:
            raise HarnessError("collector name did not match the bot")
    path = root / "events" / "samples.jsonl"
    append_jsonl(path, rows)
    print(f"collected {len(rows)} from {source.name} for {args.bot}")
    return 0


def cmd_check(args) -> int:
    root = args.root
    config = load_config(root / "config.json")
    baselines = load_baselines(root / "baselines.json")
    _same_bots(config, baselines)
    sample_path = root / "events" / "samples.jsonl"
    samples = load_samples(sample_path)
    state = load_streaks(root / "events" / "streaks.json")
    if args.from_start:
        state["last_line"] = 0
        state["open"] = {}
    judged = judge_new_samples(samples, baselines, state)
    notable = [event for event in judged if event["kind"] != "ok"]
    if notable:
        append_jsonl(root / "events" / "anomalies.jsonl", notable)
    write_json(root / "events" / "streaks.json", state)
    shown = notable
    if args.bot is not None:
        if args.bot not in baselines["bots"]:
            raise HarnessError(f"unknown bot {args.bot}")
        shown = [event for event in notable if event["bot"] == args.bot]
    exit_class = exit_class_for(notable)
    counts = _counts(judged)
    if args.json:
        print(json.dumps({"exit_class": exit_class, "counts": counts, "events": shown}, indent=2))
    else:
        if not shown:
            print("no new drift")
        for event in shown:
            print(
                f"{event['kind']} {event['bot']}.{event['metric']} "
                f"value={event['value']} consecutive={event['consecutive']}/{event['strike_limit']}"
            )
            if event["pullback"]:
                print(f"  {event['pullback']}")
        print(
            "CHECK "
            f"ok={counts['ok']} lasso={counts['lasso']} "
            f"strike={counts['strike']} release={counts['release']}"
        )
    return {"ok": 0, "lasso": 3, "strike": 4}[exit_class]


def cmd_report(args) -> int:
    root = args.root
    baselines = load_baselines(root / "baselines.json")
    events = load_events(root / "events" / "anomalies.jsonl")
    streaks = load_streaks(root / "events" / "streaks.json") if (root / "events" / "streaks.json").exists() else {
        "schema": STREAK_SCHEMA,
        "last_line": 0,
        "open": {},
    }
    payload = build_report(baselines, events, streaks)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(render_report(payload))
    return 0


def load_config(path: Path) -> dict:
    data = read_json(path, "config")
    if data.get("schema") != CONFIG_SCHEMA:
        raise HarnessError("config schema is not the harness config")
    if tuple(data.get("swarm", [])) != SWARM:
        raise HarnessError("config swarm must be selfaware then fuzzy66")
    bots = data.get("bots")
    if not isinstance(bots, dict):
        raise HarnessError("config bots must be an object")
    for name in REQUIRED_BOTS:
        if name not in bots:
            raise HarnessError(f"config is missing bot {name}")
    hosts = []
    for name, bot in bots.items():
        _validate_bot(name, bot)
        hosts.append(bot["host"])
    assert_swarm(hosts)
    _validate_known_ceilings(bots)
    return data


def _validate_bot(name: str, bot: dict) -> None:
    if not isinstance(bot, dict):
        raise HarnessError(f"{name}: bot entry is not an object")
    if bot.get("collector") not in COLLECTORS:
        raise HarnessError(f"{name}: unknown collector")
    if bot.get("host") not in SWARM:
        raise HarnessError(f"{name}: host is outside the swarm")
    metrics = bot.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        raise HarnessError(f"{name}: metrics are missing")
    for metric_name, metric in metrics.items():
        for key in ("unit", "baseline", "policy", "warn", "seed_mean", "seed_stddev", "drift_abs", "drift_k", "strike_limit"):
            if key not in metric:
                raise HarnessError(f"{name}.{metric_name}: missing {key}")
        if metric["baseline"] not in ("high", "low", "both"):
            raise HarnessError(f"{name}.{metric_name}: baseline side is invalid")
        if metric["policy"] not in ("ceiling", "floor"):
            raise HarnessError(f"{name}.{metric_name}: policy side is invalid")
        if int(metric["strike_limit"]) < 1:
            raise HarnessError(f"{name}.{metric_name}: strike_limit must be at least 1")


def _validate_known_ceilings(bots: dict) -> None:
    thermal = bots["thermal_gate"]
    if thermal["host"] != SELF_AWARE or thermal["gpu"] != XTX_GPU or thermal["lane"] != XTX_LANE:
        raise HarnessError("thermal_gate must be the selfaware RX 7900 XTX primary lane")
    if thermal["collector"] != "thermal":
        raise HarnessError("thermal_gate collector must be thermal")
    if int(thermal["metrics"]["core_c"]["warn"]) != XTX_CORE_C:
        raise HarnessError("thermal_gate core warn must stay on Gary's 80C line")
    if int(thermal["metrics"]["hotspot_c"]["warn"]) != XTX_HOTSPOT_C:
        raise HarnessError("thermal_gate hotspot warn must stay on Gary's 88C line")

    fuzzy = bots["fuzzy66_thermal"]
    if fuzzy["host"] != FUZZY66 or fuzzy["gpu"] != FUZZY_GPU or fuzzy["lane"] != FUZZY_LANE:
        raise HarnessError("fuzzy66_thermal must be the RX 6600 cheap-pass lane")
    if int(fuzzy["metrics"]["core_c"]["warn"]) != FUZZY_CHEAP_PASS_CORE_C:
        raise HarnessError("fuzzy66 core warn must stay on the fort cheap-pass default")
    if int(fuzzy["metrics"]["hotspot_c"]["warn"]) != FUZZY_CHEAP_PASS_HOTSPOT_C:
        raise HarnessError("fuzzy66 hotspot warn must stay on the fort cheap-pass default")

    if "core_c" not in thermal["metrics"] or "hotspot_c" not in thermal["metrics"]:
        raise HarnessError("thermal metrics must include core_c and hotspot_c")
    if "pnl_usd" not in bots["trader_scout"]["metrics"]:
        raise HarnessError("trader_scout must watch pnl_usd")
    if "uptime_ratio" not in bots["network_master"]["metrics"]:
        raise HarnessError("network_master must watch uptime_ratio")


def build_baselines(config: dict, samples: list[dict] | None) -> dict:
    grouped: dict[tuple[str, str], list[float]] = {}
    if samples is not None:
        for row in samples:
            grouped.setdefault((row["bot"], row["metric"]), []).append(float(row["value"]))
    bots_out = {}
    for name, bot in config["bots"].items():
        metrics_out = {}
        for metric_name, metric in bot["metrics"].items():
            values = grouped.get((name, metric_name), []) if samples is not None else []
            mean = float(metric["seed_mean"])
            stddev = float(metric["seed_stddev"])
            count = 0
            if values:
                count = len(values)
                mean = sum(values) / count
                if count >= 2:
                    variance = sum((item - mean) ** 2 for item in values) / (count - 1)
                    stddev = variance ** 0.5
            span = metric.get("span")
            metrics_out[metric_name] = {
                "unit": metric["unit"],
                "baseline": metric["baseline"],
                "policy": metric["policy"],
                "warn": metric["warn"],
                "mean": mean,
                "stddev": stddev,
                "n": count if samples is not None else 0,
                "drift_abs": metric["drift_abs"],
                "drift_k": metric["drift_k"],
                "strike_limit": metric["strike_limit"],
            }
            if span is not None:
                metrics_out[metric_name]["span"] = span
        bots_out[name] = {
            "host": bot["host"],
            "collector": bot["collector"],
            "lane": bot.get("lane"),
            "gpu": bot.get("gpu"),
            "metrics": metrics_out,
        }
    return {
        "schema": BASELINE_SCHEMA,
        "source": "samples" if samples is not None else "policy_seed",
        "notes": POLICY_NOTE,
        "swarm": list(SWARM),
        "policy": {
            "selfaware_rx_7900_xtx": {
                "core_c": XTX_CORE_C,
                "hotspot_c": XTX_HOTSPOT_C,
                "authority": "gary",
            },
            "fuzzy66_rx_6600_cheap_pass": {
                "core_c": FUZZY_CHEAP_PASS_CORE_C,
                "hotspot_c": FUZZY_CHEAP_PASS_HOTSPOT_C,
                "lane": FUZZY_LANE,
                "authority": "fort_default_pending_gary_number",
            },
        },
        "bots": bots_out,
    }


def load_baselines(path: Path) -> dict:
    data = read_json(path, "baselines")
    if data.get("schema") != BASELINE_SCHEMA:
        raise HarnessError("baselines schema is not the harness baselines")
    if tuple(data.get("swarm", [])) != SWARM:
        raise HarnessError("baselines swarm must be selfaware then fuzzy66")
    return data


def judge_new_samples(samples: list[dict], baselines: dict, state: dict) -> list[dict]:
    last_line = int(state.get("last_line", 0))
    open_streaks = dict(state.get("open") or {})
    fresh = [row for row in samples if int(row["_line"]) > last_line]
    fresh.sort(key=lambda row: (row["timestamp"], row["_line"]))
    events = []
    for row in fresh:
        _require_sample(row)
        bot_name = row["bot"]
        metric_name = row["metric"]
        if bot_name not in baselines["bots"]:
            raise HarnessError(f"unknown bot {bot_name}")
        bot = baselines["bots"][bot_name]
        if metric_name not in bot["metrics"]:
            raise HarnessError(f"unknown metric {metric_name} for {bot_name}")
        if row["collector"] != bot["collector"]:
            raise HarnessError(
                f"unknown collector mix for {bot_name}: sample says {row['collector']}"
            )
        metric = bot["metrics"][metric_name]
        reasons = judge(float(row["value"]), metric)
        key = f"{bot_name}.{metric_name}"
        previous = int(open_streaks.get(key, 0))
        kind, count = apply_streak(bool(reasons), previous, int(metric["strike_limit"]))
        if count:
            open_streaks[key] = count
        else:
            open_streaks.pop(key, None)
        events.append(
            {
                "schema": EVENT_SCHEMA,
                "timestamp": row["timestamp"],
                "bot": bot_name,
                "host": bot["host"],
                "collector": row["collector"],
                "metric": metric_name,
                "kind": kind,
                "value": row["value"],
                "baseline_mean": metric["mean"],
                "consecutive": count,
                "strike_limit": metric["strike_limit"],
                "reasons": reasons,
                "pullback": pullback(bot, kind),
            }
        )
    if fresh:
        state["last_line"] = max(int(row["_line"]) for row in samples)
    state["schema"] = STREAK_SCHEMA
    state["open"] = {key: value for key, value in sorted(open_streaks.items()) if value}
    return events


def _require_sample(row: dict) -> None:
    if row.get("schema") != SAMPLE_SCHEMA:
        raise HarnessError("sample schema is not a harness sample")
    for key in ("bot", "metric", "value", "timestamp", "collector", "source"):
        if key not in row:
            raise HarnessError(f"sample is missing {key}")


def build_report(baselines: dict, events: list[dict], streaks: dict) -> dict:
    counts = _counts(events)
    open_rows = []
    latest: dict[str, dict] = {}
    for event in events:
        latest[f"{event['bot']}.{event['metric']}"] = event
    for key, count in sorted((streaks.get("open") or {}).items()):
        event = latest.get(key)
        open_rows.append(
            {
                "key": key,
                "consecutive": count,
                "kind": None if event is None else event["kind"],
                "value": None if event is None else event["value"],
                "pullback": "" if event is None else event["pullback"],
                "strike_limit": None if event is None else event["strike_limit"],
            }
        )
    return {
        "schema": "agios.metal_master.harness_report.v1",
        "swarm": baselines["swarm"],
        "notes": baselines.get("notes", POLICY_NOTE),
        "policy": baselines["policy"],
        "source": baselines["source"],
        "counts": counts,
        "open": open_rows,
        "lasso_before_strike": counts["lasso"] > 0 and _any_open_below_strike(open_rows),
    }


def _any_open_below_strike(open_rows: list[dict]) -> bool:
    for row in open_rows:
        limit = row["strike_limit"]
        if limit is not None and row["consecutive"] < limit and row["kind"] == "lasso":
            return True
    return False


def render_report(payload: dict) -> str:
    policy = payload["policy"]
    xtx = policy["selfaware_rx_7900_xtx"]
    fuzzy = policy["fuzzy66_rx_6600_cheap_pass"]
    lines = [
        "Metal Master Fort — anomaly harness",
        "swarm: " + ", ".join(payload["swarm"]),
        (
            "Gary policy: selfaware RX 7900 XTX "
            f"core {xtx['core_c']}C / hotspot {xtx['hotspot_c']}C"
        ),
        (
            "Fort default (pending Gary's number): fuzzy66 RX 6600 cheap-pass "
            f"core {fuzzy['core_c']}C / hotspot {fuzzy['hotspot_c']}C"
        ),
        f"baseline source: {payload['source']}",
        (
            "counts: "
            f"lasso={payload['counts']['lasso']} "
            f"strike={payload['counts']['strike']} "
            f"release={payload['counts']['release']}"
        ),
    ]
    if payload["lasso_before_strike"]:
        lines.append("lasso is ahead of strike-three on at least one open metric")
    if not payload["open"]:
        lines.append("open streaks: none")
    for row in payload["open"]:
        lines.append(
            f"open {row['key']} kind={row['kind']} "
            f"consecutive={row['consecutive']}/{row['strike_limit']} value={row['value']}"
        )
        if row["pullback"]:
            lines.append(f"  {row['pullback']}")
    return "\n".join(lines)


def exit_class_for(events: list[dict]) -> str:
    kinds = {event["kind"] for event in events}
    if "strike" in kinds:
        return "strike"
    if "lasso" in kinds:
        return "lasso"
    return "ok"


def _counts(events: list[dict]) -> dict:
    counts = {"ok": 0, "lasso": 0, "strike": 0, "release": 0}
    for event in events:
        counts[event["kind"]] = counts.get(event["kind"], 0) + 1
    return counts


def _same_bots(config: dict, baselines: dict) -> None:
    if set(config["bots"]) != set(baselines["bots"]):
        raise HarnessError("baselines do not match config bots; run baseline-init")


def load_samples(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HarnessError(f"{path.name}:{index}: {exc.msg}") from exc
        if not isinstance(obj, dict):
            raise HarnessError(f"{path.name}:{index}: sample is not an object")
        obj["_line"] = index
        rows.append(obj)
    return rows


def load_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HarnessError(f"{path.name}:{index}: {exc.msg}") from exc
        rows.append(obj)
    return rows


def load_streaks(path: Path) -> dict:
    if not path.exists():
        return {"schema": STREAK_SCHEMA, "last_line": 0, "open": {}}
    data = read_json(path, "streaks")
    if data.get("schema") != STREAK_SCHEMA:
        raise HarnessError("streaks schema is not the harness streaks file")
    data.setdefault("open", {})
    data.setdefault("last_line", 0)
    return data


def read_json(path: Path, label: str) -> dict:
    if not path.is_file():
        raise HarnessError(f"missing {label} file {path.name}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HarnessError(f"invalid json in {path.name}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise HarnessError(f"{label} file must be an object")
    return data


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

