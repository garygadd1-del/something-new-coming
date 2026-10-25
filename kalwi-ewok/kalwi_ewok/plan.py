"""Build the argv for one Kalwi seat.

The plan is pure data. Dry-run prints it. ``--execute`` is the only path
that hands it to a container runtime.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from kalwi_ewok.config import ALLOWED_ENV_KEYS, RoleConfig
from kalwi_ewok.errors import PlanError

DEFAULT_IMAGE = "kalwi-ewok:local"
RUNTIMES = ("docker", "podman-none", "podman-netns")
RUN_ID_RE = re.compile(r"^[a-f0-9]{8}$")
IMAGE_RE = re.compile(r"^kalwi-ewok:[A-Za-z0-9][A-Za-z0-9_.-]{0,40}$")

_BANNED_ARGS = frozenset(
    {
        "--gpus",
        "--gpu",
        "--privileged",
        "--volume",
        "-v",
        "--mount",
        "--device",
        "--pid=host",
        "--ipc=host",
        "--uts=host",
        "--network=host",
        "--net=host",
        "--network=bridge",
        "--net=bridge",
        "--publish",
        "-p",
        "--publish-all",
        "-P",
        "--env-file",
        "--volumes-from",
        "--group-add",
        "--cap-add",
        "--device-cgroup-rule",
        "--cgroupns=host",
    }
)
_RUNTIME_BIN = {
    "docker": "docker",
    "podman-none": "podman",
    "podman-netns": "podman",
}


@dataclass(frozen=True)
class Plan:
    role: RoleConfig
    run_id: str
    runtime: str
    image: str
    container_name: str
    netns_name: str | None
    log_path: Path
    setup: tuple[tuple[str, ...], ...]
    run: tuple[str, ...]
    remove_container: tuple[str, ...]
    delete_netns: tuple[str, ...] | None
    notes: tuple[str, ...]


def build_plan(
    role: RoleConfig,
    *,
    runtime: str,
    image: str,
    run_id: str,
    log_dir: Path,
) -> Plan:
    if runtime not in RUNTIMES:
        raise PlanError(f"unknown runtime {runtime}")
    if not RUN_ID_RE.fullmatch(run_id):
        raise PlanError("run id must be 8 lowercase hex characters")
    if not IMAGE_RE.fullmatch(image):
        raise PlanError("image must be a local kalwi-ewok tag")
    if "/" in image or image.endswith(":latest"):
        raise PlanError("image must be a local kalwi-ewok tag")
    log_dir = Path(log_dir)
    resolved_log = log_dir.resolve()
    if resolved_log == Path(resolved_log.anchor):
        raise PlanError("refusing to use a filesystem root as the log directory")

    container = f"ewok-{role.name.removeprefix('kalwi-')}-{run_id}"
    named_netns = runtime == "podman-netns"
    netns = f"ewok-{run_id}" if named_netns else None
    network = f"ns:/var/run/netns/{netns}" if netns else "none"
    binary = _RUNTIME_BIN[runtime]

    run = _container_argv(
        binary=binary,
        container=container,
        network=network,
        role=role,
        image=image,
    )
    assert_container_argv(run, network=network)

    setup: tuple[tuple[str, ...], ...] = ()
    delete_netns = None
    if netns is not None:
        setup = (
            ("ip", "netns", "add", netns),
            ("ip", "netns", "exec", netns, "ip", "link", "set", "lo", "up"),
        )
        delete_netns = ("ip", "netns", "delete", netns)
        _assert_exact(
            setup[0],
            ("ip", "netns", "add", netns),
            "unexpected netns add",
        )
        _assert_exact(
            delete_netns,
            ("ip", "netns", "delete", netns),
            "cleanup must delete only this netns",
        )

    remove_container = (binary, "rm", "-f", container)
    _assert_exact(
        remove_container,
        (binary, "rm", "-f", container),
        "cleanup must remove only this container",
    )

    return Plan(
        role=role,
        run_id=run_id,
        runtime=runtime,
        image=image,
        container_name=container,
        netns_name=netns,
        log_path=resolved_log / f"{run_id}-{role.name}.log",
        setup=setup,
        run=run,
        remove_container=remove_container,
        delete_netns=delete_netns,
        notes=tuple(_notes(role, runtime)),
    )


def format_plan(plan: Plan) -> str:
    role = plan.role
    lines = [
        "kalwi-ewok: dry-run (no container, no netns, no log file)",
        "next: pass --execute to create this seat",
        f"role: {role.name}",
        f"summary: {role.summary}",
        f"runtime: {plan.runtime}",
        f"image: {plan.image}",
        f"container: {plan.container_name}",
        f"skills: {', '.join(role.skills)}",
        f"cpus: {role.cpus:.2f}",
        f"memory_mb: {role.memory_mb}",
        f"pids_limit: {role.pids_limit}",
        "gpu: off",
        f"gpu_handoff: {role.gpu_handoff}",
        "volumes: (none)",
        "secrets: not passed",
        "prod_deploy: blocked",
        "money_sends: blocked",
        f"log: {plan.log_path} (not written)",
    ]
    if plan.netns_name is None:
        lines.append(
            "network: none (ephemeral Linux netns, loopback only, "
            "removed with the container)"
        )
    else:
        lines.append(
            f"network: named netns {plan.netns_name} "
            "(loopback only, deleted on exit)"
        )
    lines.extend(plan.notes)
    lines.append("would set up:")
    if plan.setup:
        lines.extend("  " + _join(cmd) for cmd in plan.setup)
    else:
        lines.append("  (none)")
    lines.append("would run:")
    lines.append("  " + _join(plan.run))
    lines.append("would always remove:")
    lines.append("  " + _join(plan.remove_container))
    if plan.delete_netns is not None:
        lines.append("  " + _join(plan.delete_netns))
    else:
        lines.append("  (container removal drops the ephemeral netns)")
    return "\n".join(lines) + "\n"


def assert_container_argv(argv: Sequence[str], *, network: str) -> None:
    """Fail closed if a run command could seize a GPU, a volume, or a secret."""
    if len(argv) < 4 or argv[0] not in {"docker", "podman"} or argv[1] != "run":
        raise PlanError("refusing unexpected runtime command")
    if any("\x00" in arg or "\n" in arg or "\r" in arg for arg in argv):
        raise PlanError("refusing argv with control characters")
    for arg in argv:
        if arg in _BANNED_ARGS or arg.lower() in _BANNED_ARGS:
            raise PlanError(f"refusing forbidden argument {arg}")
        if "docker.sock" in arg or "/var/run/docker" in arg:
            raise PlanError("refusing docker socket access")
        if ".." in arg.split("/"):
            raise PlanError("refusing parent-directory path")
    network_value = _flag_value(argv, "--network")
    if network_value != network or network_value in {"host", "bridge", "default"}:
        raise PlanError("unexpected network mode")
    if network_value.startswith("ns:"):
        netns_path = network_value.removeprefix("ns:")
        if not re.fullmatch(r"/var/run/netns/ewok-[a-f0-9]{8}", netns_path):
            raise PlanError("refusing unexpected netns path")
    required = (
        "--rm",
        "--read-only",
        "--pull=never",
        "--restart=no",
        "--cap-drop",
        "--user",
        "--memory",
        "--cpus",
        "--pids-limit",
        "--security-opt",
        "--tmpfs",
    )
    for flag in required:
        if flag not in argv:
            raise PlanError(f"missing {flag}")
    if _flag_value(argv, "--cap-drop") != "ALL":
        raise PlanError("cap_drop must be ALL")
    if _flag_value(argv, "--user") != "1001:1001":
        raise PlanError("container user must be 1001:1001")
    if _flag_value(argv, "--security-opt") != "no-new-privileges:true":
        raise PlanError("no-new-privileges is required")
    if not IMAGE_RE.fullmatch(argv[-1]):
        raise PlanError("image must be a local kalwi-ewok tag")
    _assert_env_flags(argv)


def _container_argv(
    *,
    binary: str,
    container: str,
    network: str,
    role: RoleConfig,
    image: str,
) -> tuple[str, ...]:
    argv = [
        binary,
        "run",
        "--name",
        container,
        "--rm",
        "--network",
        network,
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        str(role.pids_limit),
        "--memory",
        f"{role.memory_mb}m",
        "--cpus",
        f"{role.cpus:.2f}",
        "--user",
        "1001:1001",
        "--pull=never",
        "--restart=no",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,noexec,size=16m",
    ]
    for key in sorted(role.env):
        argv.extend(["-e", f"{key}={role.env[key]}"])
    argv.append(image)
    return tuple(argv)


def _flag_value(argv: Sequence[str], flag: str) -> str:
    try:
        index = argv.index(flag)
    except ValueError as exc:
        raise PlanError(f"missing {flag}") from exc
    if index + 1 >= len(argv):
        raise PlanError(f"missing value for {flag}")
    return argv[index + 1]


def _assert_env_flags(argv: Sequence[str]) -> None:
    seen = []
    index = 0
    while index < len(argv):
        if argv[index] == "-e":
            if index + 1 >= len(argv):
                raise PlanError("dangling -e")
            pair = argv[index + 1]
            key, sep, value = pair.partition("=")
            if sep == "" or key not in ALLOWED_ENV_KEYS:
                raise PlanError(f"refusing env {key or pair}")
            if value == "" or "\n" in value:
                raise PlanError(f"refusing env value for {key}")
            seen.append(key)
            index += 2
            continue
        index += 1
    if set(seen) != set(ALLOWED_ENV_KEYS):
        raise PlanError("container env must be exactly the role allowlist")


def _assert_exact(actual, expected, message: str) -> None:
    if tuple(actual) != tuple(expected):
        raise PlanError(message)


def _notes(role: RoleConfig, runtime: str) -> list[str]:
    notes = [
        "Lifecycle is spawn, one stub task, then exit. Restart is off.",
        "The seat root filesystem is read-only and there are no volumes.",
    ]
    if runtime == "docker":
        notes.append(
            "Docker --network=none is the rootless isolation path: "
            "a private netns with loopback only."
        )
    elif runtime == "podman-none":
        notes.append(
            "Rootless Podman --network=none is the same private netns, "
            "without a named ip-netns."
        )
    else:
        notes.append(
            "podman-netns creates one named netns for this run and deletes "
            "that netns on exit. It needs CAP_SYS_ADMIN."
        )
    if role.name == "kalwi-render":
        notes.append(
            "Render does not seize a GPU. Godot and GPU work hand off to "
            "No-Limit Local / Game Dev."
        )
    elif role.name == "kalwi-ledger":
        notes.append("Ledger records nothing and sends no money.")
    else:
        notes.append("Scout has no external interface and does not scan.")
    return notes


def _join(argv: Sequence[str]) -> str:
    return shlex.join(argv)
