"""Claim.merge: agreement keeps the value; T against F becomes U."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from needle_trio.trinary import F, T, U, Claim  # noqa: E402


class ClaimMergeTests(unittest.TestCase):
    def test_true_requires_a_source(self):
        claim = Claim("ports are local", T, 0.99, "")
        self.assertEqual(claim.value, U)

    def test_contradiction_becomes_unknown(self):
        left = Claim("listen port is 5031", T, 0.9, "config/experts.fuzzy66.json")
        right = Claim("listen port is 5031", F, 0.4, "note")
        merged = left.merge(right)
        self.assertEqual(merged.value, U)
        self.assertEqual(merged.confidence, 0.4)
        self.assertEqual(merged.statement, left.statement)
        self.assertIn("experts.fuzzy66.json", merged.source)
        self.assertIn("note", merged.source)

    def test_agreement_keeps_value_and_higher_confidence(self):
        left = Claim("inference target is loopback", T, 0.4, "readme")
        right = Claim("inference target is loopback", T, 0.8, "proxy")
        merged = left.merge(right)
        self.assertEqual(merged.value, T)
        self.assertEqual(merged.confidence, 0.8)
        self.assertEqual(merged.source, "readme; proxy")

    def test_unknown_yields_to_a_decided_value(self):
        decided = Claim("hermes is the deep coder", T, 0.55, "experts")
        unknown = Claim("hermes is the deep coder", U, 0.95, "")
        merged = decided.merge(unknown)
        self.assertEqual(merged.value, T)
        self.assertEqual(merged.confidence, 0.95)

        false_claim = Claim("cloud api allowed", F, 0.7, "hard-rule")
        merged_false = false_claim.merge(unknown)
        self.assertEqual(merged_false.value, F)

    def test_unsourced_true_cannot_be_smuggled_through_merge(self):
        sourced = Claim("fact", T, 0.5, "file")
        smuggled = Claim("fact", T, 0.99, "")
        self.assertEqual(smuggled.value, U)
        merged = sourced.merge(smuggled)
        self.assertEqual(merged.value, T)
        self.assertEqual(merged.source, "file")

    def test_false_agreement(self):
        merged = Claim("cloud llm", F, 0.2, "a").merge(Claim("cloud llm", F, 0.6, "b"))
        self.assertEqual(merged.value, F)
        self.assertEqual(merged.confidence, 0.6)

    def test_both_unknown(self):
        merged = Claim("unseen", U, 0.2, "").merge(Claim("unseen", U, 0.8, "maybe"))
        self.assertEqual(merged.value, U)
        self.assertEqual(merged.confidence, 0.2)


if __name__ == "__main__":
    unittest.main()
