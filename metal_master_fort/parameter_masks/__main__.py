"""Show one masked brain. Pass --guard with a mask_guard binary to run the wrapper."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from parameter_masks.guard import Reroute, commit_mask
from parameter_masks.loader import MaskError, apply_mask, load_brain, load_mask


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="parameter_masks")
    parser.add_argument("--role", default="mayor")
    parser.add_argument("--job", default=None)
    parser.add_argument("--guard", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        masked = apply_mask(load_brain(), load_mask(args.role), job=args.job)
    except MaskError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.guard is not None:
        fd, name = tempfile.mkstemp(prefix="mmf-mask-", suffix=".json")
        os.close(fd)
        dest = Path(name)
        try:
            commit_mask(masked, dest, args.guard)
        except Reroute as exc:
            print(f"REROUTE {exc.reason}", file=sys.stderr)
            return 2
        finally:
            dest.unlink(missing_ok=True)
    print(
        json.dumps(
            {
                "role": masked["role"],
                "job": masked["job"],
                "kept": list(masked["parameters"]),
                "stripped": masked["stripped"],
                "emergent": masked["emergent"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
