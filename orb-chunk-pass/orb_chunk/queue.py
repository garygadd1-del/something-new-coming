"""Load, normalize, validate, filter, and plan landfall chunk jobs.

Nothing in this module starts a process.
"""

from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from orb_chunk.contract import (
    CAMERA_CONTRACT,
    CAMERA_ORDER,
    ID_RE_SOURCE,
    LANDFALL_FPS,
    LANDFALL_RENDER_STAGE,
    LANDFALL_RES,
    LANDFALL_SCENE,
    LANDFALL_SEQ,
    OWNER,
    SCHEMA_VERSION,
    USER_FLAGS,
)
from orb_chunk.errors import QueueError

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
LEGACY_SCHEMA_PATH = PACKAGE_ROOT / "schema" / "legacy_queue.schema.json"
NORMALIZED_SCHEMA_PATH = PACKAGE_ROOT / "schema" / "chunk_queue.schema.json"
DEFAULT_QUEUE_PATH = PACKAGE_ROOT / "queues" / "queue_v2.json"

ID_RE = re.compile(ID_RE_SOURCE)
CAPTURED_FROM = "Fuzzy66 Render_Chunks_20261022 queue_v2.json"


def read_json(path: Path):
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise QueueError([f"cannot read {path}: {exc}"]) from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise QueueError([f"{path}: invalid JSON: {exc}"]) from exc


@lru_cache(maxsize=1)
def legacy_schema() -> dict:
    return json.loads(LEGACY_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def normalized_schema() -> dict:
    return json.loads(NORMALIZED_SCHEMA_PATH.read_text(encoding="utf-8"))


def schema_errors(instance, schema: dict) -> list[str]:
    validator = Draft202012Validator(schema)
    found: list[str] = []
    errors = sorted(
        validator.iter_errors(instance),
        key=lambda err: ("/".join(str(part) for part in err.absolute_path), err.message),
    )
    for err in errors:
        loc = "/".join(str(part) for part in err.absolute_path) or "<root>"
        found.append(f"{loc}: {err.message}")
        if len(found) >= 40:
            found.append("... more schema errors omitted")
            break
    return found


def norm_path(value: str) -> str:
    return value.replace("\\", "/").rstrip("/")


def plan_basename(plan: str) -> str:
    return norm_path(plan).rsplit("/", 1)[-1]


def path_basename(value: str) -> str:
    return norm_path(value).rsplit("/", 1)[-1]


def format_zoom(zoom: float) -> str:
    return f"{zoom:.1f}"


def build_args(job: dict) -> list[str]:
    return [
        job["scene"],
        "--",
        f"--plan={job['plan']}",
        f"--stage={job['render_stage']}",
        f"--seq={job['seq']}",
        f"--fps={job['fps']}",
        f"--t0={job['t0']}",
        f"--zoom={format_zoom(job['zoom'])}",
        f"--follow={job['follow']}",
        f"--outdir={job['outdir']}",
    ]


def quote_arg(arg: str) -> str:
    if arg == "" or any(ch in arg for ch in ' \t"'):
        return '"' + arg.replace('"', '\\"') + '"'
    return arg


def godot_argv(job: dict, godot: str = "godot") -> list[str]:
    """Planned Godot argv. The caller prints it and does not execute it."""
    return [godot, "--path", job["proj"], "--resolution", job["res"], *job["args"]]


def _parse_user_args(args: list[str], prefix: str) -> tuple[dict | None, list[str]]:
    errors: list[str] = []
    if len(args) < 3 or args[1] != "--":
        return None, [f"{prefix}: args must be scene, '--', then --key=value flags"]
    scene = args[0]
    if not scene.startswith("res://"):
        errors.append(f"{prefix}: scene must be a res:// path")
    flags: dict[str, str] = {}
    for index, token in enumerate(args[2:], start=2):
        if token == "--" or not token.startswith("--") or "=" not in token[2:]:
            errors.append(f"{prefix}: args[{index}] is not a --key=value flag")
            continue
        key, value = token[2:].split("=", 1)
        if key in flags:
            errors.append(f"{prefix}: duplicate flag --{key}")
        flags[key] = value
    missing = [key for key in USER_FLAGS if key not in flags]
    extra = sorted(set(flags) - set(USER_FLAGS))
    for key in missing:
        errors.append(f"{prefix}: missing --{key}")
    for key in extra:
        errors.append(f"{prefix}: unknown flag --{key}")
    if errors:
        return None, errors

    try:
        parsed = {
            "scene": scene,
            "plan": flags["plan"],
            "render_stage": int(flags["stage"]),
            "seq": int(flags["seq"]),
            "fps": int(flags["fps"]),
            "t0": int(flags["t0"]),
            "zoom": float(flags["zoom"]),
            "follow": int(flags["follow"]),
            "outdir": flags["outdir"],
        }
    except ValueError as exc:
        return None, [f"{prefix}: flag value is not a number ({exc})"]
    if parsed["follow"] not in (0, 1):
        return None, [f"{prefix}: --follow must be 0 or 1"]
    return parsed, []


def _convert_legacy_job(item: dict, index: int) -> tuple[dict | None, list[str]]:
    prefix = f"jobs[{index}]"
    parsed, errors = _parse_user_args(item["args"], prefix)
    match = ID_RE.match(item["id"])
    if match is None:
        errors.append(
            f"{prefix}: id {item['id']!r} is not lf_<site>_<wide|close|mid>_t<offset>"
        )
    if parsed is None or match is None:
        return None, errors
    site, camera = match.group(1), match.group(2)
    job = {
        "ordinal": index,
        "id": item["id"],
        "site": site,
        "camera": camera,
        "t0": parsed["t0"],
        "proj": item["proj"],
        "mk": item["mk"],
        "res": item["res"],
        "scene": parsed["scene"],
        "plan": parsed["plan"],
        "render_stage": parsed["render_stage"],
        "seq": parsed["seq"],
        "fps": parsed["fps"],
        "zoom": parsed["zoom"],
        "follow": parsed["follow"],
        "outdir": parsed["outdir"],
        "args": list(item["args"]),
    }
    return job, errors


def legacy_to_normalized(items: list[dict], source: str) -> dict:
    jobs: list[dict] = []
    errors: list[str] = []
    for index, item in enumerate(items):
        job, job_errors = _convert_legacy_job(item, index)
        errors.extend(job_errors)
        if job is not None:
            jobs.append(job)
    if errors:
        raise QueueError(errors)
    project = jobs[0]["proj"] if jobs else ""
    return {
        "schema_version": SCHEMA_VERSION,
        "source": source,
        "captured_from": CAPTURED_FROM,
        "owner": OWNER,
        "execute": False,
        "project": project,
        "jobs": jobs,
    }


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=1e-9)


