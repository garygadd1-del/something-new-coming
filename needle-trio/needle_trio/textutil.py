"""Lexical helpers for needle pointers. Stdlib only."""

from __future__ import annotations

import math
import re

STOP = set(
    """a an the and or of to in on for with by is are was were be been it this that these those
    what which who whom how why when where do does did can could should would will shall may might
    i me my we our you your he she they them their his her its as at from about into than then so
    if not no yes vs versus please tell explain give list show ara""".split()
)

SYN = {
    "microentity": ["micro", "entity"],
    "smallentity": ["small", "entity"],
    "llcs": ["llc"],
    "yc": ["combinator"],
    "tm": ["trademark"],
    "ein": ["ein", "employer", "identification"],
}


def terms_of(text, limit=24):
    toks = []
    for t in re.findall(r"[A-Za-z0-9]+", (text or "").lower()):
        toks += SYN.get(t, [t])
    out, seen = [], set()
    for t in toks:
        if t in STOP or len(t) < 2 or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out[:limit]


def stem(token):
    return token[:5] if len(token) > 5 else token


def coverage(terms, text):
    """Fraction of query terms found in text.

    Damped when fewer than two terms match. One shared word is not evidence.
    """
    low = (text or "").lower()
    if not terms:
        return 0.0
    hit = sum(1 for t in terms if stem(t) in low)
    return (hit / len(terms)) * min(1.0, hit / 2.0)


def strength(bm25_score, nterms):
    if bm25_score is None:
        return 0.0
    return 1 - math.exp(-abs(bm25_score) / (3.0 * math.sqrt(max(1, nterms))))


def fts_match(terms):
    """FTS5 MATCH string. Terms are already alphanumeric; quotes keep them literal."""
    return " OR ".join('"%s"' % t.replace('"', "") for t in terms)


def clamp01(value):
    return max(0.0, min(1.0, float(value)))


def evidence_thickness(coverage_value, bm25_strength, hits, k, breadth):
    """Needle thickness in [0, 1].

    ``breadth`` is the trinary-depth window: shallow is a thin slice, deep is wide.
    Empty hits are thickness 0.
    """
    if hits <= 0 or k <= 0:
        return 0.0
    fill = hits / float(k)
    mass = (0.65 * clamp01(coverage_value)) + (0.35 * clamp01(bm25_strength))
    return clamp01(clamp01(breadth) * mass * (0.55 + 0.45 * min(1.0, fill)))
