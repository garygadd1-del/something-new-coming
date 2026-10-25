"""Anomaly harness: plant a baseline, catch the first drift, wait for strike-three."""

import json
import shutil
from pathlib import Path

import pytest

from anomaly_harness.harness import main
from house_policy import (
    FUZZY_CHEAP_PASS_CORE_C,
    FUZZY_CHEAP_PASS_HOTSPOT_C,
    XTX_CORE_C,
    XTX_HOTSPOT_C,
)

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "anomaly_harness"
FIX = PKG / "fixtures"
EVENT_SCHEMA = json.loads((PKG / "schema" / "event.schema.json").read_text(encoding="utf-8"))


def harness_root(tmp_path: Path) -> Path:
    root = tmp_path / "harness"
    (root / "events").mkdir(parents=True)
    shutil.copy(PKG / "config.json", root / "config.json")
    return root


def run(argv: list[str]) -> tuple[int, str, str]:
    import contextlib
    import io

    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def init(root: Path) -> None:
    code, _out, err = run(["--root", str(root), "baseline-init"])
    assert code == 0, err


def collect(root: Path, bot: str, source: Path) -> None:
    code, _out, err = run(
        ["--root", str(root), "collect", "--bot", bot, "--source", str(source)]
    )
    assert code == 0, err


def check(root: Path) -> tuple[int, dict]:
    code, out, err = run(["--root", str(root), "check", "--json"])
    assert err == "" or code == 2
    if code == 2:
        return code, {"error": err, "stdout": out}
    return code, json.loads(out)


def reasons_of(events, metric):
    return [reason for event in events if event["metric"] == metric for reason in event["reasons"]]


def test_seed_baselines_keep_gary_line_and_fort_default(tmp_path):
    root = harness_root(tmp_path)
    init(root)
    baselines = json.loads((root / "baselines.json").read_text(encoding="utf-8"))
    committed = json.loads((PKG / "baselines.json").read_text(encoding="utf-8"))
    assert baselines == committed
    assert baselines["swarm"] == ["selfaware", "fuzzy66"]
    assert baselines["source"] == "policy_seed"
    xtx = baselines["policy"]["selfaware_rx_7900_xtx"]
    fuzzy = baselines["policy"]["fuzzy66_rx_6600_cheap_pass"]
    assert xtx == {"core_c": XTX_CORE_C, "hotspot_c": XTX_HOTSPOT_C, "authority": "gary"}
    assert fuzzy["core_c"] == FUZZY_CHEAP_PASS_CORE_C
    assert fuzzy["hotspot_c"] == FUZZY_CHEAP_PASS_HOTSPOT_C
    assert fuzzy["lane"] == "cheap_pass"
    assert fuzzy["authority"] == "fort_default_pending_gary_number"
    thermal = baselines["bots"]["thermal_gate"]
    assert thermal["metrics"]["core_c"]["warn"] == 80
    assert thermal["metrics"]["hotspot_c"]["warn"] == 88
    assert thermal["metrics"]["core_c"]["n"] == 0
    fuzzy_bot = baselines["bots"]["fuzzy66_thermal"]
    assert fuzzy_bot["lane"] == "cheap_pass"
    assert fuzzy_bot["metrics"]["core_c"]["warn"] == 70


def test_steady_thermal_csv_is_in_band(tmp_path):
    root = harness_root(tmp_path)
    init(root)
    collect(root, "thermal_gate", FIX / "thermal_steady.csv")
    code, payload = check(root)
    assert code == 0
    assert payload["exit_class"] == "ok"
    assert payload["events"] == []
    assert payload["counts"]["ok"] == 4
    again, second = check(root)
    assert again == 0
    assert second["counts"]["ok"] == 0
    assert (root / "events" / "anomalies.jsonl").exists() is False


