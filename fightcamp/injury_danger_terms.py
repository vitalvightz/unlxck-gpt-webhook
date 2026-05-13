from __future__ import annotations

import re
from typing import TypedDict


class DangerRoute(TypedDict):
    category: str
    route: str
    reason: str


DANGER_TERM_ROUTES: dict[str, DangerRoute] = {
    "out of socket": {"category": "dislocation", "route": "restricted_rehab_only", "reason": "possible dislocation signal"},
    "popped out": {"category": "dislocation", "route": "restricted_rehab_only", "reason": "possible dislocation/subluxation signal"},
    "joint separation": {"category": "dislocation", "route": "restricted_rehab_only", "reason": "possible joint separation signal"},
    "dislocated": {"category": "dislocation", "route": "restricted_rehab_only", "reason": "dislocation signal"},
    "subluxation": {"category": "dislocation", "route": "restricted_rehab_only", "reason": "subluxation signal"},
    "cannot bear weight": {"category": "functional_red_flag", "route": "restricted_rehab_only", "reason": "loss of weight-bearing ability"},
    "unable to walk": {"category": "functional_red_flag", "route": "restricted_rehab_only", "reason": "major functional loss"},
    "giving way": {"category": "instability_event", "route": "needs_review", "reason": "joint instability event"},
    "gave way": {"category": "instability_event", "route": "needs_review", "reason": "joint instability event"},
    "buckled": {"category": "instability_event", "route": "needs_review", "reason": "joint instability event"},
    "collapsed": {"category": "instability_event", "route": "needs_review", "reason": "collapse event"},
    "collapse": {"category": "instability_event", "route": "needs_review", "reason": "collapse event"},
    "snap": {"category": "structural_event", "route": "needs_review", "reason": "possible structural injury signal"},
    "snapped": {"category": "structural_event", "route": "needs_review", "reason": "possible structural injury signal"},
    "pop": {"category": "structural_event", "route": "needs_review", "reason": "possible structural injury signal"},
    "popped": {"category": "structural_event", "route": "needs_review", "reason": "possible structural injury signal"},
}

_BENIGN_SUPPRESSOR_PATTERNS = (
    r"\bno\s+pain\b",
    r"\bpainless\b",
    r"\bno\s+swelling\b",
    r"\bcan\s+walk\b",
    r"\bcan\s+still\s+walk\b",
    r"\bcan\s+bear\s+weight\b",
    r"\bable\s+to\s+bear\s+weight\b",
    r"\bsound\s+only\b",
    r"\bnoise\s+only\b",
)


def detect_danger_term_routes(text: str) -> list[dict[str, str]]:
    cleaned = " ".join(str(text or "").lower().split())
    if not cleaned:
        return []

    benign_noise = any(re.search(p, cleaned) for p in _BENIGN_SUPPRESSOR_PATTERNS)
    found: list[dict[str, str]] = []
    for phrase, route in DANGER_TERM_ROUTES.items():
        if not re.search(rf"(?<!\\w){re.escape(phrase)}(?!\\w)", cleaned):
            continue
        if benign_noise and route["category"] in {"structural_event", "instability_event"}:
            continue
        found.append({"term": phrase, **route})
    return found
