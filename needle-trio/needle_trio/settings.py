"""Configurable paths and thresholds. Defaults are local and dry-run.

Environment variables override fields when ``settings_from_env`` is called.
None of them are secret names. API keys are not read.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from urllib.parse import urlparse

DEFAULT_INFERENCE_BASE = "http://127.0.0.1:5001"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# This proxy must not bind the inference port or the staged expert ports.
PROTECTED_PORTS = frozenset({5001, 5011, 5021, 5032, 5033, 18830, 18850, 18860, 18871, 27300, 27301, 5002})

# Cloud LLM hosts are refused even if an operator flips allow_remote.
CLOUD_LLM_MARKERS = (
    "openai.com",
    "api.openai.com",
    "anthropic.com",
    "googleapis.com",
    "generativelanguage.googleapis.com",
    "azure.com",
    "openrouter.ai",
    "groq.com",
    "mistral.ai",
    "cohere.ai",
    "api.cohere",
)


@dataclass(frozen=True)
class Settings:
    merge_threshold: float = 0.50
    wide_spread: float = 0.35
    high_confidence: float = 0.90
    sourced_true_thickness: float = 0.62
    inference_base: str = DEFAULT_INFERENCE_BASE
    listen_host: str = "127.0.0.1"
    listen_port: int = 5031
    live: bool = False
    request_timeout_s: float = 30.0
    allow_remote_hosts: bool = False
    index_path: str | None = None
    experts_path: str | None = None
    log_dir: str | None = None

    def with_updates(self, **kwargs) -> "Settings":
        return replace(self, **kwargs)


def _flag(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _float_env(name: str):
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    return float(raw)


def settings_from_env(base: Settings | None = None) -> Settings:
    s = base or Settings()
    updates = {}
    live = _flag("NEEDLE_TRIO_LIVE")
    if live is not None:
        updates["live"] = live
    remote = _flag("NEEDLE_TRIO_ALLOW_REMOTE")
    if remote is not None:
        updates["allow_remote_hosts"] = remote
    merge = _float_env("NEEDLE_TRIO_MERGE_THRESHOLD")
    if merge is not None:
        updates["merge_threshold"] = merge
    spread = _float_env("NEEDLE_TRIO_WIDE_SPREAD")
    if spread is not None:
        updates["wide_spread"] = spread
    base_url = os.environ.get("NEEDLE_TRIO_INFERENCE_BASE")
    if base_url:
        updates["inference_base"] = base_url.strip()
    port = os.environ.get("NEEDLE_TRIO_LISTEN_PORT")
    if port:
        updates["listen_port"] = int(port)
    host = os.environ.get("NEEDLE_TRIO_LISTEN_HOST")
    if host:
        updates["listen_host"] = host.strip()
    index = os.environ.get("NEEDLE_TRIO_INDEX")
    if index:
        updates["index_path"] = index.strip()
    experts = os.environ.get("NEEDLE_TRIO_EXPERTS")
    if experts:
        updates["experts_path"] = experts.strip()
    log_dir = os.environ.get("NEEDLE_TRIO_LOG_DIR")
    if log_dir:
        updates["log_dir"] = log_dir.strip()
    if not updates:
        return s
    return s.with_updates(**updates)


def assert_inference_allowed(url: str, *, allow_remote: bool) -> None:
    """Refuse cloud LLM APIs. Remote hosts need an explicit opt-in and still cannot be cloud APIs."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("inference base must be an http(s) URL with a host")
    host = parsed.hostname.lower()
    marker_hay = host
    for marker in CLOUD_LLM_MARKERS:
        if marker in marker_hay:
            raise ValueError("cloud LLM APIs are not an inference target for needle-trio")
    if host not in LOOPBACK_HOSTS and not allow_remote:
        raise ValueError("inference host must be loopback unless NEEDLE_TRIO_ALLOW_REMOTE=1")


def assert_bind_allowed(host: str, port: int) -> None:
    if host.lower() not in LOOPBACK_HOSTS:
        raise ValueError("proxy binds loopback only")
    if int(port) in PROTECTED_PORTS:
        raise ValueError("port %s is protected (inference or expert); refusing to bind" % port)
    if not (1 <= int(port) <= 65535):
        raise ValueError("port out of range")
