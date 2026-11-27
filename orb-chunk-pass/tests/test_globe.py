"""Globe tile plan and the Windows runner's execute gate."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from orb_chunk.cli import main
from orb_chunk.globe import all_tile_ids, argument_list, parse_passes, plan, tile_ids

RUNNER = ROOT / "scripts" / "globe_runner.ps1"
MARKER = "# --- execute gate: Godot starts only below this line ---"
FLAGS = [
    "--path",
    "--windowed",
    "--resolution",
    "--",
    "--worker",
    "--no-auto",
    "--no-link",
]


def _argv_for_row_a_trace() -> list[str]:
    tiles = [f"A{number:02d}" for number in range(1, 27)]
    return [
        "godot",
        "--path",
        r"C:\AGIOS\Sandbox\Render_Chunks_20261022\src\ara_body",
        "--windowed",
        "--resolution",
        "1024x1024",
        "res://refrender/globe_shot.tscn",
        "--",
        "--worker",
        "--no-auto",
        "--no-link",
        "--pass=trace",
        "--tiles=" + ",".join(tiles),
        "--outdir=C:/AGIOS/Sandbox/Render_Chunks_20261022/out/globe/trace",
    ]


class GlobePlanTest(unittest.TestCase):
    def test_tile_ids(self):
        self.assertEqual(tile_ids("A")[0], "A01")
        self.assertEqual(tile_ids("A")[-1], "A26")
        self.assertEqual(tile_ids("Z")[0], "Z01")
        self.assertEqual(tile_ids("Z")[-1], "Z26")
        self.assertEqual(len(all_tile_ids()), 676)
        self.assertEqual(len(set(all_tile_ids())), 676)

    def test_full_grid_argv(self):
        jobs = plan(passes=["trace", "shade"])
        self.assertEqual(len(jobs), 52)
        self.assertEqual(jobs[0]["row"], "A")
        self.assertEqual(jobs[0]["pass"], "trace")
        self.assertEqual(jobs[1]["pass"], "shade")
        self.assertEqual(jobs[2]["row"], "B")
        self.assertEqual(jobs[0]["argv"], _argv_for_row_a_trace())
        self.assertEqual(
            jobs[0]["argv"],
            argument_list(
                godot="godot",
                project=r"C:\AGIOS\Sandbox\Render_Chunks_20261022\src\ara_body",
                resolution="1024x1024",
                scene="res://refrender/globe_shot.tscn",
                pass_name="trace",
                tiles=tile_ids("A"),
                outdir=r"C:\AGIOS\Sandbox\Render_Chunks_20261022\out\globe\trace",
            ),
        )
        positions = [jobs[0]["argv"].index(flag) for flag in FLAGS]
        self.assertEqual(positions, sorted(positions))

    def test_existing_png_is_omitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "trace"
            folder.mkdir()
            (folder / "tile_A01.png").write_bytes(b"png")
            jobs = plan(passes=["trace"], existing={("trace", "A01")})
            row_a = jobs[0]
            self.assertEqual(row_a["tiles"][0], "A02")
            self.assertEqual(len(row_a["tiles"]), 25)
            self.assertNotIn("A01", row_a["argv"][-2])

    def test_bad_pass(self):
        with self.assertRaises(Exception):
            parse_passes("trace,bake")

    def test_out_root_skips_existing_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "trace"
            folder.mkdir()
            (folder / "tile_A01.png").write_bytes(b"png")
            out = StringIO()
            with mock.patch("sys.stdout", out):
                code = main(
                    ["globe-dry-run", "--format", "json", "--passes", "trace", "--out-root", tmp]
                )
            self.assertEqual(code, 0)
            job = json.loads(out.getvalue())["jobs"][0]
            self.assertEqual(job["tiles"][0], "A02")
            self.assertEqual(len(job["tiles"]), 25)
            self.assertNotIn("A01", job["tiles"])

    def test_cli_globe_dry_run(self):
        out = StringIO()
        with mock.patch("subprocess.Popen", side_effect=AssertionError("spawn")), mock.patch(
            "sys.stdout", out
        ):
            code = main(["globe-dry-run", "--format", "json", "--passes", "trace"])
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertIs(payload["dry_run"], True)
        self.assertIs(payload["godot_invoked"], False)
        self.assertEqual(payload["process_starts"], 26)
        self.assertEqual(payload["jobs"][0]["argv"], _argv_for_row_a_trace())

        text = StringIO()
        with mock.patch("sys.stdout", text):
            code = main(["globe-dry-run", "--passes", "trace", "--node", "throne"])
        self.assertEqual(code, 0)
        printed = text.getvalue()
        self.assertIn("Godot is not started.", printed)
        self.assertIn("node: throne", printed)
        self.assertIn("process_starts: 26", printed)
        self.assertNotIn("mode: execute", printed)


class RunnerGateTest(unittest.TestCase):
    def test_execute_side_effects_stay_below_the_gate(self):
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("No-Limit Local", text)
        self.assertIn(MARKER, text)
        self.assertEqual(text.count("Start-Process"), 1)
        head, tail = text.split(MARKER, 1)
        for token in (
            "Start-Process",
            "powershell.exe",
            "Stop-Process",
            "Add-Content",
            "Set-Content",
            "WriteAllLines",
            "New-Item",
            "Invoke-Expression",
        ):
            self.assertNotIn(token, head, token)
        self.assertIn("Start-Process", tail)
        self.assertIn("powershell.exe", tail)
        self.assertIn("[string]$Godot = ''", text)
        for flag in FLAGS:
            self.assertIn(flag, text)
        self.assertLess(text.index("--windowed"), text.index("--worker"))
        self.assertLess(text.index("--worker"), text.index("--no-auto"))
        self.assertLess(text.index("--no-auto"), text.index("--no-link"))

    @unittest.skipUnless(shutil.which("pwsh"), "pwsh not installed")
    def test_pwsh_dry_run_does_not_execute(self):
        proc = subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(RUNNER)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("mode: dry-run", proc.stdout)
        self.assertIn("Godot is not started.", proc.stdout)
        self.assertIn("process_starts: 52", proc.stdout)
        self.assertIn("row=A pass=trace tiles=26", proc.stdout)
        self.assertIn("--pass=trace", proc.stdout)
        self.assertNotIn("mode: execute", proc.stdout)
        refused = subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(RUNNER), "-Execute"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertNotEqual(refused.returncode, 0)
        combined = refused.stdout + refused.stderr
        self.assertIn("requires -Godot", combined)
        self.assertNotIn("mode: execute", combined)


if __name__ == "__main__":
    unittest.main()
