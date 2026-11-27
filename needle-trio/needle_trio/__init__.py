"""Coder-trio needle router. Dry-run by default. Stdlib only.

Three coders (shallow / mid / deep) point with needles, vote confidence, and
gate the result with Kleene T/U/F. Nothing here launches a model.
"""

from .trinary import AND, F, IMPLIES, NOT, OR, T, U, Claim, to_gate, tv
from .trio import Needle, decide

__all__ = [
    "AND",
    "Claim",
    "F",
    "IMPLIES",
    "NOT",
    "Needle",
    "OR",
    "T",
    "U",
    "decide",
    "to_gate",
    "tv",
]

__version__ = "0.1.0"
