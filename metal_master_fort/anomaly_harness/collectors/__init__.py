"""Local collectors. Thermal, trader, and network read files. None open a socket."""

from anomaly_harness.collectors.network import collect_network
from anomaly_harness.collectors.thermal import collect_thermal
from anomaly_harness.collectors.trader import collect_trader

COLLECTORS = {
    "thermal": collect_thermal,
    "trader": collect_trader,
    "network": collect_network,
}

__all__ = ["COLLECTORS", "collect_network", "collect_thermal", "collect_trader"]
