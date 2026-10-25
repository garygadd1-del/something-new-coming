"""Plan globe tile passes (trace / shade) without starting Godot.

Tile ids are A01..Z26. One planned process covers the missing tiles of one
row and one pass. This matches scripts/globe_runner.ps1.
"""

from __future__ import annotations

import re
import string
from pathlib import Path

from orb_chunk.errors import QueueError

ROWS = tuple(string.ascii_uppercase)
TILES_PER_ROW = 26
PASSES = ("trace", "shade")
GLOBE_SCENE = "res://refrender/globe_shot.tscn"
DEFAULT_ROOT = r"C:\AGIOS\Sandbox\Render_Chunks_20261022"
DEFAULT_RESOLUTION = "1024x1024"
GODOT_TIMEOUT_MS = 900000
TILE_RE = re.compile(r"^[A-Z][0-9]{2}$")
RES_RE = re.compile(r"^[1-9][0-9]*x[1-9][0-9]*$")


def tile_ids(row: str) -> list[str]:
    if row not in ROWS:
        raise QueueError([f"unknown globe row: {row}"])
    return [f"{row}{number:02d}" for number in range(1, TILES_PER_ROW + 1)]


def all_tile_ids() -> list[str]:
    return [tile_id for row in ROWS for tile_id in tile_ids(row)]


def parse_passes(text: str) -> list[str]:
    parts = [part.strip() for part in text.split(",") if part.strip()]
    unknown = [part for part in parts if part not in PASSES]
    if not parts or unknown:
        raise QueueError([f"passes must be trace and/or shade, got {text!r}"])
    if len(parts) != len(set(parts)):
        raise QueueError(["duplicate pass in --passes"])
    return parts


def windows_join(root: str, *parts: str) -> str:
    cleaned = root.rstrip("\\/")
    return "\\".join((cleaned, *parts))


def argument_list(
    *,
    godot: str,
    project: str,
    resolution: str,
    scene: str,
    pass_name: str,
    tiles: list[str],
    outdir: str,
) -> list[str]:
    """Argv used by globe_runner.ps1. Printed by dry-run, started only with -Execute."""
    return [
        godot,
        "--path",
        project,
        "--windowed",
        "--resolution",
        resolution,
        scene,
        "--",
        "--worker",
        "--no-auto",
        "--no-link",
        f"--pass={pass_name}",
        f"--tiles={','.join(tiles)}",
        f"--outdir={outdir.replace(chr(92), '/')}",
    ]


def find_existing(out_root: Path, passes: list[str]) -> set[tuple[str, str]]:
    """Read tile PNGs already on disk. Does not create files."""
    found: set[tuple[str, str]] = set()
    if not out_root.exists():
        return found
    if not out_root.is_dir():
        raise QueueError([f"out-root is not a directory: {out_root}"])
    for pass_name in passes:
        folder = out_root / pass_name
        if not folder.exists():
            continue
        if not folder.is_dir():
            raise QueueError([f"pass folder is not a directory: {folder}"])
        for png in sorted(folder.glob("tile_*.png")):
            tile = png.name[len("tile_") : -len(".png")]
            if TILE_RE.fullmatch(tile):
                found.add((pass_name, tile))
    return found


def plan(
    *,
    passes: list[str],
    root: str = DEFAULT_ROOT,
    godot: str = "godot",
    resolution: str = DEFAULT_RESOLUTION,
    scene: str = GLOBE_SCENE,
    existing: set[tuple[str, str]] | None = None,
) -> list[dict]:
    if not root:
        raise QueueError(["globe root is empty"])
    if RES_RE.fullmatch(resolution) is None:
        raise QueueError([f"resolution must look like 1024x1024, got {resolution!r}"])
    present = existing or set()
    project = windows_join(root, "src", "ara_body")
    jobs: list[dict] = []
    for row in ROWS:
        ids = tile_ids(row)
        for pass_name in passes:
            todo = [tile_id for tile_id in ids if (pass_name, tile_id) not in present]
            outdir = windows_join(root, "out", "globe", pass_name)
            skipped = not todo
            jobs.append(
                {
                    "row": row,
                    "pass": pass_name,
                    "tiles": todo,
                    "skipped": skipped,
                    "outdir": outdir.replace("\\", "/"),
                    "argv": []
                    if skipped
                    else argument_list(
                        godot=godot,
                        project=project,
                        resolution=resolution,
                        scene=scene,
                        pass_name=pass_name,
                        tiles=todo,
                        outdir=outdir,
                    ),
                }
            )
    return jobs
