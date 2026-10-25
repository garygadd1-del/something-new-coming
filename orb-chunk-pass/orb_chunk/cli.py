"""Command line for the orb-and-chunk queue.

Subcommands validate, list, filter, and dry-run. There is no execute command.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from orb_chunk.errors import QueueError
from orb_chunk.globe import (
    DEFAULT_RESOLUTION,
    DEFAULT_ROOT,
    GODOT_TIMEOUT_MS,
    find_existing,
    parse_passes,
    plan as plan_globe,
)
from orb_chunk.queue import (
    camera_counts,
    dump_queue,
    godot_argv,
    load_queue,
    plan_basename,
    quote_arg,
    select_jobs,
)


def _add_queue_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--queue",
        type=Path,
        default=None,
        help="Legacy queue_v2.json array or a normalized queue document.",
    )


def _add_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--camera",
        action="append",
        choices=["wide", "close", "mid"],
        default=None,
        help="Camera pass. Repeat to include more than one. This is not Godot --stage.",
    )
    parser.add_argument("--site", action="append", default=None, help="Site id such as s07. Repeatable.")
    parser.add_argument("--t0", action="append", type=int, default=None, help="Start offset. Repeatable.")
    parser.add_argument("--id", action="append", dest="ids", default=None, help="Exact chunk id. Repeatable.")
    parser.add_argument(
        "--order",
        choices=["file", "camera"],
        default="file",
        help="file keeps the capture order. camera groups wide, then close, then mid.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orb-chunk",
        description=(
            "Plan the AGIOS landfall chunk queue and globe tile passes. "
            "Prints Godot arguments. Does not start Godot."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate the queue and print counts.")
    _add_queue_arg(validate)

    listing = sub.add_parser("list", help="List jobs. Filters are optional.")
    _add_queue_arg(listing)
    _add_filters(listing)
    listing.add_argument("--json", action="store_true", help="Print normalized jobs as JSON.")

    dry = sub.add_parser("dry-run", help="Print planned Godot argv for chunk jobs.")
    _add_queue_arg(dry)
    _add_filters(dry)
    dry.add_argument(
        "--godot",
        default="godot",
        help="Binary name placed in argv. It is printed and never executed.",
    )
    dry.add_argument("--format", choices=["text", "json"], default="text")

    globe = sub.add_parser("globe-dry-run", help="Print planned Godot argv for globe tiles.")
    globe.add_argument("--passes", default="trace,shade", help="Comma-separated trace and/or shade.")
    globe.add_argument("--node", default="selfaware", help="Seat name recorded in the plan (selfaware, throne, aidev).")
    globe.add_argument("--resolution", default=DEFAULT_RESOLUTION)
    globe.add_argument("--root", default=DEFAULT_ROOT, help="Sandbox root printed into argv. Not required to exist.")
    globe.add_argument("--godot", default="godot", help="Binary name placed in argv. Never executed.")
    globe.add_argument("--format", choices=["text", "json"], default="text")
    globe.add_argument(
        "--out-root",
        type=Path,
        default=None,
        help="Existing out/globe directory. Tile PNGs found here are omitted. Read-only.",
    )

    preflight = sub.add_parser("preflight", help="Print the path checklist for the render seat.")
    _add_queue_arg(preflight)

    normalize = sub.add_parser("normalize", help="Write the normalized queue JSON to stdout or --out.")
    _add_queue_arg(normalize)
    normalize.add_argument("--out", type=Path, default=None, help="Destination file. Omit to write stdout.")

    return parser


def _queue_path(args: argparse.Namespace) -> Path | None:
    return args.queue


def _selected(doc: dict, args: argparse.Namespace) -> list[dict]:
    return select_jobs(
        doc,
        cameras=args.camera,
        sites=args.site,
        t0s=args.t0,
        ids=args.ids,
        order=args.order,
    )


def _print_json(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def cmd_validate(doc: dict) -> int:
    counts = camera_counts(doc["jobs"])
    sys.stdout.write(
        "ok\n"
        "Godot is not started.\n"
        f"jobs: {len(doc['jobs'])}\n"
        f"wide: {counts['wide']}\n"
        f"close: {counts['close']}\n"
        f"mid: {counts['mid']}\n"
        f"owner: {doc['owner']}\n"
        "execute: false\n"
    )
    return 0


def cmd_list(doc: dict, args: argparse.Namespace) -> int:
    jobs = _selected(doc, args)
    if args.json:
        _print_json(
            {
                "godot_invoked": False,
                "job_count": len(jobs),
                "jobs": jobs,
            }
        )
        return 0
    lines = [
        "Godot is not started.",
        f"jobs: {len(jobs)}",
        f"{'id':<20} {'camera':<6} {'site':<5} {'t0':>4} {'res':<9} {'zoom':>4} {'follow':>6} plan",
    ]
    for job in jobs:
        lines.append(
            f"{job['id']:<20} {job['camera']:<6} {job['site']:<5} {job['t0']:>4} "
            f"{job['res']:<9} {job['zoom']:>4.1f} {job['follow']:>6} {plan_basename(job['plan'])}"
        )
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def cmd_dry_run(doc: dict, args: argparse.Namespace) -> int:
    jobs = _selected(doc, args)
    if args.format == "json":
        _print_json(
            {
                "dry_run": True,
                "godot_invoked": False,
                "kind": "landfall-chunk",
                "order": args.order,
                "owner": doc["owner"],
                "job_count": len(jobs),
                "jobs": [
                    {
                        "id": job["id"],
                        "camera": job["camera"],
                        "site": job["site"],
                        "t0": job["t0"],
                        "res": job["res"],
                        "zoom": job["zoom"],
                        "follow": job["follow"],
                        "argv": godot_argv(job, args.godot),
                    }
                    for job in jobs
                ],
            }
        )
        return 0
    lines = [
        "dry-run: true",
        "Godot is not started.",
        "godot_invoked: false",
        "kind: landfall-chunk",
        f"order: {args.order}",
        f"jobs: {len(jobs)}",
        f"owner: {doc['owner']}",
        "---",
    ]
    for job in jobs:
        argv = " ".join(quote_arg(arg) for arg in godot_argv(job, args.godot))
        lines.extend(
            [
                f"id: {job['id']}",
                f"camera: {job['camera']}",
                f"site: {job['site']}",
                f"t0: {job['t0']}",
                f"resolution: {job['res']}",
                f"zoom: {job['zoom']:.1f}",
                f"follow: {job['follow']}",
                f"argv: {argv}",
                "---",
            ]
        )
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def cmd_globe(args: argparse.Namespace) -> int:
    passes = parse_passes(args.passes)
    existing = find_existing(args.out_root, passes) if args.out_root else set()
    jobs = plan_globe(
        passes=passes,
        root=args.root,
        godot=args.godot,
        resolution=args.resolution,
        existing=existing,
    )
    starts = [job for job in jobs if not job["skipped"]]
    if args.format == "json":
        _print_json(
            {
                "dry_run": True,
                "godot_invoked": False,
                "kind": "globe",
                "node": args.node,
                "passes": passes,
                "process_starts": len(starts),
                "timeout_ms": GODOT_TIMEOUT_MS,
                "jobs": jobs,
            }
        )
        return 0
    lines = [
        "dry-run: true",
        "Godot is not started.",
        "godot_invoked: false",
        "kind: globe",
        f"node: {args.node}",
        f"passes: {','.join(passes)}",
        f"process_starts: {len(starts)}",
        f"timeout_ms: {GODOT_TIMEOUT_MS}",
        "cap: not applied in dry-run (the Windows runner stops at gpu_policy max_hours, fallback 3)",
        "---",
    ]
    for job in jobs:
        if job["skipped"]:
            lines.append(f"SKIP row={job['row']} pass={job['pass']} reason=pngs-present")
            continue
        argv = " ".join(quote_arg(arg) for arg in job["argv"])
        lines.append(f"row={job['row']} pass={job['pass']} tiles={len(job['tiles'])}")
        lines.append(f"argv: {argv}")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def cmd_preflight(doc: dict) -> int:
    plans = []
    seen = set()
    for job in doc["jobs"]:
        if job["plan"] not in seen:
            seen.add(job["plan"])
            plans.append(job["plan"])
    lines = [
        "Godot is not started.",
        f"owner: {doc['owner']}",
        "execute: false",
        f"jobs: {len(doc['jobs'])}",
        f"project: {doc['project']}",
        "scene: res://scenes/showcase.tscn",
        "render_stage: 5",
        "seq: 240",
        "fps: 12",
        "resolution: 1280x720",
        "cameras: wide zoom=0.6 follow=0; close zoom=1.6 follow=1; mid zoom=1.0 follow=1",
        "plans:",
    ]
    lines.extend(f"- {plan}" for plan in plans)
    lines.append(f"outputs: {len(doc['jobs'])}")
    lines.append(f"sample-outdir: {doc['jobs'][0]['outdir']}")
    lines.append("check-on-seat: No-Limit Local confirms these paths before any -Execute.")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def cmd_normalize(doc: dict, args: argparse.Namespace) -> int:
    text = dump_queue(doc)
    if args.out is None:
        sys.stdout.write(text)
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    sys.stdout.write(f"wrote {args.out}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "globe-dry-run":
            return cmd_globe(args)
        doc = load_queue(_queue_path(args))
        if args.command == "validate":
            return cmd_validate(doc)
        if args.command == "list":
            return cmd_list(doc, args)
        if args.command == "dry-run":
            return cmd_dry_run(doc, args)
        if args.command == "preflight":
            return cmd_preflight(doc)
        if args.command == "normalize":
            return cmd_normalize(doc, args)
    except QueueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
