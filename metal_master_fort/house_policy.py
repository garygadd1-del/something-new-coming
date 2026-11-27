"""House thermal policy for the Metal Master Fort.

The planted swarm list is SelfAware and Fuzzy 66 only. Throne is in the
hardware inventory below and is not on that list until the owner says so.

The constants further down are the anomaly harness seed. That seed still
labels a selfaware RX 7900 XTX line at 80C core / 88C hotspot, and a fuzzy66
RX 6600 cheap-pass line at 70C core / 80C hotspot. OBSERVED_HARDWARE is the
corrected inventory. Ceilings there are OPEN until the owner sets them.

A tighter ceiling than a planted number is allowed. A looser one is refused.
"""

from __future__ import annotations

SELF_AWARE = "selfaware"
FUZZY66 = "fuzzy66"
SWARM = (SELF_AWARE, FUZZY66)

XTX_GPU = "rx_7900_xtx"
XTX_LANE = "primary"
XTX_CORE_C = 80
XTX_HOTSPOT_C = 88

FUZZY_GPU = "rx_6600"
FUZZY_LANE = "cheap_pass"
FUZZY_CHEAP_PASS_CORE_C = 70
FUZZY_CHEAP_PASS_HOTSPOT_C = 80

STRIKE_LIMIT = 3

# Observed hardware. These are not ceilings and they do not replace the seed.
# A ceiling the owner has not set stays None (OPEN). Do not invent one.
OBSERVED_HARDWARE = (
    {
        "machine": "throne",
        "gpu": "rx_7900_xtx",
        "observed_core_c": 86,
        "observed_hotspot_c": 88,
        "observed_load_pct": 80,
        "ceiling": None,
    },
    {
        "machine": "selfaware",
        "gpu": "rx_9070",
        "observed_core_c": 85,
        "observed_hotspot_c": None,
        "observed_load_pct": None,
        "ceiling": None,
    },
    {
        "machine": "selfaware",
        "gpu": "gtx_1650",
        "observed_core_c": 80,
        "observed_hotspot_c": None,
        "observed_load_pct": None,
        "ceiling": None,
    },
    {
        "machine": "fuzzy66",
        "gpu": "rx_7900_gre",
        "also": "older cards",
        "observed_core_c": None,
        "observed_hotspot_c": None,
        "observed_load_pct": None,
        "ceiling": None,
    },
)

POLICY_NOTE = (
    "RX 7900 XTX warn lines are Gary's house policy: 80C core, 88C hotspot. "
    "RX 6600 cheap-pass warn lines are fort defaults, 70C core and 80C hotspot, "
    "until Gary writes the house numbers."
)


class PolicyError(ValueError):
    """A host or a ceiling is outside the house policy."""


def assert_swarm(hosts) -> None:
    unknown = sorted({host for host in hosts if host not in SWARM})
    if unknown:
        raise PolicyError(
            "swarm is selfaware and fuzzy66 only; refused host " + ", ".join(unknown)
        )
