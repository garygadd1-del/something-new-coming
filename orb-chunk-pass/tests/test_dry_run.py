"""Dry-run output never describes a launched Godot process."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from orb_chunk.cli import main

WIDE_T0 = [
    "godot",
    "--path",
    r"C:\AGIOS\Sandbox\Render_Chunks_20261022\src\landfall",
    "--resolution",
    "1280x720",
    "res://scenes/showcase.tscn",
    "--",
    "--plan=C:/AGIOS/Sandbox/Render_Chunks_20261022/plans/plan_s07.json",
    "--stage=5",
    "--seq=240",
    "--fps=12",
    "--t0=0",
    "--zoom=0.6",
    "--follow=0",
    "--outdir=C:/AGIOS/Sandbox/Render_Chunks_20261022/out/v2/lf_s07_wide_t0",
]

MID = [
    "godot",
    "--path",
    r"C:\AGIOS\Sandbox\Render_Chunks_20261022\src\landfall",
    "--resolution",
    "1280x720",
    "res://scenes/showcase.tscn",
    "--",
    "--plan=C:/AGIOS/Sandbox/Render_Chunks_20261022/plans/plan_s11.json",
    "--stage=5",
    "--seq=240",
    "--fps=12",
    "--t0=20",
    "--zoom=1.0",
    "--follow=1",
    "--outdir=C:/AGIOS/Sandbox/Render_Chunks_20261022/out/v2/lf_s11_mid_t20",
]


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    out = StringIO()
    err = StringIO()
    with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class DryRunTest(unittest.TestCase):
    def test_package_has_no_process_launcher(self):
        banned = ("subprocess", "os.system", "os.exec", "Popen", "Start-Process", "CreateProcess")
        for path in (ROOT / "orb_chunk").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in banned:
                self.assertNotIn(token, text, f"{path.name} contains {token}")

    def test_no_execute_command(self):
        err = StringIO()
        with mock.patch("sys.stderr", err), self.assertRaises(SystemExit) as caught:
            main(["execute"])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("invalid choice", err.getvalue())

    def test_dry_run_json_argv(self):
        with mock.patch("subprocess.Popen", side_effect=AssertionError("spawn")), mock.patch(
            "subprocess.run", side_effect=AssertionError("spawn")
        ), mock.patch("os.system", side_effect=AssertionError("spawn")):
            code, out, err = run_cli(["dry-run", "--id", "lf_s11_mid_t20", "--format", "json"])
        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")
        payload = json.loads(out)
        self.assertIs(payload["dry_run"], True)
        self.assertIs(payload["godot_invoked"], False)
        self.assertEqual(payload["job_count"], 1)
        self.assertEqual(payload["jobs"][0]["argv"], MID)
        self.assertEqual(payload["jobs"][0]["camera"], "mid")
        self.assertEqual(payload["jobs"][0]["t0"], 20)

        code, out, err = run_cli(["dry-run", "--id", "lf_s07_wide_t0", "--format", "json"])
        self.assertEqual(json.loads(out)["jobs"][0]["argv"], WIDE_T0)

    def test_dry_run_text_says_godot_is_idle(self):
        code, out, err = run_cli(["dry-run", "--order", "camera", "--id", "lf_s11_mid_t20"])
        self.assertEqual(code, 0, err)
        self.assertIn("Godot is not started.", out)
        self.assertIn("godot_invoked: false", out)
        self.assertIn("id: lf_s11_mid_t20", out)
        self.assertIn("--zoom=1.0", out)
        self.assertIn("--follow=1", out)
        self.assertIn("--t0=20", out)
        self.assertNotIn("mode: execute", out)

    def test_validate_and_preflight(self):
        code, out, err = run_cli(["validate"])
        self.assertEqual(code, 0, err)
        self.assertIn("Godot is not started.", out)
        self.assertIn("jobs: 54", out)
        self.assertIn("wide: 18", out)
        self.assertIn("close: 18", out)
        self.assertIn("mid: 18", out)
        self.assertIn("execute: false", out)

        code, out, err = run_cli(["preflight"])
        self.assertEqual(code, 0, err)
        self.assertIn("No-Limit Local", out)
        self.assertIn("execute: false", out)
        for name in ("plan_s07.json", "plan_s101.json", "plan_s11.json", "plan_s23.json", "plan_s42.json", "plan_s77.json"):
            self.assertIn(name, out)

    def test_unknown_id_is_an_error(self):
        code, out, err = run_cli(["list", "--id", "lf_s07_wide_t99"])
        self.assertEqual(code, 2)
        self.assertIn("unknown id", err)
        self.assertEqual(out, "")

    def test_camera_order_groups_stages(self):
        code, out, err = run_cli(["dry-run", "--order", "camera", "--format", "json"])
        self.assertEqual(code, 0, err)
        jobs = json.loads(out)["jobs"]
        self.assertEqual(len(jobs), 54)
        self.assertTrue(all(job["camera"] == "wide" for job in jobs[:18]))
        self.assertTrue(all(job["camera"] == "close" for job in jobs[18:36]))
        self.assertTrue(all(job["camera"] == "mid" for job in jobs[36:]))
        self.assertEqual(jobs[0]["id"], "lf_s07_wide_t0")
        self.assertEqual(jobs[18]["id"], "lf_s07_close_t0")
        self.assertEqual(jobs[36]["id"], "lf_s07_mid_t0")


if __name__ == "__main__":
    unittest.main()
