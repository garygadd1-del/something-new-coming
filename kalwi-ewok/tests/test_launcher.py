import os
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout

from kalwi_ewok.config import load_roles
from kalwi_ewok.launcher import CmdResult, execute_plan, main
from kalwi_ewok.plan import build_plan

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "abcdef12"


def _explode(argv):
    raise AssertionError(f"runtime invoked: {argv}")


class LauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roles = load_roles(ROOT / "roles")

    def test_dry_run_writes_nothing_and_skips_the_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp) / "runs"
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = main(
                    [
                        "--role",
                        "kalwi-render",
                        "--run-id",
                        RUN_ID,
                        "--log-dir",
                        str(log_dir),
                    ],
                    runner=_explode,
                )
            self.assertEqual(code, 0)
            self.assertIn("dry-run", stdout.getvalue())
            self.assertIn("ewok-render-abcdef12", stdout.getvalue())
            self.assertFalse(log_dir.exists())

    def test_env_var_does_not_enable_execute(self):
        os.environ["KALWI_EWOK_EXECUTE"] = "1"
        try:
            with redirect_stdout(StringIO()):
                code = main(
                    ["--role", "kalwi-scout", "--run-id", RUN_ID, "--log-dir", "/tmp/kalwi-ewok-unused"],
                    runner=_explode,
                )
        finally:
            del os.environ["KALWI_EWOK_EXECUTE"]
        self.assertEqual(code, 0)

    def test_all_roles_dry_run(self):
        for role in ("kalwi-render", "kalwi-ledger", "kalwi-scout"):
            for runtime in ("docker", "podman-none", "podman-netns"):
                stdout = StringIO()
                with redirect_stdout(stdout):
                    code = main(
                        ["--role", role, "--runtime", runtime, "--run-id", RUN_ID],
                        runner=_explode,
                    )
                self.assertEqual(code, 0, stdout.getvalue())
                self.assertIn(role, stdout.getvalue())
                self.assertNotIn("--gpus", stdout.getvalue())

    def test_execute_captures_logs_and_removes_only_this_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp) / "runs"
            calls = []

            def runner(argv):
                calls.append(list(argv))
                if argv[1] == "run":
                    return CmdResult(0, "kalwi-ewok: die-clean role=kalwi-render\n", "")
                if argv[1] == "rm":
                    return CmdResult(1, "", "Error: No such container: ewok-render-abcdef12\n")
                return CmdResult(0, "", "")

            stderr = StringIO()
            with redirect_stderr(stderr):
                code = main(
                    [
                        "--role",
                        "kalwi-render",
                        "--execute",
                        "--run-id",
                        RUN_ID,
                        "--log-dir",
                        str(log_dir),
                    ],
                    runner=runner,
                )
            self.assertEqual(code, 0)
            self.assertEqual((log_dir / f"{RUN_ID}-kalwi-render.log").read_text(encoding="utf-8"),
                             "kalwi-ewok: die-clean role=kalwi-render\n")
            self.assertEqual(calls[0][0:2], ["docker", "run"])
            self.assertEqual(calls[1], ["docker", "rm", "-f", "ewok-render-abcdef12"])
            self.assertIn("removing container ewok-render-abcdef12", stderr.getvalue())

    def test_failed_run_still_removes_the_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = _docker_plan(self.roles, Path(tmp))
            calls = []

            def runner(argv):
                calls.append(list(argv))
                if argv[1] == "run":
                    return CmdResult(9, "", "boom\n")
                return CmdResult(0, "", "")

            stderr = StringIO()
            with redirect_stderr(stderr):
                code = execute_plan(plan, runner)
            self.assertEqual(code, 9)
            self.assertEqual(calls[-1], ["docker", "rm", "-f", "ewok-render-abcdef12"])
            self.assertIn("boom", stderr.getvalue())

    def test_runtime_exception_still_cleans_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = _docker_plan(self.roles, Path(tmp))
            calls = []

            def runner(argv):
                calls.append(list(argv))
                if argv[1] == "run":
                    raise OSError("runtime missing")
                return CmdResult(0, "", "")

            stderr = StringIO()
            with redirect_stderr(stderr):
                code = execute_plan(plan, runner)
            self.assertEqual(code, 1)
            self.assertEqual(calls[-1][1], "rm")
            self.assertIn("runtime missing", stderr.getvalue())

    def test_cleanup_failure_after_success_exits_4(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = _docker_plan(self.roles, Path(tmp))

            def runner(argv):
                if argv[1] == "run":
                    return CmdResult(0, "ok\n", "")
                return CmdResult(1, "", "permission denied\n")

            stderr = StringIO()
            with redirect_stderr(stderr):
                code = execute_plan(plan, runner)
            self.assertEqual(code, 4)
            self.assertIn("permission denied", stderr.getvalue())

    def test_podman_netns_failure_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_plan(
                self.roles["kalwi-scout"],
                runtime="podman-netns",
                image="kalwi-ewok:local",
                run_id=RUN_ID,
                log_dir=Path(tmp),
            )

            def add_fails(argv):
                if list(argv[:3]) == ["ip", "netns", "add"]:
                    return CmdResult(1, "", "cannot add\n")
                raise AssertionError(argv)

            stderr = StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(execute_plan(plan, add_fails), 1)
            self.assertIn("cannot add", stderr.getvalue())

            calls = []

            def run_fails(argv):
                calls.append(list(argv))
                if list(argv[:3]) == ["ip", "netns", "add"]:
                    return CmdResult(0, "", "")
                if argv[:2] == ["ip", "netns"] and argv[2] == "exec":
                    return CmdResult(0, "", "")
                if argv[1] == "run":
                    return CmdResult(3, "nope\n", "")
                return CmdResult(0, "", "")

            stderr = StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(execute_plan(plan, run_fails), 3)
            self.assertEqual(calls[-2], ["podman", "rm", "-f", "ewok-scout-abcdef12"])
            self.assertEqual(calls[-1], ["ip", "netns", "delete", "ewok-abcdef12"])
            self.assertIn("nope\n", (Path(tmp) / f"{RUN_ID}-kalwi-scout.log").read_text(encoding="utf-8"))

    def test_deploy_flag_is_rejected(self):
        stderr = StringIO()
        with redirect_stderr(stderr):
            code = main(["--role", "kalwi-render", "--push"], runner=_explode)
        self.assertEqual(code, 2)
        self.assertIn("unrecognized arguments", stderr.getvalue())

    def test_module_dry_run(self):
        proc = subprocess.run(
            [sys.executable, "-m", "kalwi_ewok", "--role", "kalwi-ledger", "--run-id", RUN_ID],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("dry-run", proc.stdout)
        self.assertIn("kalwi-ledger", proc.stdout)
        self.assertIn("--execute", proc.stdout)


def _docker_plan(roles, log_dir: Path):
    return build_plan(
        roles["kalwi-render"],
        runtime="docker",
        image="kalwi-ewok:local",
        run_id=RUN_ID,
        log_dir=log_dir,
    )


if __name__ == "__main__":
    unittest.main()
