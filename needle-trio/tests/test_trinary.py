"""Kleene K3 truth table for the coder-trio gate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from needle_trio.trinary import (  # noqa: E402
    AND,
    F,
    IMPLIES,
    KLEENE_ROWS,
    NOT,
    OR,
    T,
    U,
    label,
    to_gate,
    truth_table,
    tv,
)


class TruthTableTests(unittest.TestCase):
    def test_kleene_rows(self):
        self.assertEqual(len(KLEENE_ROWS), 9)
        for a, b, not_a, and_ab, or_ab, implies in KLEENE_ROWS:
            self.assertEqual(NOT(a), not_a)
            self.assertEqual(AND(a, b), and_ab)
            self.assertEqual(OR(a, b), or_ab)
            self.assertEqual(IMPLIES(a, b), implies)

    def test_truth_table_text_covers_every_pair(self):
        text = truth_table()
        self.assertTrue(text.startswith("a b | NOT a | a AND b | a OR b | a->b"))
        body = text.splitlines()[1:]
        self.assertEqual(len(body), 9)
        for a, b, *_rest in KLEENE_ROWS:
            self.assertTrue(any(line.startswith("%s %s |" % (a, b)) for line in body))

    def test_empty_and_or_identities(self):
        self.assertEqual(AND(), T)
        self.assertEqual(OR(), F)

    def test_not_unknown_stays_unknown(self):
        self.assertEqual(NOT(U), U)
        self.assertEqual(NOT(NOT(T)), T)
        self.assertEqual(NOT(NOT(F)), F)

    def test_coercion(self):
        self.assertEqual(tv(None), U)
        self.assertEqual(tv(True), T)
        self.assertEqual(tv(False), F)
        self.assertEqual(tv(1), T)
        self.assertEqual(tv(0), U)
        self.assertEqual(tv(-1), F)
        self.assertEqual(tv(0.5), T)
        self.assertEqual(tv("yes"), T)
        self.assertEqual(tv("ACCEPT"), T)
        self.assertEqual(tv("reject"), F)
        self.assertEqual(tv("maybe"), U)
        self.assertEqual(tv("+1"), T)
        self.assertEqual(tv("-1"), F)

    def test_gate_and_label(self):
        self.assertEqual(to_gate(T), 1)
        self.assertEqual(to_gate(U), 0)
        self.assertEqual(to_gate(F), -1)
        self.assertEqual(to_gate(True), 1)
        self.assertEqual(to_gate(None), 0)
        self.assertEqual(label(T), "TRUE")
        self.assertEqual(label("no"), "FALSE")
        self.assertEqual(label(None), "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
