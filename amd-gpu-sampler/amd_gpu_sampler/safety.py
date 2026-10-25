"""Guards shared by the sampler. These checks refuse unsafe inputs; they do not delete anything."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

SECRET_NAME = re.compile(
    r"(^|[^a-z0-9])(key|secret|token|credential|password)([^a-z0-9]|$)|(\.pem|\.pfx)$",
    re.IGNORECASE,
)
_JSON_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")


class SafetyError(Exception):
    """Raised when an input would leave the read-only, no-secrets contract."""


def assert_not_secret(path: Path) -> None:
    if SECRET_NAME.search(path.name):
        raise SafetyError(f"refusing to open a secret-like filename: {path.name}")


def assert_safe_json_name(filename: str) -> None:
    if not _JSON_NAME.fullmatch(filename) or filename.endswith(".tmp"):
        raise SafetyError(f"unsafe output name: {filename}")


def assert_no_traversal(value: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise SafetyError("path is empty")
    if "\n" in value or "\r" in value or "\x00" in value:
        raise SafetyError("path contains a control character")
    path = Path(value)
    if ".." in path.parts:
        raise SafetyError("path traversal is not allowed")
    assert_not_secret(path)
    return path


def jload(path: Path):
    """Load a JSON file. Returns None if it cannot be read. Never opens secret-like names."""
    assert_not_secret(path)
    try:
        with open(path, encoding="utf-8-sig") as handle:
            return json.load(handle)
    except (OSError, ValueError, UnicodeError):
        return None


def atomic_write_json(directory: Path, filename: str, payload: dict) -> None:
    """Replace `filename` inside `directory` by writing a sibling temp file and renaming it.

    Renaming replaces the previous snapshot of this same output. Symlinks are refused.
    Nothing is unlinked.
    """
    assert_safe_json_name(filename)
    if directory.is_symlink():
        raise SafetyError("refusing to write into a symlinked directory")
    directory.mkdir(parents=True, exist_ok=True)
    dest = directory / filename
    tmp = directory / f"{filename}.tmp"
    if dest.is_symlink() or tmp.is_symlink():
        raise SafetyError("refusing to write through a symlink")
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, dest)
