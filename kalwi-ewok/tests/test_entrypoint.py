import os
import stat
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "agent" / "entrypoint.sh"
HOOKS = ROOT / "skills" / "hooks"


class EntrypointTests(unittest.TestCase):
    def test_shell_syntax_and_executable_bit(self):
        proc = subprocess.run(["/bin/sh", "-n", str(ENTRY)], capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        mode = ENTRY.stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR)

    def test_stub_roles_exit_clean_when_not_root(self):
        for role in ("kalwi-render", "kalwi-ledger", "kalwi-scout"):
            proc = _run({"KALWI_ROLE": role})
            if os.geteuid() == 0:
                self.assertEqual(proc.returncode, 2)
                self.assertIn("root", proc.stderr)
                continue
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn(f"spawn role={role}", proc.stdout)
            self.assertIn("gpu=off", proc.stdout)
            self.assertIn(f"die-clean role={role}", proc.stdout)
            self.assertIn(str(HOOKS / role), proc.stdout)

    def test_gates_refuse_before_hooks(self):
        cases = [
            ({"KALWI_GPU": "on"}, "KALWI_GPU"),
            ({"KALWI_PROD_DEPLOY": "1"}, "hard gate"),
            ({"KALWI_MONEY_SENDS": "1"}, "hard gate"),
            ({"KALWI_SECRETS": "present"}, "hard gate"),
            ({"KALWI_TASK": "render-frame"}, "stub task"),
            ({"KALWI_ROLE": "kalwi-prod"}, "unknown role"),
        ]
        for overrides, needle in cases:
            proc = _run(overrides)
            self.assertEqual(proc.returncode, 2, overrides)
            self.assertIn(needle, proc.stderr)
            self.assertNotIn("die-clean", proc.stdout)

    def test_arguments_are_refused(self):
        proc = _run({}, args=["nope"])
        self.assertEqual(proc.returncode, 2)
        self.assertIn("arguments", proc.stderr)

    def test_hooks_are_empty_stubs(self):
        banned = ("curl", "wget", "nvidia-smi", "python", "nc ")
        for role in ("kalwi-render", "kalwi-ledger", "kalwi-scout"):
            hooks = list((HOOKS / role).glob("*.sh"))
            self.assertEqual(len(hooks), 1)
            text = hooks[0].read_text(encoding="utf-8")
            self.assertIn("exit 0", text)
            for word in banned:
                self.assertNotIn(word, text)
            proc = subprocess.run(["/bin/sh", str(hooks[0])], capture_output=True, text=True, check=False)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout, "")
        render = (HOOKS / "kalwi-render" / "00-stub.sh").read_text(encoding="utf-8")
        self.assertIn("No-Limit Local / Game Dev", render)


def _run(overrides, args=None):
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "KALWI_ROLE": "kalwi-render",
        "KALWI_TASK": "stub",
        "KALWI_GPU": "off",
        "KALWI_PROD_DEPLOY": "0",
        "KALWI_MONEY_SENDS": "0",
        "KALWI_SECRETS": "none",
    }
    env.update(overrides)
    return subprocess.run(
        ["/bin/sh", str(ENTRY), *(args or [])],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


if __name__ == "__main__":
    unittest.main()
