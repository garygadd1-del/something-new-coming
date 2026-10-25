"""PASS_PLAN.md lists every captured chunk id under the right stage."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from orb_chunk.queue import load_queue

PLAN = ROOT / "PASS_PLAN.md"
README = ROOT / "README.md"
ID_RE = re.compile(r"lf_s\d+_(?:wide|close|mid)_t\d+")


class PassPlanTest(unittest.TestCase):
    def test_stage_sections_match_the_queue(self):
        doc = load_queue()
        expected = {
            "wide": {job["id"] for job in doc["jobs"] if job["camera"] == "wide"},
            "close": {job["id"] for job in doc["jobs"] if job["camera"] == "close"},
            "mid": {job["id"] for job in doc["jobs"] if job["camera"] == "mid"},
        }
        text = PLAN.read_text(encoding="utf-8")
        parts = re.split(r"(?m)^## Stage (wide|close|mid)\s*$", text)
        self.assertGreaterEqual(len(parts), 7)
        bodies = {}
        index = 1
        while index < len(parts) - 1:
            bodies[parts[index]] = set(ID_RE.findall(parts[index + 1].split("\n## ")[0]))
            index += 2
        self.assertEqual(set(bodies), {"wide", "close", "mid"})
        for camera, ids in expected.items():
            self.assertEqual(bodies[camera], ids)
        self.assertEqual(len(expected["wide"] & expected["close"]), 0)
        self.assertIn("## Handoff for No-Limit Local", text)
        self.assertIn("No-Limit Local", text)
        self.assertIn("A01", text)
        self.assertIn("Z26", text)
        self.assertIn("trace", text)
        self.assertIn("shade", text)
        self.assertIn("Fuzzy66", text)

    def test_readme_points_at_the_gate(self):
        text = README.read_text(encoding="utf-8")
        self.assertIn("No-Limit Local", text)
        self.assertIn("python3 -m orb_chunk", text)
        self.assertIn("--execute", text)
        self.assertIn("-Execute", text)


if __name__ == "__main__":
    unittest.main()
