"""Kalwi Ewok launcher.

Dry-run is the default. ``--execute`` creates one seat, captures its logs,
and removes that container. The podman-netns runtime also creates one named
network namespace and deletes that same namespace on the way out.
"""

from __future__ import annotations

import argparse
import secrets
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from kalwi_ewok.config import ROLES, default_roles_dir, load_role, package_root
from kalwi_ewok.errors import EwokError
from kalwi_ewok.plan import DEFAULT_IMAGE, RUNTIMES, Plan, build_plan, format_plan

RUN_TIMEOUT_SECONDS = 30
Runner = Callable[[Sequence[str]], "CmdResult"]


@dataclass(frozen=True)
class CmdResult:
    returncode: int
    stdout: str
    stderr: str = ""


def main(argv: Sequence[str] | None = None, runner: Runner | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(None if argv is None else list(argv))
    except SystemExit as exc:
        code = exc.code
        return 1 if code is None else int(code)

    try:
        role = load_role(Path(args.roles_dir) / f"{args.role}.yaml")
        run_id = args.run_id or secrets.token_hex(4)
        plan = build_plan(
            role,
            runtime=args.runtime,
            image=args.image,
            run_id=run_id,
            log_dir=Path(args.log_dir),
        )
    except EwokError as exc:
        print(f"kalwi-ewok: {exc}", file=sys.stderr)
        return 2

    if not args.execute:
        sys.stdout.write(format_plan(plan))
        return 0

    print(
        "kalwi-ewok: execute "
        f"role={plan.role.name} runtime={plan.runtime} container={plan.container_name}",
        file=sys.stderr,
    )
    return execute_plan(plan, runner or subprocess_runner)


def execute_plan(plan: Plan, runner: Runner) -> int:
    """Run one plan. Cleanup covers the container and any netns this call created."""
    created_netns = False
    started_run = False
    exit_code = 1
    cleanup_ok = True
    try:
        setup_failed = False
        for argv in plan.setup:
            result = runner(argv)
            if list(argv[:3]) == ["ip", "netns", "add"] and result.returncode == 0:
                created_netns = True
            if result.returncode != 0:
                _emit_streams(result)
                exit_code = result.returncode or 1
                setup_failed = True
                break
        if not setup_failed:
            started_run = True
            result = runner(plan.run)
            _write_log(plan.log_path, result.stdout + result.stderr)
            if result.returncode != 0:
                _emit_streams(result)
            exit_code = result.returncode
    except Exception as exc:
        print(f"kalwi-ewok: {exc}", file=sys.stderr)
        exit_code = 1
    finally:
        cleanup_ok = _cleanup_created(plan, runner, started_run, created_netns)
    if exit_code == 0 and not cleanup_ok:
        return 4
    return exit_code


def subprocess_runner(argv: Sequence[str]) -> CmdResult:
    try:
        completed = subprocess.run(
            list(argv),
            check=False,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=RUN_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _as_text(exc.stdout)
        stderr = _as_text(exc.stderr) + f"\nkalwi-ewok: timed out after {RUN_TIMEOUT_SECONDS}s\n"
        return CmdResult(124, stdout, stderr)
    return CmdResult(completed.returncode, completed.stdout, completed.stderr)


def _cleanup_created(
    plan: Plan,
    runner: Runner,
    started_run: bool,
    created_netns: bool,
) -> bool:
    cleanup_ok = True
    if started_run:
        print(
            f"kalwi-ewok: removing container {plan.container_name}",
            file=sys.stderr,
        )
        if not _cleanup_one(runner, plan.remove_container):
            cleanup_ok = False
    if created_netns and plan.delete_netns is not None:
        print(f"kalwi-ewok: removing netns {plan.netns_name}", file=sys.stderr)
        if not _cleanup_one(runner, plan.delete_netns):
            cleanup_ok = False
    return cleanup_ok


def _cleanup_one(runner: Runner, argv: Sequence[str]) -> bool:
    try:
        result = runner(argv)
    except Exception as exc:
        print(f"kalwi-ewok: cleanup failed: {exc}", file=sys.stderr)
        return False
    if result.returncode == 0 or _already_gone(result):
        return True
    _emit_streams(result)
    return False


def _already_gone(result: CmdResult) -> bool:
    blob = f"{result.stdout}\n{result.stderr}".lower()
    phrases = (
        "no such container",
        "no such network namespace",
        "cannot find network namespace",
        "no such file",
        "not found",
    )
    return result.returncode != 0 and any(phrase in blob for phrase in phrases)


def _write_log(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(body, encoding="utf-8")


def _emit_streams(result: CmdResult) -> None:
    if result.stdout:
        print(result.stdout, file=sys.stderr, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kalwi-ewok",
        description=(
            "Spawn one short-lived Kalwi Ewok seat. "
            "Dry-run unless --execute is set."
        ),
        epilog=(
            "Hard gates: no prod deploy, no money or sends, no secrets in the image, "
            "no GPU. The default is a dry-run. --execute is required to create a "
            "container or a network namespace. Cleanup removes only the container "
            "and, for podman-netns, the netns created for that run."
        ),
    )
    parser.add_argument("--role", required=True, choices=ROLES)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Create the isolated seat for real. Omit this flag for a dry-run (the default).",
    )
    parser.add_argument("--runtime", choices=RUNTIMES, default="docker")
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--log-dir",
        default=str(package_root() / "runs"),
        help="Host directory for captured logs. Written only with --execute.",
    )
    parser.add_argument(
        "--roles-dir",
        default=str(default_roles_dir()),
        help=argparse.SUPPRESS,
    )
    return parser
