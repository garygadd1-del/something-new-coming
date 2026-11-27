"""Coder-trio needle decision.

Three coder agents, one needle each:

  * shallow — thin slice, short transforms, first hit
  * mid     — everyday code and sourced facts
  * deep    — hard designs and cross-checking

Gary, 2026-10-24 ~11:33 PM EDT:

  * each needle is shallow / mid / deep (trinary depth)
  * each needle has thickness 0–1
  * merge results only past a complexity threshold
  * each coder votes confidence; a wide spread argues before commit
  * cross-checked facts take high confidence

Kleene T/U/F gates the commit. Contradiction (T against F) becomes U.
``decide`` only returns a decision. The proxy is what may POST, and only in
explicit live mode.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field

from .classify import CATEGORY_WEIGHT, GENERATIVE, SINGLE_DEPTH, classify_rules
from .experts import suggest_expert
from .index import Pointer
from .settings import Settings
from .textutil import clamp01, terms_of
from .trinary import F, T, U, Claim, to_gate

DEPTHS = ("shallow", "mid", "deep")
# Parallel to Kleene rank F < U < T. Depth is not a truth value.
DEPTH_RANK = {"shallow": 0, "mid": 1, "deep": 2}
DEPTH_KLEENE_PARALLEL = {"shallow": F, "mid": U, "deep": T}

CODERS = {
    "shallow": "coder-shallow",
    "mid": "coder-mid",
    "deep": "coder-deep",
}


@dataclass
class Needle:
    depth: str
    thickness: float
    pointers: tuple[Pointer, ...] = ()
    claim: Claim | None = None
    confidence: float | None = None
    coder: str = ""

    def __post_init__(self):
        if self.depth not in DEPTHS:
            raise ValueError("depth must be shallow, mid, or deep")
        self.thickness = round(clamp01(self.thickness), 3)
        if not self.coder:
            self.coder = CODERS[self.depth]
        if self.confidence is not None:
            self.confidence = round(clamp01(self.confidence), 3)


def complexity_score(query: str, category: str, terms: list[str]) -> float:
    """Query complexity in [0, 1]. Independent of which coder answered."""
    length = min(1.0, len(query or "") / 1200.0)
    term_span = min(1.0, len(terms) / 10.0)
    cat = CATEGORY_WEIGHT.get(category, CATEGORY_WEIGHT["unknown"])
    return round(clamp01(0.20 * length + 0.20 * term_span + 0.60 * cat), 3)


def vote_confidence(needle: Needle, claim: Claim) -> float:
    """Coder certainty in [0, 1]. Separate from accept/hold/reject."""
    if needle.confidence is not None:
        return needle.confidence
    if claim.value == U:
        return round(clamp01(needle.thickness * 0.5), 3)
    sourced = 0.10 if (claim.source or "").strip() else 0.0
    return round(clamp01(0.20 + 0.70 * needle.thickness + sourced), 3)


def _normalize(statement: str) -> str:
    return " ".join((statement or "").split()).lower()


def _empty_needle(depth: str, query: str) -> Needle:
    return Needle(depth, 0.0, (), Claim(query or "", U, 0.0, ""))


def _claim_from_search(query: str, needle: Needle, settings: Settings) -> Claim:
    pointer = needle.pointers[0] if needle.pointers else None
    if pointer is None:
        return Claim(query or "", U, 0.0, "")
    statement = pointer.title or pointer.snippet or query or ""
    source = pointer.path or ""
    value = T if source and needle.thickness >= settings.sourced_true_thickness else U
    return Claim(statement, value, 0.0, source)


def _align_claim(needle: Needle, settings: Settings, query: str) -> tuple[Claim, float]:
    base = needle.claim if needle.claim is not None else _claim_from_search(query, needle, settings)
    confidence = vote_confidence(needle, base)
    claim = Claim(base.statement, base.value, confidence, base.source)
    return claim, confidence


def _merge_group(claims: list[Claim]) -> Claim:
    merged = claims[0]
    for claim in claims[1:]:
        merged = merged.merge(claim)
    return merged


def _group_claims(claims: list[Claim]) -> dict[str, list[Claim]]:
    groups: dict[str, list[Claim]] = {}
    for claim in claims:
        groups.setdefault(_normalize(claim.statement), []).append(claim)
    return groups


def _is_cross_checked(claims: list[Claim]) -> bool:
    """Two or more sourced coders agree on T or on F, and that statement is not disputed.

    A group that already contains both T and F is a contradiction, not a cross-check.
    """
    for group in _group_claims(claims).values():
        values = {c.value for c in group}
        if T in values and F in values:
            continue
        for value in (T, F):
            sourced = [c for c in group if c.value == value and (c.source or "").strip()]
            if len(sourced) >= 2:
                return True
    return False


def _has_contradiction(claims: list[Claim]) -> bool:
    for group in _group_claims(claims).values():
        values = {c.value for c in group}
        if T in values and F in values:
            return True
    return False


def _primary_group(claims: list[Claim]) -> list[Claim]:
    groups = list(_group_claims(claims).values())
    if not groups:
        return []
    def key(group):
        sourced = sum(1 for c in group if (c.source or "").strip())
        thick = max(c.confidence for c in group)
        return (sourced, len(group), thick)
    return max(groups, key=key)


def needles_from_index(index, query: str) -> list[Needle]:
    found = []
    for depth in DEPTHS:
        hit = index.search(query, depth)
        found.append(Needle(depth, hit["thickness"], tuple(hit["pointers"])))
    return found


def _ensure_three(query: str, needles: list[Needle] | None, index, settings: Settings) -> list[Needle]:
    if needles is not None:
        by_depth = {n.depth: n for n in needles}
        return [by_depth.get(depth) or _empty_needle(depth, query) for depth in DEPTHS]
    if index is None and settings.index_path:
        from .index import NeedleIndex

        path = settings.index_path
        if NeedleIndex(path).available():
            index = NeedleIndex(path)
    if index is not None and getattr(index, "available", lambda: True)():
        return needles_from_index(index, query)
    return [_empty_needle(depth, query) for depth in DEPTHS]


def _expert_public(expert, why: str) -> dict | None:
    if expert is None:
        return None
    data = expert.as_dict()
    # Model paths can point at local weights. The router never opens them.
    # Keep the label so a human can see which file the staged config named.
    data["match"] = why
    data["url"] = "http://%s:%s" % (expert.dial_host, expert.port)
    return data


def needs_model(category: str, action: str, truth: str) -> bool:
    """Whether a local completion would be requested once live mode is on.

    Argue / hold never call a model. A contradiction is not papered over.
    Generative categories still need a coder model when the needle only cited
    a fact. Lookups with a decided truth stay on the pointer.
    """
    if action in {"argue", "hold"}:
        return False
    if category in GENERATIVE:
        return True
    return truth == U


def render_answer(decision: dict) -> str:
    action = decision["action"]
    if action == "argue":
        lines = [
            "HOLD. Coder confidence spread is too wide to commit.",
            "Spread %.3f (wide at %.3f)." % (decision["spread"], decision["wide_spread"]),
        ]
    elif action == "hold":
        lines = ["HOLD. Coder claims contradict (T against F) so the merged value is U."]
    elif decision["commit"]:
        lines = [
            "COMMIT %s at confidence %.3f." % (decision["truth"], decision["confidence"])
        ]
    else:
        lines = ["No commit. Truth %s, action %s." % (decision["truth"], action)]
    if decision.get("merged"):
        lines.append("Results were merged (complexity past the threshold).")
    else:
        lines.append("Results were not merged. Single %s needle." % decision.get("depth"))
    pointers = decision.get("pointers") or []
    if pointers:
        lines.append("Pointers:")
        for pointer in pointers[:6]:
            lines.append("- %s :: %s" % (pointer.get("path") or "?", pointer.get("title") or ""))
    expert = decision.get("suggested_expert") or {}
    if expert:
        lines.append(
            "Suggested expert %s :%s (%s, %s)."
            % (expert.get("name"), expert.get("port"), expert.get("role"), expert.get("match"))
        )
    if decision.get("dry_run"):
        lines.append("Dry-run: no model was called.")
    return "\n".join(lines)


@dataclass
class _Built:
    claims: list[Claim] = field(default_factory=list)
    votes: list[dict] = field(default_factory=list)


def _build(query: str, needles: list[Needle], settings: Settings) -> _Built:
    built = _Built()
    for needle in needles:
        claim, confidence = _align_claim(needle, settings, query)
        built.claims.append(claim)
        built.votes.append(
            {
                "coder": needle.coder,
                "depth": needle.depth,
                "depth_rank": DEPTH_RANK[needle.depth],
                "depth_kleene_parallel": DEPTH_KLEENE_PARALLEL[needle.depth],
                "thickness": needle.thickness,
                "confidence": confidence,
                "truth": claim.value,
                "statement": claim.statement,
                "source": claim.source,
                "pointers": [p.as_dict() for p in needle.pointers],
            }
        )
    return built


def decide(
    query: str,
    needles: list[Needle] | None = None,
    index=None,
    settings: Settings | None = None,
    experts=None,
) -> dict:
    """Return a JSON-ready decision. Never performs HTTP. The proxy calls a model only when live mode is on."""
    settings = settings or Settings()
    query = query or ""
    category, score, scores = classify_rules(query)
    terms = terms_of(query)
    complexity = complexity_score(query, category, terms)
    trio = _ensure_three(query, needles, index, settings)
    built = _build(query, trio, settings)
    confidences = [v["confidence"] for v in built.votes]
    spread = round(max(confidences) - min(confidences), 3) if confidences else 0.0
    wide = spread >= settings.wide_spread
    contradiction = _has_contradiction(built.claims)
    cross = _is_cross_checked(built.claims)
    past_threshold = complexity >= settings.merge_threshold
    reasons = [
        "category=%s (rules, score %.1f)" % (category, score),
        "complexity %.3f %s merge threshold %.3f"
        % (
            complexity,
            ">=" if past_threshold else "<",
            settings.merge_threshold,
        ),
    ]

    selected_depth = SINGLE_DEPTH.get(category, "shallow")
    selected_claim = next(c for c, v in zip(built.claims, built.votes) if v["depth"] == selected_depth)

    merged_flag = False
    if past_threshold:
        group = _primary_group(built.claims)
        if len(group) >= 2:
            result_claim = _merge_group(group)
            merged_flag = True
            reasons.append("merged %d claims that share a statement" % len(group))
        else:
            result_claim = selected_claim
            reasons.append("complexity past threshold but coders did not share a statement; no merge")
    else:
        result_claim = selected_claim
        reasons.append("below complexity threshold: single %s needle, no merge" % selected_depth)

    observed = U if contradiction else result_claim.value
    confidence = round(result_claim.confidence, 3)

    if wide:
        action = "argue"
        truth = U
        commit = False
        reasons.append(
            "confidence spread %.3f >= %.3f: argue before commit" % (spread, settings.wide_spread)
        )
        if contradiction:
            reasons.append("T vs F contradiction is also present; commit stays held")
    elif contradiction:
        action = "hold"
        truth = U
        commit = False
        reasons.append("T vs F contradiction -> U, hold")
    elif observed == U:
        action = "merge" if merged_flag else "single"
        truth = U
        commit = False
        reasons.append("no decided truth; not a commit")
    else:
        action = "merge" if merged_flag else "single"
        truth = observed
        commit = True
        if cross:
            confidence = round(max(confidence, settings.high_confidence), 3)
            reasons.append(
                "cross-checked facts -> high confidence %.3f" % confidence
            )
        else:
            reasons.append("single-source or uncorroborated fact")

    if action == "argue":
        confidence = round(min(confidences), 3) if confidences else 0.0

    high = bool(commit and cross and confidence >= settings.high_confidence)
    depth_out = "merged" if merged_flag and action != "single" else selected_depth
    if action == "argue":
        depth_out = "merged" if merged_flag else selected_depth

    expert_depth = selected_depth if not merged_flag else "deep" if category in {"heavy", "research"} else selected_depth
    if experts is None:
        from .experts import load_experts

        experts = load_experts(settings.experts_path, allow_remote=settings.allow_remote_hosts)
    expert, why = suggest_expert(query, tuple(experts), expert_depth)
    model_needed = needs_model(category, action, truth)
    reasons.append("suggested expert via %s" % why)

    pointers = []
    for vote in built.votes:
        pointers.extend(vote["pointers"])

    decision = {
        "id": uuid.uuid4().hex[:12],
        "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "query": query[:2000],
        "category": category,
        "rule_scores": scores,
        "complexity": complexity,
        "merge_threshold": settings.merge_threshold,
        "merged": merged_flag and action != "single",
        "spread": spread,
        "wide_spread": settings.wide_spread,
        "spread_wide": wide,
        "cross_checked": cross,
        "action": action,
        "commit": commit,
        "truth": truth,
        "observed_truth": observed,
        "gate": to_gate(truth),
        "confidence": confidence,
        "high_confidence": high,
        "depth": depth_out,
        "selected_depth": selected_depth,
        "votes": built.votes,
        "pointers": pointers[:12],
        "suggested_expert": _expert_public(expert, why),
        "needs_model": model_needed,
        "reasons": reasons,
        "dry_run": True,
        "inference": {
            "base": settings.inference_base,
            "called": False,
            "error": None,
            "url": None,
        },
    }
    decision["merged"] = bool(merged_flag)
    _log_decision(decision, settings)
    return decision


def _log_decision(decision: dict, settings: Settings) -> None:
    """Optional JSONL. Off unless log_dir is set. No snippets and no query text."""
    if not settings.log_dir:
        return
    import json
    import os

    try:
        os.makedirs(settings.log_dir, exist_ok=True)
        slim = {
            "id": decision["id"],
            "ts": decision["ts"],
            "category": decision["category"],
            "action": decision["action"],
            "commit": decision["commit"],
            "truth": decision["truth"],
            "complexity": decision["complexity"],
            "spread": decision["spread"],
            "cross_checked": decision["cross_checked"],
            "depth": decision["depth"],
            "votes": [
                {"coder": v["coder"], "depth": v["depth"], "confidence": v["confidence"], "truth": v["truth"]}
                for v in decision["votes"]
            ],
        }
        name = "decisions_%s.jsonl" % datetime.date.today().isoformat()
        path = os.path.join(settings.log_dir, name)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(slim, ensure_ascii=False) + "\n")
    except OSError:
        return
