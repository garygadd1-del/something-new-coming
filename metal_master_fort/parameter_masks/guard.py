"""Hand a masked brain to the Rust wrapper.

The wrapper is the immune step. If the JSON is not a masked brain, or the
binary is missing, this raises Reroute and the caller stops the task.
A missing binary is a failure, not a skip.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


class Reroute(Exception):
    """The mask was refused. Do not continue the task."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def commit_mask(masked: dict, dest: Path, binary: Path | None) -> None:
    """Write ``masked`` and refuse it unless mask_guard says OK."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(masked, indent=2) + "\n", encoding="utf-8")
    if binary is None or not Path(binary).is_file():
        raise Reroute("mask_guard binary missing")
    proc = subprocess.run(
        [str(binary), str(dest)],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.startswith("OK"):
        reason = (proc.stderr or proc.stdout or "mask_guard rerouted").strip()
        raise Reroute(f"mask_guard: {reason}")