def semantic_errors(doc: dict) -> list[str]:
    errors: list[str] = []
    jobs = doc.get("jobs", [])
    if doc.get("owner") != OWNER:
        errors.append(f"owner must be {OWNER}")
    if doc.get("execute") is not False:
        errors.append("execute must be false")

    projects = {job["proj"] for job in jobs}
    if len(projects) > 1:
        errors.append("jobs use multiple proj paths: " + ", ".join(sorted(projects)))
    elif projects and doc.get("project") != next(iter(projects)):
        errors.append("project does not match job proj")

    ordinals = [job["ordinal"] for job in jobs]
    if ordinals != list(range(len(jobs))):
        errors.append("ordinal must be 0..n-1 in file order")

    seen: set[str] = set()
    for index, job in enumerate(jobs):
        prefix = f"jobs[{index}]"
        job_id = job["id"]
        if job_id in seen:
            errors.append(f"duplicate id {job_id}")
        seen.add(job_id)

        match = ID_RE.match(job_id)
        if match is None:
            errors.append(f"{prefix}: id {job_id!r} does not match the chunk pattern")
            continue
        id_site, id_camera, id_t0 = match.group(1), match.group(2), int(match.group(3))
        if job["site"] != id_site:
            errors.append(f"{prefix}: site {job['site']!r} does not match id {job_id}")
        if job["camera"] != id_camera:
            errors.append(f"{prefix}: camera {job['camera']!r} does not match id {job_id}")
        if job["t0"] != id_t0:
            errors.append(f"{prefix}: t0 {job['t0']} does not match id {job_id}")

        contract = CAMERA_CONTRACT.get(job["camera"])
        if contract is None:
            errors.append(f"{prefix}: camera {job['camera']!r} is not a pass")
        elif not _close(job["zoom"], contract["zoom"]) or job["follow"] != contract["follow"]:
            errors.append(
                f"{prefix}: camera {job['camera']} requires zoom {contract['zoom']} "
                f"follow {contract['follow']}"
            )

        if job["scene"] != LANDFALL_SCENE:
            errors.append(f"{prefix}: scene must be {LANDFALL_SCENE}")
        if job["render_stage"] != LANDFALL_RENDER_STAGE:
            errors.append(f"{prefix}: render_stage must be {LANDFALL_RENDER_STAGE}")
        if job["seq"] != LANDFALL_SEQ:
            errors.append(f"{prefix}: seq must be {LANDFALL_SEQ}")
        if job["fps"] != LANDFALL_FPS:
            errors.append(f"{prefix}: fps must be {LANDFALL_FPS}")
        if job["res"] != LANDFALL_RES:
            errors.append(f"{prefix}: res must be {LANDFALL_RES}")

        if norm_path(job["mk"]) != norm_path(job["outdir"]):
            errors.append(f"{prefix}: mk does not match outdir")
        if path_basename(job["outdir"]) != job_id:
            errors.append(f"{prefix}: outdir must end with {job_id}")
        if plan_basename(job["plan"]) != f"plan_{job['site']}.json":
            errors.append(f"{prefix}: plan file must be plan_{job['site']}.json")
        if list(job["args"]) != build_args(job):
            errors.append(f"{prefix}: args do not match fields")
    return errors


