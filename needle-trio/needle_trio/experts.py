"""Expert trio config: Hermes, gpt-oss, Ternary-Bonsai.

The shipped JSON is the staged Fuzzy66 router (2026-10-21). This loader never
starts or stops a process and never opens the model files named in the config.
Dial targets stay on loopback unless the caller sets allow_remote_hosts.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .settings import LOOPBACK_HOSTS

# Package root is needle-trio/, one level above this file's package directory
# only when the package lives in needle-trio/needle_trio. The JSON sits beside
# the package: needle-trio/config/experts.fuzzy66.json.
_DEFAULT_JSON = Path(__file__).resolve().parent.parent / "config" / "experts.fuzzy66.json"

DEPTH_EXPERT = {
    "shallow": "bonsai8b",
    "mid": "gptoss20b",
    "deep": "hermes14b",
}

# Tie-break order from the staged fallback_chain.
FALLBACK_CHAIN = ("hermes14b", "gptoss20b", "bonsai8b")


@dataclass(frozen=True)
class Expert:
    name: str
    port: int
    role: str
    keywords: tuple[str, ...]
    depth: str
    configured_host: str
    dial_host: str
    model: str = ""
    existing: bool = True
    note: str = ""
    remote: bool = False

    def as_dict(self):
        data = asdict(self)
        data["keywords"] = list(self.keywords)
        return data


def _depth_for(name: str) -> str:
    for depth, expert_name in DEPTH_EXPERT.items():
        if expert_name == name:
            return depth
    return "mid"


def _dial_host(configured: str, *, allow_remote: bool) -> tuple[str, bool]:
    host = (configured or "127.0.0.1").strip()
    remote = host.lower() not in LOOPBACK_HOSTS
    if remote and not allow_remote:
        return "127.0.0.1", True
    return host, remote


def experts_from_data(data: dict, *, allow_remote: bool = False) -> tuple[Expert, ...]:
    experts = []
    for raw in data.get("experts") or []:
        configured = str(raw.get("host") or "127.0.0.1")
        dial, remote = _dial_host(configured, allow_remote=allow_remote)
        name = str(raw["name"])
        experts.append(
            Expert(
                name=name,
                port=int(raw["port"]),
                role=str(raw.get("role") or ""),
                keywords=tuple(str(k).lower() for k in (raw.get("keywords") or [])),
                depth=_depth_for(name),
                configured_host=configured,
                dial_host=dial,
                model=str(raw.get("model") or ""),
                existing=bool(raw.get("existing", True)),
                note=str(raw.get("note") or ""),
                remote=remote,
            )
        )
    return tuple(experts)


def load_experts(path: str | Path | None = None, *, allow_remote: bool = False) -> tuple[Expert, ...]:
    target = Path(path) if path else _DEFAULT_JSON
    if not target.is_file():
        return experts_from_data(_builtin_payload(), allow_remote=allow_remote)
    with target.open("r", encoding="utf-8") as handle:
        return experts_from_data(json.load(handle), allow_remote=allow_remote)


def _builtin_payload() -> dict:
    """Used only when the shipped JSON is missing. Ports and roles match Fuzzy66."""
    return {
        "experts": [
            {
                "name": "hermes14b",
                "port": 5021,
                "host": "127.0.0.1",
                "role": "persona / deep reasoning",
                "keywords": ["why", "explain", "reason", "plan", "feel", "philosophy"],
            },
            {
                "name": "gptoss20b",
                "port": 5032,
                "host": "127.0.0.1",
                "role": "research + sourced summaries (CPU)",
                "keywords": ["research", "source", "compare", "summarize", "history", "facts"],
            },
            {
                "name": "bonsai8b",
                "port": 5033,
                "host": "127.0.0.1",
                "role": "small talk, short transforms, classifier (CPU)",
                "keywords": ["hi", "hello", "rewrite", "shorten", "classify", "list"],
            },
        ]
    }


def _keyword_score(query: str, expert: Expert) -> int:
    q = query or ""
    score = 0
    for keyword in expert.keywords:
        if not keyword:
            continue
        if re.search(r"\b" + re.escape(keyword) + r"\b", q, re.I):
            score += 1
    return score


def suggest_expert(query: str, experts: tuple[Expert, ...], depth: str) -> tuple[Expert | None, str]:
    """Keyword match first. Otherwise the expert that owns this trinary depth."""
    if not experts:
        return None, "none"
    ranked = sorted(
        experts,
        key=lambda expert: (
            -_keyword_score(query, expert),
            FALLBACK_CHAIN.index(expert.name) if expert.name in FALLBACK_CHAIN else 99,
        ),
    )
    best = ranked[0]
    if _keyword_score(query, best) > 0:
        return best, "keyword"
    wanted = DEPTH_EXPERT.get(depth, DEPTH_EXPERT["mid"])
    for expert in experts:
        if expert.name == wanted:
            return expert, "depth"
    return best, "depth"
