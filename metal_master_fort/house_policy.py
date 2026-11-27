"""House thermal policy for the Metal Master Fort.

Gary's standing caps are dated 2026-11-25. A tighter ceiling is allowed.
A looser ceiling is refused. A None ceiling is OPEN: do not invent a number.

The planted swarm list is SelfAware and Fuzzy 66 only. Throne holds the
RX 7900 XTX and is not on that list until the owner says so.
"""

from __future__ import annotations

SELF_AWARE = "selfaware"
FUZZY66 = "fuzzy66"
SWARM = (SELF_AWARE, FUZZY66)

THRONE = "throne"
STANDING_CAPS = "2026-11-25"
AUTHORITY_GARY = "gary"

XTX_GPU = "rx_7900_xtx"
XTX_CORE_C = 86
XTX_HOTSPOT_C = 88
XTX_LOAD_PCT = 80

GPU_9070 = "rx_9070"
CORE_9070_C = 85

GPU_1650 = "gtx_1650"
CORE_1650_C = 80

GRE_GPU = "rx_7900_gre"

STRIKE_LIMIT = 3

# Standing caps. Fuzzy 66's GRE ceiling stays None (OPEN).
# The older cards were pulled: the PSU cannot run the GRE plus those cards.
GARY_CAPS = (
    {
        "machine": THRONE,
        "gpu": XTX_GPU,
        "core_c": XTX_CORE_C,
        "hotspot_c": XTX_HOTSPOT_C,
        "load_pct": XTX_LOAD_PCT,
        "authority": AUTHORITY_GARY,
        "standing_caps": STANDING_CAPS,
    },
    {
        "machine": SELF_AWARE,
        "gpu": GPU_9070,
        "core_c": CORE_9070_C,
        "hotspot_c": None,
        "load_pct": None,
        "authority": AUTHORITY_GARY,
        "standing_caps": STANDING_CAPS,
    },
    {
        "machine": SELF_AWARE,
        "gpu": GPU_1650,
        "core_c": CORE_1650_C,
        "hotspot_c": None,
        "load_pct": None,
        "authority": AUTHORITY_GARY,
        "standing_caps": STANDING_CAPS,
    },
    {
        "machine": FUZZY66,
        "gpu": GRE_GPU,
        "core_c": None,
        "hotspot_c": None,
        "load_pct": None,
        "authority": None,
        "standing_caps": None,
    },
)

POLICY_NOTE = (
    "Gary standing caps 2026-11-25. "
    "Throne RX 7900 XTX: 86C core, 88C hotspot, 80% load. "
    "SelfAware RX 9070: 85C core. Hotspot and load are OPEN. "
    "SelfAware GTX 1650: 80C core. Hotspot and load are OPEN. "
    "Fuzzy 66 has only the RX 7900 GRE. Its ceiling is OPEN. "
    "The older cards were pulled because the PSU cannot run the GRE plus those cards. "
    "Throne is not on the planted swarm list."
)


def standing_policy() -> dict:
    """The harness policy seed. The GRE is absent because its ceiling is OPEN."""
    return {
        "throne_rx_7900_xtx": {
            "core_c": XTX_CORE_C,
            "hotspot_c": XTX_HOTSPOT_C,
            "load_pct": XTX_LOAD_PCT,
            "authority": AUTHORITY_GARY,
            "standing_caps": STANDING_CAPS,
        },
        "selfaware_rx_9070": {
            "core_c": CORE_9070_C,
            "hotspot_c": None,
            "load_pct": None,
            "authority": AUTHORITY_GARY,
            "standing_caps": STANDING_CAPS,
        },
        "selfaware_gtx_1650": {
            "core_c": CORE_1650_C,
            "hotspot_c": None,
            "load_pct": None,
            "authority": AUTHORITY_GARY,
            "standing_caps": STANDING_CAPS,
        },
    }


class PolicyError(ValueError):
    """A host or a ceiling is outside the house policy."""


def assert_swarm(hosts) -> None:
    unknown = sorted({host for host in hosts if host not in SWARM})
    if unknown:
        raise PolicyError(
            "swarm is selfaware and fuzzy66 only; refused host " + ", ".join(unknown)
        )