def test_core_drift_is_a_lasso_before_the_policy_line(tmp_path):
    root = harness_root(tmp_path)
    init(root)
    collect(root, "thermal_gate", FIX / "thermal_core_drift.json")
    code, payload = check(root)
    assert code == 3
    core = [event for event in payload["events"] if event["metric"] == "core_c"]
    assert len(core) == 1
    event = core[0]
    assert event["kind"] == "lasso"
    assert event["consecutive"] == 1
    assert event["strike_limit"] == 3
    assert event["value"] == 71
    assert any(reason.startswith("baseline:") for reason in event["reasons"])
    assert not any(reason.startswith("policy:") for reason in event["reasons"])
    assert "before this becomes a third strike" in event["pullback"]
    assert "RX 7900 XTX" in event["pullback"]
    for key in EVENT_SCHEMA["required"]:
        assert key in event
    hotspot = [event for event in payload["events"] if event["metric"] == "hotspot_c"]
    assert hotspot == []


def test_policy_line_is_still_a_lasso_on_the_first_reading(tmp_path):
    root = harness_root(tmp_path)
    init(root)
    collect(root, "thermal_gate", FIX / "thermal_policy.json")
    code, payload = check(root)
    assert code == 3
    event = next(event for event in payload["events"] if event["metric"] == "core_c")
    assert event["kind"] == "lasso"
    assert event["consecutive"] == 1
    joined = " ".join(event["reasons"])
    assert "baseline:" in joined
    assert "policy:" in joined
    assert "80" in joined


def test_three_hot_readings_reach_strike_three(tmp_path):
    root = harness_root(tmp_path)
    init(root)
    collect(root, "thermal_gate", FIX / "thermal_three_strikes.json")
    code, payload = check(root)
    assert code == 4
    core = [event for event in payload["events"] if event["metric"] == "core_c"]
    assert [event["kind"] for event in core] == ["lasso", "lasso", "strike"]
    assert [event["consecutive"] for event in core] == [1, 2, 3]
    assert core[-1]["pullback"].startswith("Third strike.")
    assert not any(event["metric"] == "hotspot_c" for event in payload["events"])


def test_cold_reading_and_release(tmp_path):
    root = harness_root(tmp_path)
    init(root)
    collect(root, "thermal_gate", FIX / "thermal_cold.json")
    code, payload = check(root)
    assert code == 3
    event = next(event for event in payload["events"] if event["metric"] == "core_c")
    assert event["kind"] == "lasso"
    assert any("below" in reason for reason in event["reasons"])
    collect(root, "thermal_gate", FIX / "thermal_release.json")
    code, payload = check(root)
    assert code == 0
    release = next(event for event in payload["events"] if event["metric"] == "core_c")
    assert release["kind"] == "release"
    assert release["consecutive"] == 0
    assert release["pullback"] == ""
    streaks = json.loads((root / "events" / "streaks.json").read_text(encoding="utf-8"))
    assert "thermal_gate.core_c" not in streaks["open"]


def test_fuzzy_cheap_pass_lasso_uses_the_fort_default(tmp_path):
    root = harness_root(tmp_path)
    init(root)
    collect(root, "fuzzy66_thermal", FIX / "fuzzy_cheap_pass.json")
    code, payload = check(root)
    assert code == 3
    event = next(event for event in payload["events"] if event["metric"] == "core_c")
    assert event["kind"] == "lasso"
    assert event["host"] == "fuzzy66"
    assert event["consecutive"] == 1
    assert any(reason.startswith("baseline:") for reason in event["reasons"])
    assert not any(reason.startswith("policy:") for reason in event["reasons"])
    assert "cheap-pass" in event["pullback"]
    assert "RX 6600" in event["pullback"]


def test_trader_and_network_stubs_lasso_before_their_floors(tmp_path):
    root = harness_root(tmp_path)
    init(root)
    collect(root, "trader_scout", FIX / "trader_steady.json")
    collect(root, "network_master", FIX / "network_steady.json")
    code, payload = check(root)
    assert code == 0
    assert payload["events"] == []

    root = harness_root(tmp_path / "drift")
    init(root)
    collect(root, "trader_scout", FIX / "trader_slide.json")
    collect(root, "network_master", FIX / "network_early.json")
    code, payload = check(root)
    assert code == 3
    trader = next(event for event in payload["events"] if event["bot"] == "trader_scout")
    network = next(event for event in payload["events"] if event["bot"] == "network_master")
    assert trader["kind"] == "lasso"
    assert trader["value"] == -16
    assert not any(reason.startswith("policy:") for reason in trader["reasons"])
    assert "not a price and not an order" in trader["pullback"]
    assert network["kind"] == "lasso"
    assert network["value"] == 0.988
    assert not any(reason.startswith("policy:") for reason in network["reasons"])
    assert "does not open a socket" in network["pullback"]


