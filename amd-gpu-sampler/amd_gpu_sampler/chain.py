"""Append-only SHA-256 JSONL health chain.

Each record binds to the previous hash:

    sha256(prev_hex + "|" + canonical_json_without_hash)

canonical JSON uses sorted keys, compact separators, and UTF-8.
The chain anchors at 64 zero hex digits. Sequence numbers start at 1
and never reset when the log rolls to a new day file.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from amd_gpu_sampler.safety import SafetyError

GENESIS_PREV = "0" * 64
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_TYPE = re.compile(r"^[a-z_]{1,32}$")
_LOG_NAME = re.compile(r"^health_\d{8}\.jsonl$")
_MAX_BODY = 262144

# Locked vector (see tests/test_chain.py):
# prev = 64 zeros
# body = {"data":{"a":1},"prev":"<64 zeros>","seq":1,"ts":"2026-10-25T00:00:00.000+00:00","type":"note","unix":1.0}
# sha256 = 17f3ba2e4131a661e4e88b3662b1bd82531dd9ec44426998af2d33dd52933a7a


class ChainError(Exception):
    """The on-disk chain cannot be extended without a human looking at it."""


def digest(prev: str, record_without_hash: dict) -> str:
    body = json.dumps(record_without_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(f"{prev}|{body}".encode("utf-8")).hexdigest()


def now_iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec="milliseconds")


@dataclass
class VerifyReport:
    ok: bool
    records: int
    head_hash: str | None
    errors: list[str]


def verify_records(records: list[dict]) -> VerifyReport:
    """Verify hash links, sequence, and monotonic timestamps.

    A log whose first record is seq 1 must anchor at the genesis hash.
    A partial slice may start later; its first `prev` is the anchor, and
    every record's own hash is still recomputed.
    """
    errors: list[str] = []
    prev_hash: str | None = None
    prev_seq: int | None = None
    prev_unix: float | None = None
    for index, rec in enumerate(records):
        prefix = f"record {index}"
        if not isinstance(rec, dict):
            errors.append(f"{prefix} is not an object")
            continue
        missing = [key for key in ("seq", "ts", "unix", "type", "data", "prev", "hash") if key not in rec]
        if missing:
            errors.append(f"{prefix} missing {missing[0]}")
            continue
        seq = rec["seq"]
        if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
            errors.append(f"{prefix} has a bad seq")
        elif prev_seq is not None and seq != prev_seq + 1:
            errors.append(f"{prefix} seq {seq} does not follow {prev_seq}")
        elif seq == 1 and rec["prev"] != GENESIS_PREV:
            errors.append(f"{prefix} seq 1 must anchor at genesis")
        if not isinstance(rec["ts"], str) or not rec["ts"]:
            errors.append(f"{prefix} has a bad ts")
        unix = rec["unix"]
        if isinstance(unix, bool) or not isinstance(unix, (int, float)):
            errors.append(f"{prefix} has a bad unix time")
        elif prev_unix is not None and float(unix) < prev_unix:
            errors.append(f"{prefix} unix time moved backwards")
        if not isinstance(rec["type"], str) or not _TYPE.fullmatch(rec["type"]):
            errors.append(f"{prefix} has a bad type")
        if not isinstance(rec["data"], dict):
            errors.append(f"{prefix} data must be an object")
        prev = rec["prev"]
        hashed = rec["hash"]
        if not isinstance(prev, str) or not _HEX64.fullmatch(prev):
            errors.append(f"{prefix} has a bad prev")
        elif prev_hash is not None and prev != prev_hash:
            errors.append(f"{prefix} prev does not match the previous hash")
        if not isinstance(hashed, str) or not _HEX64.fullmatch(hashed):
            errors.append(f"{prefix} has a bad hash")
        else:
            body = {key: value for key, value in rec.items() if key != "hash"}
            try:
                expected = digest(prev if isinstance(prev, str) else "", body)
            except (TypeError, ValueError):
                expected = ""
            if hashed != expected:
                errors.append(f"{prefix} hash mismatch")
        if isinstance(seq, int) and not isinstance(seq, bool):
            prev_seq = seq
        if isinstance(unix, (int, float)) and not isinstance(unix, bool):
            prev_unix = float(unix)
        if isinstance(hashed, str):
            prev_hash = hashed
        if len(errors) >= 20:
            break
    return VerifyReport(ok=not errors, records=len(records), head_hash=prev_hash if not errors else None, errors=errors)


class Chain:
    def __init__(self, logdir: Path):
        self.dir = Path(logdir)
        if self.dir.exists() and self.dir.is_symlink():
            raise SafetyError("refusing to use a symlinked log directory")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.seq = 0
        self.prev = GENESIS_PREV
        self.last_t = 0.0
        self.last_unix = 0.0
        self._fh = None
        self._day: str | None = None
        self._resume()

    def _resume(self) -> None:
        if not any(self.dir.iterdir()):
            return
        records = iter_log_records(self.dir)
        if not records:
            return
        report = verify_records(records)
        if not report.ok:
            raise ChainError(report.errors[0] if report.errors else "log chain failed verification")
        last = records[-1]
        self.seq = int(last["seq"])
        self.prev = str(last["hash"])
        self.last_t = float(last["unix"])
        self.last_unix = float(last["unix"])

    def add(self, typ: str, data: dict, t: float | None = None) -> dict:
        if not isinstance(data, dict):
            raise ChainError("chain data must be an object")
        if not _TYPE.fullmatch(typ):
            raise ChainError("chain type is not allowed")
        stamp = time.time() if t is None else float(t)
        if stamp < self.last_t:
            stamp = self.last_t
        unix = round(stamp, 3)
        if unix < self.last_unix:
            unix = self.last_unix
        record = {
            "seq": self.seq + 1,
            "ts": now_iso(stamp),
            "unix": unix,
            "type": typ,
            "data": data,
            "prev": self.prev,
        }
        encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        if len(encoded.encode("utf-8")) > _MAX_BODY:
            raise ChainError("chain record is too large")
        record["hash"] = digest(self.prev, {key: value for key, value in record.items() if key != "hash"})
        self._write(record, stamp)
        self.seq = int(record["seq"])
        self.prev = str(record["hash"])
        self.last_t = stamp
        self.last_unix = unix
        return record

    def _write(self, record: dict, stamp: float) -> None:
        day = datetime.fromtimestamp(stamp).strftime("%Y%m%d")
        name = f"health_{day}.jsonl"
        if not _LOG_NAME.fullmatch(name):
            raise SafetyError("refusing log filename")
        path = self.dir / name
        if path.is_symlink():
            raise SafetyError("refusing to append through a symlink")
        if day != self._day:
            self.close()
            self._fh = open(path, "a", encoding="utf-8", newline="\n")
            self._day = day
        assert self._fh is not None
        self._fh.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None
            self._day = None


def iter_log_records(logdir: Path) -> list[dict]:
    if not logdir.is_dir():
        raise ChainError(f"log directory not found: {logdir}")
    records: list[dict] = []
    files = sorted(path for path in logdir.iterdir() if path.is_file() and _LOG_NAME.fullmatch(path.name))
    if not files and any(logdir.iterdir()):
        raise ChainError("log directory has no health_YYYYMMDD.jsonl files")
    for path in files:
        with open(path, encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except ValueError as exc:
                    raise ChainError(f"{path.name}:{line_no} is not JSON") from exc
                records.append(rec)
    return records


def verify_log(path: Path) -> VerifyReport:
    """Verify a log directory or a single health JSONL file. Does not modify it."""
    if path.is_file():
        records = []
        with open(path, encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    records.append(json.loads(line))
                except ValueError:
                    return VerifyReport(False, 0, None, [f"{path.name}:{line_no} is not JSON"])
        return verify_records(records)
    return verify_records(iter_log_records(path))
