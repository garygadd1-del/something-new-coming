import re
import shutil
import subprocess
import unittest
from pathlib import Path

from kalwi_ewok.config import load_roles
from kalwi_ewok.yaml_subset import parse_simple_yaml

ROOT = Path(__file__).resolve().parents[1]

# Pieces are concatenated so this file does not contain a contiguous credential prefix.
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bAKIA" + r"[0-9A-Z]{16}\b"),
    re.compile(r"sk-" + "ant-"),
    re.compile(r"sk-" + "proj-"),
    re.compile(r"ghp_" + r"[A-Za-z0-9]{20,}"),
    re.compile("github_" + "pat_"),
    re.compile(r"xox[baprs]-" + r"[A-Za-z0-9-]"),
    re.compile(r"AIza" + r"[0-9A-Za-z\-_]{20,}"),
)
_FORBIDDEN_COMPOSE_KEYS = frozenset(
    {
        "volumes",
        "ports",
        "devices",
        "gpus",
        "privileged",
        "env_file",
        "secrets",
        "cap_add",
        "sysctls",
        "extra_hosts",
        "links",
        "pid",
        "ipc",
    }
)


class ImageContractTests(unittest.TestCase):
    def test_dockerfile_is_non_root_and_has_no_toolchain(self):
        text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# syntax=docker/dockerfile:1\n"))
        self.assertIn("FROM alpine:3.20\n", text)
        self.assertNotIn("latest", text.lower())
        self.assertEqual(text.count("USER "), 1)
        self.assertIn("USER 1001:1001\n", text)
        self.assertNotIn("EXPOSE", text)
        self.assertNotIn("apk", text.lower())
        self.assertNotIn("ARG ", text)
        self.assertNotIn("nvidia", text.lower())
        self.assertNotIn("docker.sock", text)
        self.assertIn("COPY --link --chown=1001:1001 skills/", text)
        self.assertNotIn("kalwi_ewok", text)

    def test_dockerignore_keeps_secrets_and_launcher_out(self):
        text = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        for needle in ("**/.npmrc", "**/.env", "**/*.pem", "**/*.key", "kalwi_ewok", "runs", "tests"):
            self.assertIn(needle, text)
        self.assertNotIn("*.md", text.splitlines())

    def test_compose_matches_roles_and_has_no_host_surface(self):
        text = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        self.assertEqual(text.count('restart: "no"'), 3)
        self.assertNotIn("docker.sock", text)
        data = parse_simple_yaml(text)
        self.assertEqual(data["name"], "kalwi-ewok")
        keys = set(_walk_keys(data))
        self.assertTrue(keys.isdisjoint(_FORBIDDEN_COMPOSE_KEYS), keys & _FORBIDDEN_COMPOSE_KEYS)
        roles = load_roles(ROOT / "roles")
        services = data["services"]
        self.assertEqual(set(services), set(roles))
        for name, role in roles.items():
            service = services[name]
            self.assertEqual(service["network_mode"], "none")
            self.assertEqual(service["restart"], "no")
            self.assertIs(service["read_only"], True)
            self.assertEqual(service["user"], "1001:1001")
            self.assertEqual(service["cap_drop"], ["ALL"])
            self.assertEqual(service["security_opt"], ["no-new-privileges:true"])
            self.assertEqual(service["image"], "kalwi-ewok:local")
            self.assertEqual(service["cpus"], role.cpus)
            self.assertEqual(service["pids_limit"], role.pids_limit)
            self.assertEqual(int(service["mem_limit"].removesuffix("m")), role.memory_mb)
            self.assertEqual(service["environment"], dict(role.env))
            self.assertEqual(service["profiles"], [name.removeprefix("kalwi-")])
            self.assertNotIn("volumes", service)

    def test_tree_has_no_baked_credentials(self):
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if any(part in {"__pycache__", "runs", ".venv"} for part in path.parts):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern in _SECRET_PATTERNS:
                self.assertIsNone(pattern.search(text), f"{pattern.pattern} in {path}")

    @unittest.skipUnless(shutil.which("docker"), "docker not installed")
    def test_compose_config_when_docker_is_present(self):
        proc = subprocess.run(
            ["docker", "compose", "config", "--quiet"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)


def _walk_keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _walk_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_keys(item)


if __name__ == "__main__":
    unittest.main()