def test_from_samples_replants_one_metric_and_leaves_the_rest(tmp_path):
    root = harness_root(tmp_path)
    init(root)
    source = tmp_path / "cores.csv"
    source.write_text(
        "timestamp,bot,metric,value\n"
        "2026-10-25T01:00:00Z,thermal_gate,core_c,10\n"
        "2026-10-25T01:05:00Z,thermal_gate,core_c,20\n",
        encoding="utf-8",
    )
    collect(root, "thermal_gate", source)
    code, _out, err = run(["--root", str(root), "baseline-init", "--from-samples"])
    assert code == 0, err
    baselines = json.loads((root / "baselines.json").read_text(encoding="utf-8"))
    core = baselines["bots"]["thermal_gate"]["metrics"]["core_c"]
    hotspot = baselines["bots"]["thermal_gate"]["metrics"]["hotspot_c"]
    assert baselines["source"] == "samples"
    assert core["n"] == 2
    assert core["mean"] == 15
    assert core["stddev"] == pytest.approx(50**0.5)
    assert core["warn"] == 80
    assert hotspot["n"] == 0
    assert hotspot["mean"] == 72
    assert hotspot["warn"] == 88


def test_unknown_metric_is_a_data_error_not_a_strike(tmp_path):
    root = harness_root(tmp_path)
    init(root)
    source = tmp_path / "typo.json"
    source.write_text(
        json.dumps(
            {
                "bot": "thermal_gate",
                "timestamp": "2026-10-25T08:00:00Z",
                "readings": {"coreC": 81},
            }
        ),
        encoding="utf-8",
    )
    collect(root, "thermal_gate", source)
    code, _out, err = run(["--root", str(root), "check"])
    assert code == 2
    assert "unknown metric coreC for thermal_gate" in err
    assert not (root / "events" / "anomalies.jsonl").exists()


def test_refuses_a_remote_source_and_a_trader_csv(tmp_path):
    root = harness_root(tmp_path)
    init(root)
    code, _out, err = run(
        ["--root", str(root), "collect", "--bot", "thermal_gate", "--source", "http://example.test/t.csv"]
    )
    assert code == 2
    assert "local file" in err
    code, _out, err = run(
        [
            "--root",
            str(root),
            "collect",
            "--bot",
            "trader_scout",
            "--source",
            str(FIX / "thermal_steady.csv"),
            "--format",
            "csv",
        ]
    )
    assert code == 2
    assert "does not compute live P&L" in err


def test_loosened_ceiling_is_refused(tmp_path):
    root = harness_root(tmp_path)
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    config["bots"]["thermal_gate"]["metrics"]["core_c"]["warn"] = 90
    (root / "config.json").write_text(json.dumps(config), encoding="utf-8")
    code, _out, err = run(["--root", str(root), "baseline-init"])
    assert code == 2
    assert "80" in err


def test_report_names_both_ceilings(tmp_path):
    root = harness_root(tmp_path)
    init(root)
    collect(root, "thermal_gate", FIX / "thermal_core_drift.json")
    assert check(root)[0] == 3
    code, out, err = run(["--root", str(root), "report"])
    assert code == 0, err
    assert "Gary policy: selfaware RX 7900 XTX core 80C / hotspot 88C" in out
    assert "Fort default (pending Gary's number): fuzzy66 RX 6600 cheap-pass core 70C / hotspot 80C" in out
    assert "lasso is ahead of strike-three" in out
    assert "swarm: selfaware, fuzzy66" in out
