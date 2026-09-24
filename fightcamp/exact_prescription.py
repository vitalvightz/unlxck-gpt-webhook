"""Resolve bank dose ranges into one executable, conservative working dose.

This operates on a selected prescription, never on bank evidence or safety prose.
The existing session/phase selection and countdown caps remain the authorities;
when they leave a range, workload and intensity take its lower bound while rest
takes its upper bound. A number without a dose unit is not interpreted as load.
"""
from __future__ import annotations

import re

_RANGE = re.compile(r"(?<![\w.])(?P<low>\d+(?:\.\d+)?)\s*[-–—]\s*(?P<high>\d+(?:\.\d+)?)")
_DOSE_UNIT = re.compile(
    r"^\s*(?:sets?\b|reps?\b|rounds?\b|holds?\b|bursts?\b|"
    r"%|kg\b|kgs\b|lb\b|lbs\b|s\b|sec\b|secs\b|seconds?\b|"
    r"m\b|min\b|mins\b|minutes?\b|RPE\b|RIR\b|[x×])",
    re.I,
)
_WORKING_RANGE = re.compile(
    r"(?<![\w.])\d+(?:\.\d+)?\s*[-–—]\s*\d+(?:\.\d+)?\s*"
    r"(?:sets?\b|reps?\b|rounds?\b|holds?\b|bursts?\b|%|kg\b|"
    r"lbs?\b|s\b|sec\b|seconds?\b|min\b|minutes?\b|[x×])",
    re.I,
)
_EFFORT_RANGE = re.compile(r"\b(?:RPE|RIR)\s*\d+(?:\.\d+)?\s*[-–—]\s*\d", re.I)
_PREFIX_RANGE = re.compile(
    r"\b(?:sets?|reps?|rounds?|work|rest|recovery|reset|duration|load)\s*[:=]?\s*"
    r"\d+(?:\.\d+)?\s*[-–—]\s*\d+(?:\.\d+)?\b", re.I,
)
_TRIPLE = re.compile(r"\b\d+\s*[x×]\s*\d+\s*[x×]\s*\d+\b", re.I)
_UNLABELLED_TIME = re.compile(
    r"\b(?:rest|work|duration)\s*[:=]?\s*\d+(?:\.\d+)?\b"
    r"(?!\s*(?:s\b|sec\b|secs\b|seconds?\b|min\b|mins\b|minutes?\b))",
    re.I,
)
_UNLABELLED_LOAD = re.compile(
    r"\bload\s*[:=]?\s*\d+(?:\.\d+)?\b"
    r"(?!\s*(?:%|kg\b|kgs\b|lb\b|lbs\b))",
    re.I,
)


def ambiguous_working_dose(text: str) -> bool:
    """True for a ranged dose or an unlabeled three-number multiplier."""
    return bool(_WORKING_RANGE.search(text) or _EFFORT_RANGE.search(text) or _PREFIX_RANGE.search(text) or _TRIPLE.search(text))


def missing_working_units(text: str) -> bool:
    """A stated work/rest/duration quantity must say seconds or minutes."""
    return bool(_UNLABELLED_TIME.search(text) or _UNLABELLED_LOAD.search(text))


def resolve_working_prescription(text: str) -> str:
    """Select exact quantities from unit-bearing bank ranges.

    A rest range selects its longer end. All other dose ranges select their
    lower end. Non-dose prose (for example, a D-21 to D-8 eligibility window)
    is preserved. An unresolvable alternative remains visible to validation.
    """
    source = str(text or "")

    def choose(match: re.Match[str]) -> str:
        tail = source[match.end():]
        head = source[max(0, match.start() - 28):match.start()]
        if not (_DOSE_UNIT.match(tail) or re.search(
            r"\b(?:RPE|RIR|sets?|reps?|rounds?|work|rest|recovery|reset|duration|load)\s*[:=]?\s*$",
            head, re.I,
        )):
            return match.group(0)
        rest_context = bool(re.search(r"\b(?:rest|recovery|reset|RIR)\s*[:=]?\s*$", head, re.I))
        rest_context = rest_context or bool(re.match(
            r"\s*(?:s|sec|secs|seconds?|min|mins|minutes?)\s+(?:rest|recovery|reset)\b",
            tail, re.I,
        ))
        return match.group("high" if rest_context else "low")

    return _RANGE.sub(choose, source)


def label_strength_sets_reps(text: str) -> str:
    """Expand a strength bank's two-number shorthand when it names rep work."""
    source = str(text or "")
    match = re.search(r"\b(\d+)\s*[x×]\s*(\d+)\b", source, re.I)
    if not match:
        return source
    before = source[max(0, match.start() - 8):match.start()]
    after = source[match.end():]
    if re.search(r"sets?\s*$", before, re.I) or re.match(r"\s*(?:s|sec|seconds?|min|minutes?)\b", after, re.I):
        return source
    sets, reps = int(match.group(1)), int(match.group(2))
    labelled = f"{sets} {'set' if sets == 1 else 'sets'} x {reps} {'rep' if reps == 1 else 'reps'}"
    return source[:match.start()] + labelled + re.sub(r"^\s*reps?\b", "", after, count=1, flags=re.I)
