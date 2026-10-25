"""Drift math for the anomaly harness.

A baseline is a planted post. Collect does not move it. Check measures how
far the new reading is from that post.

The first drift is a lasso: catch it, and say how to pull it back, while the
streak is still 1 or 2. Strike-three is the alarm people learn to ignore when
it is the only signal. The harness writes the lasso before that.
"""

from __future__ import annotations

from anomaly_harness.errors import HarnessError


def fmt(value: float) -> str:
    return format(float(value), ".6g")


def band_width(metric: dict) -> float:
    return max(float(metric["drift_abs"]), float(metric["drift_k"]) * float(metric["stddev"]))


def judge(value: float, metric: dict) -> list[str]:
    """Return reason strings. An empty list means the reading is in band."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HarnessError(f"metric value is not a number: {value!r}")
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise HarnessError("metric value is not finite")

    mean = float(metric["mean"])
    band = band_width(metric)
    reasons: list[str] = []
    side = metric["baseline"]
    if side in ("high", "both") and number > mean + band:
        reasons.append(
            f"baseline: {fmt(number)} is above {fmt(mean)} by more than {fmt(band)}"
        )
    if side in ("low", "both") and number < mean - band:
        reasons.append(
            f"baseline: {fmt(number)} is below {fmt(mean)} by more than {fmt(band)}"
        )

    warn = float(metric["warn"])
    policy = metric["policy"]
    if policy == "ceiling" and number >= warn:
        reasons.append(f"policy: {fmt(number)} crossed ceiling {fmt(warn)}")
    elif policy == "floor" and number <= warn:
        reasons.append(f"policy: {fmt(number)} crossed floor {fmt(warn)}")

    span = metric.get("span")
    if span is not None:
        low, high = float(span[0]), float(span[1])
        if number < low or number > high:
            reasons.append(f"span: {fmt(number)} outside {fmt(low)}..{fmt(high)}")
    return reasons


def apply_streak(is_drift: bool, previous: int, strike_limit: int) -> tuple[str, int]:
    """Map one reading onto ok, release, lasso, or strike.

    ``previous`` is the consecutive drift count before this reading.
    """
    if strike_limit < 1:
        raise HarnessError("strike_limit must be at least 1")
    if not is_drift:
        if previous > 0:
            return "release", 0
        return "ok", 0
    count = previous + 1
    if count >= strike_limit:
        return "strike", count
    return "lasso", count


def pullback(bot: dict, kind: str) -> str:
    if kind not in ("lasso", "strike"):
        return ""
    gpu = bot.get("gpu")
    if gpu == "rx_7900_xtx":
        text = "ease the RX 7900 XTX load on selfaware"
    elif gpu == "rx_6600":
        text = "hold the RX 6600 on the cheap-pass lane"
    elif bot.get("collector") == "trader":
        text = (
            "pause new trader-scout risk. "
            "This flag is a drift from the baseline, not a price and not an order"
        )
    elif bot.get("collector") == "network":
        text = "network-master uptime left its baseline. This harness does not open a socket"
    else:
        text = "pull this metric back toward its baseline"
    if kind == "lasso":
        return f"Lasso: {text} before this becomes a third strike."
    return f"Third strike. {text[0].upper()}{text[1:]}."