def validate_instance(data, source_name: str) -> dict:
    """Return a normalized document or raise QueueError."""
    if isinstance(data, list):
        legacy_problems = schema_errors(data, legacy_schema())
        if legacy_problems:
            raise QueueError(legacy_problems)
        doc = legacy_to_normalized(data, source=source_name)
    elif isinstance(data, dict):
        doc = data
    else:
        raise QueueError(["root must be a legacy array or a normalized object"])

    problems = schema_errors(doc, normalized_schema())
    if not problems:
        problems = semantic_errors(doc)
    if problems:
        raise QueueError(problems)
    return doc


def load_queue(path: Path | None = None) -> dict:
    queue_path = Path(path) if path is not None else DEFAULT_QUEUE_PATH
    data = read_json(queue_path)
    return validate_instance(data, source_name=queue_path.name)


def dump_queue(doc: dict) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def camera_counts(jobs: list[dict]) -> dict[str, int]:
    counts = {camera: 0 for camera in CAMERA_ORDER}
    for job in jobs:
        counts[job["camera"]] += 1
    return counts


def filter_jobs(
    jobs: list[dict],
    *,
    cameras: list[str] | None = None,
    sites: list[str] | None = None,
    t0s: list[int] | None = None,
    ids: list[str] | None = None,
) -> list[dict]:
    camera_set = set(cameras or [])
    site_set = set(sites or [])
    t0_set = set(t0s or [])
    id_set = set(ids or [])
    errors: list[str] = []

    known_cameras = {job["camera"] for job in jobs}
    known_sites = {job["site"] for job in jobs}
    known_t0 = {job["t0"] for job in jobs}
    known_ids = {job["id"] for job in jobs}
    for camera in sorted(camera_set - known_cameras):
        errors.append(f"unknown camera: {camera}")
    for site in sorted(site_set - known_sites):
        errors.append(f"unknown site: {site}")
    for t0 in sorted(t0_set - known_t0):
        errors.append(f"unknown t0: {t0}")
    for job_id in sorted(id_set - known_ids):
        errors.append(f"unknown id: {job_id}")
    if errors:
        raise QueueError(errors)

    selected = []
    for job in jobs:
        if camera_set and job["camera"] not in camera_set:
            continue
        if site_set and job["site"] not in site_set:
            continue
        if t0_set and job["t0"] not in t0_set:
            continue
        if id_set and job["id"] not in id_set:
            continue
        selected.append(job)

    if id_set:
        found = {job["id"] for job in selected}
        missing = id_set - found
        for job_id in sorted(missing):
            errors.append(f"id excluded by other filters: {job_id}")
    if errors:
        raise QueueError(errors)
    return selected


def order_jobs(jobs: list[dict], order: str) -> list[dict]:
    if order == "file":
        return sorted(jobs, key=lambda job: job["ordinal"])
    if order == "camera":
        rank = {camera: index for index, camera in enumerate(CAMERA_ORDER)}
        return sorted(jobs, key=lambda job: (rank[job["camera"]], job["t0"], job["ordinal"]))
    raise QueueError([f"unknown order: {order}"])


def select_jobs(
    doc: dict,
    *,
    cameras: list[str] | None = None,
    sites: list[str] | None = None,
    t0s: list[int] | None = None,
    ids: list[str] | None = None,
    order: str = "file",
) -> list[dict]:
    return order_jobs(
        filter_jobs(doc["jobs"], cameras=cameras, sites=sites, t0s=t0s, ids=ids),
        order,
    )
