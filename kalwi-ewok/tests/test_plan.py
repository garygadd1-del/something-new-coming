import os
import unittest
from pathlib import Path

from kalwi_ewok.config import load_roles
from kalwi_ewok.errors import PlanError
from kalwi_ewok.plan import assert_container_argv, build_plan, format_plan

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "abcdef12"


class PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roles = load_roles(ROOT / "roles")

    def test_docker_render_argv_is_closed(self):
        plan = build_plan(
            self.roles["kalwi-render"],
            runtime="docker",
            image="kalwi-ewok:local",
            run_id=RUN_ID,
            log_dir=ROOT / "runs",
        )
        self.assertEqual(
            list(plan.run),
            [
                "docker",
                "run",
                "--name",
                "ewok-render-abcdef12",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--pids-limit",
                "64",
                "--memory",
                "256m",
                "--cpus",
                "0.50",
                "--user",
                "1001:1001",
                "--pull=never",
                "--restart=no",
                "--tmpfs",
                "/tmp:rw,nosuid,nodev,noexec,size=16m",
                "-e",
                "KALWI_GPU=off",
                "-e",
                "KALWI_HANDOFF=No-Limit Local / Game Dev",
                "-e",
                "KALWI_MONEY_SENDS=0",
                "-e",
                "KALWI_PROD_DEPLOY=0",
                "-e",
                "KALWI_ROLE=kalwi-render",
                "-e",
                "KALWI_SECRETS=none",
                "-e",
                "KALWI_SKILLS=render-stub",
                "-e",
                "KALWI_TASK=stub",
                "kalwi-ewok:local",
            ],
        )
        self.assertEqual(plan.remove_container, ("docker", "rm", "-f", "ewok-render-abcdef12"))
        self.assertIsNone(plan.delete_netns)
        self.assertEqual(plan.setup, ())

    def test_podman_netns_is_created_and_named_in_cleanup(self):
        plan = build_plan(
            self.roles["kalwi-ledger"],
            runtime="podman-netns",
            image="kalwi-ewok:local",
            run_id=RUN_ID,
            log_dir=ROOT / "runs",
        )
        self.assertEqual(
            plan.setup,
            (
                ("ip", "netns", "add", "ewok-abcdef12"),
                ("ip", "netns", "exec", "ewok-abcdef12", "ip", "link", "set", "lo", "up"),
            ),
        )
        self.assertEqual(plan.run[plan.run.index("--network") + 1], "ns:/var/run/netns/ewok-abcdef12")
        self.assertEqual(plan.remove_container, ("podman", "rm", "-f", "ewok-ledger-abcdef12"))
        self.assertEqual(plan.delete_netns, ("ip", "netns", "delete", "ewok-abcdef12"))
        text = format_plan(plan)
        self.assertIn("dry-run", text)
        self.assertIn("not written", text)
        self.assertLess(text.index("netns add"), text.index("netns delete"))

    def test_dry_run_text_names_the_render_handoff(self):
        plan = build_plan(
            self.roles["kalwi-render"],
            runtime="docker",
            image="kalwi-ewok:local",
            run_id=RUN_ID,
            log_dir=ROOT / "runs",
        )
        text = format_plan(plan)
        self.assertIn("No-Limit Local / Game Dev", text)
        self.assertIn("gpu: off", text)
        self.assertNotIn("--gpus", text)
        self.assertNotIn("nvidia", text.lower())

    def test_host_environment_is_not_copied(self):
        os.environ["OPENAI_API_KEY"] = "host-only-marker"
        try:
            plan = build_plan(
                self.roles["kalwi-scout"],
                runtime="podman-none",
                image="kalwi-ewok:local",
                run_id=RUN_ID,
                log_dir=ROOT / "runs",
            )
        finally:
            del os.environ["OPENAI_API_KEY"]
        joined = " ".join(plan.run)
        self.assertNotIn("OPENAI_API_KEY", joined)
        self.assertNotIn("host-only-marker", joined)
        self.assertEqual(plan.run[0], "podman")
        self.assertEqual(plan.run[plan.run.index("--network") + 1], "none")

    def test_registry_image_and_latest_are_rejected(self):
        role = self.roles["kalwi-render"]
        for image in ("ghcr.io/acme/kalwi-ewok:local", "kalwi-ewok:latest", "busybox:1.36"):
            with self.assertRaises(PlanError):
                build_plan(role, runtime="docker", image=image, run_id=RUN_ID, log_dir=ROOT / "runs")

    def test_guard_rejects_privileged_gpu_and_extra_env(self):
        plan = build_plan(
            self.roles["kalwi-render"],
            runtime="docker",
            image="kalwi-ewok:local",
            run_id=RUN_ID,
            log_dir=ROOT / "runs",
        )
        privileged = list(plan.run)
        privileged.insert(2, "--privileged")
        with self.assertRaises(PlanError):
            assert_container_argv(privileged, network="none")

        host_net = list(plan.run)
        host_net[host_net.index("--network") + 1] = "host"
        with self.assertRaises(PlanError):
            assert_container_argv(host_net, network="host")

        with_secret = list(plan.run)
        image = with_secret.pop()
        with_secret.extend(["-e", "OPENAI_API_KEY=host-only-marker"])
        with_secret.append(image)
        with self.assertRaises(PlanError):
            assert_container_argv(with_secret, network="none")


if __name__ == "__main__":
    unittest.main()
