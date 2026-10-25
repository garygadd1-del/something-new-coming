"""Load and validate Kalwi role files.

Role files are the contract for a seat: env, skill stub, resource caps,
network mode, and the hard gates. Unknown keys fail closed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from kalwi_ewok.errors import ConfigError
from kalwi_ewok.yaml_subset import parse_simple_yaml

ROLES = ("kalwi-render", "kalwi-ledger", "kalwi-scout")
ROLE_FILES = tuple(f"{name}.yaml" for name in ROLES)
ROLE_SKILL = {
    "kalwi-render": "render-stub",
    "kalwi-ledger": "ledger-stub",
    "kalwi-scout": "scout-stub",
}
RENDER_HANDOFF = "No-Limit Local / Game Dev"

ALLOWED_ENV_KEYS = frozenset(
    {
        "KALWI_ROLE",
        "KALWI_TASK",
        "KALWI_GPU",
        "KALWI_SKILLS",
        "KALWI_PROD_DEPLOY",
        "KALWI_MONEY_SENDS",
        "KALWI_SECRETS",
        "KALWI_HANDOFF",
    }
)

# Patterns are concatenated so the source tree does not contain a contiguous
# credential prefix. Values are still rejected at load time.
_SECRET_VALUE_RE = re.compile(
    "|".join(
        [
            r"sk-" + r"ant-",
            r"sk-" + r"proj-",
            r"sk-" + r"[A-Za-z0-9]{16,}",
            r"AKIA" + r"[0-9A-Z]{16}",
            r"ghp_" + r"[A-Za-z0-9]{20,}",
            r"github_" + r"pat_",
            r"xox[baprs]-",
            r"AIza" + r"[0-9A-Za-z\-_]{20,}",
            r"-----BEGIN " + r"[A-Z ]*PRIVATE KEY-----",
        ]
    )
)
_CLOUD_HOSTS = (
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "api.groq.com",
    "openrouter.ai",
)
_VALUE_CHARS = re.compile(r"[\n\r\x00$`;&|<>]")

_TOP_KEYS = frozenset(
    {
        "name",
        "summary",
        "skills",
        "env",
        "resources",
        "network",
        "gpu",
        "volumes",
        "security",
        "gates",
    }
)
_RESOURCE_KEYS = frozenset({"cpus", "memory_mb", "pids_limit"})
_NETWORK_KEYS = frozenset({"mode"})
_GPU_KEYS = frozenset({"seize", "handoff"})
_SECURITY_KEYS = frozenset({"read_only", "no_new_privileges", "cap_drop"})
_GATE_KEYS = frozenset({"prod_deploy", "money_sends", "secrets_in_image"})


@dataclass(frozen=True)
class RoleConfig:
    name: str
    summary: str
    skills: tuple[str, ...]
    env: Mapping[str, str]
    cpus: float
    memory_mb: int
    pids_limit: int
    network_mode: str
    gpu_seize: bool
    gpu_handoff: str
    volumes: tuple[str, ...]
    read_only: bool
    no_new_privileges: bool
    cap_drop: tuple[str, ...]
    prod_deploy: bool
    money_sends: bool
    secrets_in_image: bool


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_roles_dir() -> Path:
    return package_root() / "roles"


def load_roles(directory: Path | None = None) -> dict[str, RoleConfig]:
    directory = default_roles_dir() if directory is None else Path(directory)
    found = sorted(path.name for path in directory.glob("*.yaml"))
    expected = sorted(ROLE_FILES)
    if found != expected:
        raise ConfigError(
            f"{directory} must contain exactly {', '.join(expected)}; found {found or 'nothing'}"
        )
    loaded = {}
    for name in ROLE_FILES:
        config = load_role(directory / name)
        loaded[config.name] = config
    return loaded


def load_role(path: Path) -> RoleConfig:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"{path} is not utf-8") from exc
    try:
        data = parse_simple_yaml(text)
    except ConfigError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    config = validate_role(data)
    if Path(path).stem != config.name:
        raise ConfigError(f"{path} name {config.name} must match the filename")
    return config


def validate_role(data: dict) -> RoleConfig:
    _exact_keys(data, _TOP_KEYS, "role")
    name = _require_str(data["name"], "name")
    if name not in ROLES:
        raise ConfigError(f"unknown role {name}")
    summary = _require_str(data["summary"], "summary")
    if not 20 <= len(summary) <= 200:
        raise ConfigError("summary must be 20 to 200 characters")

    skills = _require_str_list(data["skills"], "skills")
    expected_skill = ROLE_SKILL[name]
    if skills != [expected_skill]:
        raise ConfigError(f"{name} skill set must be exactly {expected_skill}")

    env = _validate_env(data["env"], name, expected_skill)
    cpus, memory_mb, pids_limit = _validate_resources(data["resources"])
    network_mode = _validate_network(data["network"])
    gpu_seize, gpu_handoff = _validate_gpu(data["gpu"], name)
    if env["KALWI_HANDOFF"] != gpu_handoff:
        raise ConfigError("KALWI_HANDOFF must match gpu.handoff")

    volumes = _require_str_list(data["volumes"], "volumes")
    if volumes:
        raise ConfigError("volumes must be empty")

    read_only, no_new_privileges, cap_drop = _validate_security(data["security"])
    prod_deploy, money_sends, secrets_in_image = _validate_gates(data["gates"])

    return RoleConfig(
        name=name,
        summary=summary,
        skills=(expected_skill,),
        env=MappingProxyType(env),
        cpus=cpus,
        memory_mb=memory_mb,
        pids_limit=pids_limit,
        network_mode=network_mode,
        gpu_seize=gpu_seize,
        gpu_handoff=gpu_handoff,
        volumes=(),
        read_only=read_only,
        no_new_privileges=no_new_privileges,
        cap_drop=tuple(cap_drop),
        prod_deploy=prod_deploy,
        money_sends=money_sends,
        secrets_in_image=secrets_in_image,
    )


def _validate_env(raw, name: str, skill: str) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ConfigError("env must be a mapping")
    if set(raw) != ALLOWED_ENV_KEYS:
        extra = sorted(set(raw) - ALLOWED_ENV_KEYS)
        missing = sorted(ALLOWED_ENV_KEYS - set(raw))
        raise ConfigError(f"env keys mismatch; extra={extra} missing={missing}")
    env: dict[str, str] = {}
    for key in sorted(raw):
        value = raw[key]
        if not isinstance(value, str):
            raise ConfigError(f"{key} must be a string")
        if len(value) > 120:
            raise ConfigError(f"{key} is too long")
        if _VALUE_CHARS.search(value):
            raise ConfigError(f"illegal character in {key}")
        if _SECRET_VALUE_RE.search(value):
            raise ConfigError(f"refusing secret-like value in {key}")
        lowered = value.lower()
        for host in _CLOUD_HOSTS:
            if host in lowered:
                raise ConfigError(f"refusing cloud API host in {key}")
        env[key] = value
    if env["KALWI_ROLE"] != name:
        raise ConfigError("KALWI_ROLE must match the role name")
    if env["KALWI_TASK"] != "stub":
        raise ConfigError("KALWI_TASK must be stub")
    if env["KALWI_GPU"] != "off":
        raise ConfigError("KALWI_GPU must be off")
    if env["KALWI_SKILLS"] != skill:
        raise ConfigError("KALWI_SKILLS must match the role skill stub")
    if env["KALWI_PROD_DEPLOY"] != "0":
        raise ConfigError("prod deploy is forbidden")
    if env["KALWI_MONEY_SENDS"] != "0":
        raise ConfigError("money sends are forbidden")
    if env["KALWI_SECRETS"] != "none":
        raise ConfigError("secrets in the seat env are forbidden")
    return env


def _validate_resources(raw) -> tuple[float, int, int]:
    _exact_keys(raw, _RESOURCE_KEYS, "resources")
    cpus = raw["cpus"]
    if isinstance(cpus, bool) or not isinstance(cpus, float):
        raise ConfigError("cpus must be a decimal number")
    if not 0.1 <= cpus <= 1.0:
        raise ConfigError("cpus must be between 0.1 and 1.0")
    memory_mb = _require_int(raw["memory_mb"], "memory_mb")
    if not 64 <= memory_mb <= 256:
        raise ConfigError("memory_mb must be between 64 and 256")
    pids_limit = _require_int(raw["pids_limit"], "pids_limit")
    if not 16 <= pids_limit <= 64:
        raise ConfigError("pids_limit must be between 16 and 64")
    return cpus, memory_mb, pids_limit


def _validate_network(raw) -> str:
    _exact_keys(raw, _NETWORK_KEYS, "network")
    mode = _require_str(raw["mode"], "network.mode")
    if mode != "none":
        raise ConfigError("network mode must be none")
    return mode


def _validate_gpu(raw, name: str) -> tuple[bool, str]:
    _exact_keys(raw, _GPU_KEYS, "gpu")
    seize = raw["seize"]
    if not isinstance(seize, bool):
        raise ConfigError("gpu.seize must be a boolean")
    if seize:
        raise ConfigError("GPU seize is forbidden")
    handoff = _require_str(raw["handoff"], "gpu.handoff")
    if name == "kalwi-render":
        if handoff != RENDER_HANDOFF:
            raise ConfigError(
                "render hands off GPU work to No-Limit Local / Game Dev"
            )
    elif handoff != "none":
        raise ConfigError("gpu.handoff must be none for this role")
    return False, handoff


def _validate_security(raw) -> tuple[bool, bool, list[str]]:
    _exact_keys(raw, _SECURITY_KEYS, "security")
    read_only = raw["read_only"]
    no_new = raw["no_new_privileges"]
    if read_only is not True:
        raise ConfigError("read_only must be true")
    if no_new is not True:
        raise ConfigError("no_new_privileges must be true")
    cap_drop = _require_str_list(raw["cap_drop"], "cap_drop")
    if cap_drop != ["ALL"]:
        raise ConfigError("cap_drop must be ALL")
    return True, True, cap_drop


def _validate_gates(raw) -> tuple[bool, bool, bool]:
    _exact_keys(raw, _GATE_KEYS, "gates")
    prod = raw["prod_deploy"]
    money = raw["money_sends"]
    secrets = raw["secrets_in_image"]
    for label, value in (
        ("prod_deploy", prod),
        ("money_sends", money),
        ("secrets_in_image", secrets),
    ):
        if not isinstance(value, bool):
            raise ConfigError(f"gates.{label} must be a boolean")
        if value:
            raise ConfigError(f"{label.replace('_', ' ')} is forbidden")
    return False, False, False


def _exact_keys(raw, expected: frozenset[str], label: str) -> None:
    if not isinstance(raw, dict):
        raise ConfigError(f"{label} must be a mapping")
    if set(raw) != expected:
        extra = sorted(set(raw) - expected)
        missing = sorted(expected - set(raw))
        raise ConfigError(f"{label} keys mismatch; extra={extra} missing={missing}")


def _require_str(value, label: str) -> str:
    if not isinstance(value, str) or value == "":
        raise ConfigError(f"{label} must be a non-empty string")
    return value


def _require_int(value, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{label} must be an integer")
    return value


def _require_str_list(value, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ConfigError(f"{label} must be a list")
    if not all(isinstance(item, str) and item != "" for item in value):
        raise ConfigError(f"{label} must be a list of strings")
    return list(value)
