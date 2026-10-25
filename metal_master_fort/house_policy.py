"""House thermal policy for the Metal Master Fort.

The swarm is SelfAware and Fuzzy 66 only.

RX 7900 XTX core 80C / hotspot 88C is Gary's line.
RX 6600 cheap-pass core 70C / hotspot 80C is a fort default until Gary
writes that number. Do not treat the fort default as Gary's line.
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
