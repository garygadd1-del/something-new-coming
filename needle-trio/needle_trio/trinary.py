"""Kleene K3 (strong) truth values for coder-trio gating.

Values: T (true), F (false), U (unknown). Order for AND/OR: F < U < T.
  NOT:     T->F, F->T, U->U
  AND:     F dominates; else U if any U; else T      (= min)
  OR:      T dominates; else U if any U; else F      (= max)
  IMPLIES: OR(NOT a, b)

Depth (shallow / mid / deep) is a separate three-valued scale. It is not a
truth value. Claim truth stays T/U/F. The Chaos Ledger gate +1/0/-1
(ACCEPT/HOLD/REJECT) maps 1:1 onto T/U/F via to_gate().

Adapted from the staged Ara trinary module. Stdlib only. This module does not
load models, open secrets, or talk to the network.
"""

from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass, field

T, F, U = "T", "F", "U"
VALUES = (T, F, U)
_RANK = {F: 0, U: 1, T: 2}
NAMES = {T: "TRUE", F: "FALSE", U: "UNKNOWN"}


def tv(x):
    """Coerce bool/None/str/int to a truth value. None -> U. +1/0/-1 -> T/U/F."""
    if x is None:
        return U
    if isinstance(x, bool):
        return T if x else F
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return T if x > 0 else F if x < 0 else U
    s = str(x).strip().upper()
    if s in ("T", "TRUE", "YES", "ACCEPT", "VERIFIED", "PROMOTED", "+1", "1"):
        return T
    if s in ("F", "FALSE", "NO", "REJECT", "INCORRECT", "BLOCKED", "-1"):
        return F
    return U


def NOT(a):
    a = tv(a)
    return F if a == T else T if a == F else U


def AND(*xs):
    vals = [tv(x) for x in xs] or [T]
    return min(vals, key=_RANK.get)


def OR(*xs):
    vals = [tv(x) for x in xs] or [F]
    return max(vals, key=_RANK.get)


def IMPLIES(a, b):
    return OR(NOT(a), b)


def to_gate(v):
    """T/U/F -> Chaos Ledger gate +1/0/-1 (accept/hold/reject)."""
    return {T: 1, U: 0, F: -1}[tv(v)]


def label(v):
    return NAMES[tv(v)]


def now_et():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Claim:
    statement: str
    value: str = U
    confidence: float = 0.5
    source: str = ""
    timestamp: str = field(default_factory=now_et)

    def __post_init__(self):
        self.value = tv(self.value)
        self.confidence = float(self.confidence)
        # Nothing is TRUE without a source.
        if self.value == T and not (self.source or "").strip():
            self.value = U

    def merge(self, other):
        """Combine with another claim about the same statement.

        Agreement keeps the value. A lone U yields to a decided T or F.
        Disagreement (T vs F) never silently overwrites: it becomes U.
        """
        a, b = self.value, tv(other.value)
        if a == b:
            v = a
        elif U in (a, b):
            v = a if b == U else b
        else:
            v = U  # contradiction
        if v != U:
            confidence = max(self.confidence, other.confidence)
        else:
            confidence = min(self.confidence, other.confidence)
        source = "; ".join(s for s in (self.source, other.source) if s)
        return Claim(self.statement, v, confidence, source, now_et())

    def as_dict(self):
        return asdict(self)


def truth_table():
    rows = ["a b | NOT a | a AND b | a OR b | a->b"]
    for a in (T, U, F):
        for b in (T, U, F):
            rows.append(
                "%s %s |   %s   |    %s    |   %s    |  %s"
                % (a, b, NOT(a), AND(a, b), OR(a, b), IMPLIES(a, b))
            )
    return "\n".join(rows)


# Expected Kleene cells, used by tests and by anyone checking the table by hand.
# Row order is a in (T, U, F), b in (T, U, F): NOT a, AND, OR, IMPLIES.
KLEENE_ROWS = (
    # a, b, NOT a, AND, OR, IMPLIES
    (T, T, F, T, T, T),
    (T, U, F, U, T, U),
    (T, F, F, F, T, F),
    (U, T, U, U, T, T),
    (U, U, U, U, U, U),
    (U, F, U, F, U, U),
    (F, T, T, F, T, T),
    (F, U, T, F, U, T),
    (F, F, T, F, F, T),
)


if __name__ == "__main__":
    print(truth_table())
