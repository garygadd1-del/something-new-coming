"""Rule classifier for coder-trio routing.

Patterns are adapted from the staged needle router. They only label a query.
They never call a model. The optional Bonsai HTTP classifier from the staged
module is intentionally absent: this package does not read API keys.
"""

from __future__ import annotations

import re

RULES = {
    "smalltalk": [
        (
            r"^\s*(hi|hello|hey|yo|thanks|thank you|thx|good (morning|night|evening)|how are you|what'?s up|you there|ok(ay)?|cool|nice)\b[\s\W]*(ara)?[\s\W]*$",
            3.0,
        ),
        (r"^\s*(how'?s it going|are you (there|ok|awake))\b", 2.0),
    ],
    "code": [
        (
            r"\b(write|create|generate|implement|fix|debug|refactor|optimi[sz]e|port|convert)\b.{0,40}\b(python|javascript|typescript|powershell|bash|rust|c\+\+|c#|godot|gdscript|script|function|class|module|program|regex|sql|unit tests?)\b",
            3.0,
        ),
        (r"```", 2.0),
        (r"\b(traceback|stack ?trace|segfault|compile error|syntax error|exception)\b", 2.5),
        (r"\b(pull request|git (rebase|merge|diff)|dockerfile|compose file)\b", 1.5),
    ],
    "heavy": [
        (r"\b(prove|proof|theorem|lemma|derive|derivation|formal(ly)?|rigorous(ly)?)\b", 3.0),
        (r"\b(step[- ]by[- ]step|chain of thought|think (hard|carefully|deeply))\b", 2.0),
        (
            r"\b(design|architect|plan)\b.{0,50}\b(system|architecture|pipeline|protocol|framework|strategy)\b",
            2.5,
        ),
        (
            r"\b(trade-?offs?|critique|red[- ]team|stress[- ]test|analy[sz]e)\b.{0,60}\b(design|plan|architecture|argument|proposal|strategy)\b",
            2.5,
        ),
        (
            r"\b(write|compose|draft)\b.{0,30}\b(essay|story|chapter|long|detailed|monologue|speech|poem|song)\b",
            2.5,
        ),
        (
            r"\b(matrix|tensor|eigen|gradient|integral|differential|convolution)\b.{0,60}\b(factori[sz]ation|solve|compute|derive|prove|decomposition)\b",
            3.0,
        ),
    ],
    "research": [
        (
            r"\b(research|latest|current(ly)?|news|today|this week|up to date)\b.{0,60}\b(on|about|for|in|of)\b",
            2.0,
        ),
        (r"\b(search the web|look (it )?up online|find sources|cite sources|with sources|web search)\b", 3.0),
        (
            r"\b(compare|survey|literature)\b.{0,40}\b(papers|studies|sources|vendors|products|providers|competitors)\b",
            2.5,
        ),
    ],
    "transform": [
        (
            r"\b(summari[sz]e|tl;?dr|rewrite|rephrase|paraphrase|translate|proofread|fix (the )?grammar|extract|classify|categori[sz]e|label|reformat|convert (this|the) (text|list))\b",
            2.5,
        ),
    ],
    "explain": [
        (
            r"\b(explain|why (is|does|do|did)|how does|how do|what'?s the difference|difference between|compare|pros and cons|walk me through|help me understand)\b",
            2.0,
        ),
    ],
    "memory": [
        (
            r"\b(do you remember|remember when|what did i (say|tell)|did i (say|tell|mention)|what do you know about me|my (name|birthday|plan|project)s?|last time we)\b",
            3.0,
        ),
    ],
    "lookup": [
        (
            r"^\s*(what|what'?s|whats|who|who'?s|when|where|which|how (much|many|long|old|big)|is there|are there|do i need|does .{0,40} (cost|require|need))\b",
            1.5,
        ),
        (
            r"\b(define|definition of|meaning of|fee|fees|cost|price|deadline|requirement|requirements|rule|rules|limit|where is|which file|find (me )?the|look up|what port|what is|status of)\b",
            1.5,
        ),
    ],
}

# Near-tie precedence. First match at the top score wins.
PRECEDENCE = (
    "heavy",
    "code",
    "research",
    "transform",
    "explain",
    "memory",
    "lookup",
    "smalltalk",
)

# How hard the query is before any needle is opened. Used as the main term
# of the complexity score. Simple lookups stay under the merge threshold.
CATEGORY_WEIGHT = {
    "smalltalk": 0.05,
    "lookup": 0.20,
    "memory": 0.30,
    "transform": 0.35,
    "unknown": 0.40,
    "explain": 0.55,
    "code": 0.70,
    "research": 0.75,
    "heavy": 0.90,
}

# Depth used when complexity is below the merge threshold (one coder, no blend).
SINGLE_DEPTH = {
    "smalltalk": "shallow",
    "lookup": "shallow",
    "transform": "shallow",
    "unknown": "shallow",
    "memory": "mid",
    "explain": "mid",
    "code": "mid",
    "research": "deep",
    "heavy": "deep",
}

GENERATIVE = {"code", "heavy", "research", "explain", "transform"}


def classify_rules(text):
    """Return (category, score, score_map). No network."""
    scores = {}
    t = text or ""
    for cat, pats in RULES.items():
        for rx, weight in pats:
            if re.search(rx, t, re.I | re.S):
                scores[cat] = scores.get(cat, 0.0) + weight
    if not scores:
        return "unknown", 0.0, {}
    best = max(scores.values())
    cat = next(c for c in PRECEDENCE if scores.get(c, -1) >= best - 0.5)
    return cat, scores[cat], {k: round(v, 2) for k, v in scores.items()}
