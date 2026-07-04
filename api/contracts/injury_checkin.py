"""Daily injury check-in reconciliation (Block 4 §6 follow-up).

The Today check-in carries a single ``active_injury`` flag (none/stable/worse).
That can't say *which* injury, and it can't tell a resolved injury from a brand
new one. This contract reconciles the athlete's declared injuries for a training
day against their existing open ``injury_flags`` so every injury keeps identity
over time:

* a report with no ``flag_id`` opens a new flag,
* an ``improving`` report parks the flag in ``monitoring``,
* a ``resolved`` report closes it (``resolved``), and
* an ``ongoing`` / ``worse`` report keeps it ``open`` (severity may change).

Pure and deterministic: this computes the create/update plan; the service
applies it to storage and stamps ``resolved_at``. Capturing per-injury state now
is exactly what lets a later PR make plans dynamic when an injury clears or a new
one appears — this PR only persists it and feeds the risk watch.
"""

from __future__ import annotations

import re
from typing import Iterable, Literal, Mapping, Sequence

from pydantic import BaseModel, Field, model_validator

from .command_view import RiskWatchItem, make_risk

InjuryFlagSeverity = Literal["mild", "moderate", "severe"]
InjuryFlagStatus = Literal["open", "monitoring", "resolved"]
# What the athlete reports about an injury on a given day.
InjuryCheckinStatus = Literal["ongoing", "improving", "worse", "resolved"]

# Reported day-state -> persisted flag status. "improving" parks the flag in
# monitoring; "resolved" closes it; "ongoing"/"worse" keep it open.
_FLAG_STATUS_BY_REPORT: dict[str, InjuryFlagStatus] = {
    "ongoing": "open",
    "worse": "open",
    "improving": "monitoring",
    "resolved": "resolved",
}

# Open/active statuses for risk-watch purposes (resolved flags are silent).
ACTIVE_FLAG_STATUSES: frozenset[str] = frozenset({"open", "monitoring"})


class DeclaredInjury(BaseModel):
    """One injury as reported on a daily check-in.

    ``flag_id`` references an existing open flag being updated; without it the
    report is a new injury and needs a ``body_area`` or ``description`` to
    identify it.
    """

    flag_id: str | None = None
    body_area: str = ""
    description: str = ""
    severity: InjuryFlagSeverity | None = None
    status: InjuryCheckinStatus = "ongoing"

    @model_validator(mode="after")
    def _check_identifiable(self) -> "DeclaredInjury":
        if not self.flag_id and not (self.body_area.strip() or self.description.strip()):
            raise ValueError("a new injury needs a body_area or description")
        return self


class FlagUpdate(BaseModel):
    flag_id: str
    fields: dict[str, object] = Field(default_factory=dict)


class ReconciliationPlan(BaseModel):
    """Storage-agnostic plan: flags to create, and existing flags to update."""

    creates: list[dict[str, object]] = Field(default_factory=list)
    updates: list[FlagUpdate] = Field(default_factory=list)


# Canonical injury-type key (from the shared injury synonym logic) -> the short
# athlete-facing noun we display. Everything not listed maps to itself, so only
# the keys whose canonical name reads oddly to an athlete need an entry.
_CONDITION_DISPLAY_NOUN = {"contusion": "bruise"}

# Curated condition words (with their common inflections) stripped out of the
# body-location text so a label never reads "wrist tightness tightness". This is
# deliberately a small, safe list — NOT the full synonym map, whose looser
# entries ("full", "hit", "point"...) would eat real location words.
_CONDITION_STRIP = re.compile(
    r"\b(?:bruis(?:e|ed|ing)|contusion|hyperextend(?:ed|ing|s)?|hyperextension|"
    r"disloc(?:ate|ated|ation)|fractur(?:e|ed)|broken|break|ruptur(?:e|ed)|tears?|torn|"
    r"sprain(?:ed|ing)?|strain(?:ed|ing)?|pulled|tendon[ai]tis|tendinopathy|"
    r"imping(?:ed|ement)|instability|unstable|inflam(?:ed|mation|matory)|"
    r"swollen|swelling|stiff(?:ness)?|tight(?:ness)?|sore(?:ness)?|"
    r"ach(?:e|es|ing|y)|pain(?:ful)?|hurts?|hurting|abrasion|graze|blister|laceration)\b",
    re.I,
)

# Connective/filler words removed once the condition is stripped, leaving only
# the body location. Laterality (left/right) is deliberately kept.
_LOCATION_FILLER = re.compile(
    r"\b(?:is|are|was|were|been|be|has|have|had|got|getting|gets|feels?|feeling|felt|"
    r"seems?|it|this|that|a|an|the|my|some|really|quite|very|bit|of|in|on|with|and)\b",
    re.I,
)


def _clean_location(text: str) -> str:
    """Reduce a body-area string to just the location words (no condition/filler)."""
    text = _CONDITION_STRIP.sub(" ", text)
    text = _LOCATION_FILLER.sub(" ", text)
    text = re.sub(r"[^a-zA-Z\s/-]", " ", text)
    words = [w for w in text.lower().split() if w]
    seen: list[str] = []
    for word in words:
        if word not in seen:
            seen.append(word)
    return " ".join(seen)


def build_injury_label(body_area: object, description: object) -> str:
    """Build a short, athlete-facing injury label using the injury synonym logic.

    The condition is identified with the shared deterministic injury scorer rather
    than parsing the athlete's exact words, so a flag stored as "left wrist" with a
    "tightness" intake type reads as "Left wrist tightness", and colourful phrasing
    ("dead leg", "corked", "black and blue") still resolves to the right noun. The
    location is taken from the clean structured ``body_area`` so free-text notes
    never leak into the label.
    """
    from fightcamp.injury_scoring import score_injury_phrase

    body = str(body_area or "").strip()
    desc = str(description or "").strip()
    location_source = body or desc
    if not location_source:
        return "injury"

    condition_key = str(score_injury_phrase(f"{body} {desc}").get("injury_type") or "")
    condition = (
        _CONDITION_DISPLAY_NOUN.get(condition_key, condition_key)
        if condition_key and condition_key != "unspecified"
        else ""
    )

    location = _clean_location(location_source)
    if condition and location and not location.endswith(condition):
        label = f"{location} {condition}"
    elif condition and not location:
        label = condition
    else:
        label = location or location_source

    label = label.strip()
    if not label:
        return "injury"
    return (label[0].upper() + label[1:])[:60]


def _flag_label(flag: Mapping[str, object]) -> str:
    label = str(flag.get("label") or "").strip()
    if label:
        return label[:60]
    return build_injury_label(flag.get("body_area"), flag.get("description"))


def reconcile_injury_checkin(
    *,
    declared: Sequence[DeclaredInjury],
    open_flag_ids: Iterable[str],
) -> ReconciliationPlan:
    """Build the create/update plan for a day's declared injuries.

    A ``flag_id`` is only honoured when it belongs to the athlete's current open
    flags (``open_flag_ids``) — anything else is treated as a new injury, so a
    stale or foreign id can never mutate another athlete's flag.
    """
    known = {str(flag_id) for flag_id in open_flag_ids}
    creates: list[dict[str, object]] = []
    updates: list[FlagUpdate] = []

    for injury in declared:
        flag_status = _FLAG_STATUS_BY_REPORT[injury.status]
        if injury.flag_id and injury.flag_id in known:
            fields: dict[str, object] = {"status": flag_status}
            if injury.severity is not None:
                fields["severity"] = injury.severity
            if injury.body_area.strip():
                fields["body_area"] = injury.body_area.strip()
            if injury.description.strip():
                fields["description"] = injury.description.strip()
            updates.append(FlagUpdate(flag_id=injury.flag_id, fields=fields))
            continue

        # A brand-new injury reported as already resolved is a no-op — there is
        # nothing to track. Otherwise open (or monitor) a fresh flag.
        if flag_status == "resolved":
            continue
        if not (injury.body_area.strip() or injury.description.strip()):
            raise ValueError("a new injury needs a body_area or description")
        description = injury.description.strip() or injury.body_area.strip()
        creates.append(
            {
                "source": "checkin",
                "body_area": injury.body_area.strip(),
                "description": description,
                "severity": injury.severity or "moderate",
                "status": flag_status,
            }
        )

    return ReconciliationPlan(creates=creates, updates=updates)


def open_injury_flag_risks(
    open_flags: Sequence[Mapping[str, object]],
) -> list[RiskWatchItem]:
    """Surface tracked open injuries as a single risk-watch item.

    A severe open injury reads as a stop-level "keep load off it" item; otherwise
    a softer "training around it" reminder so the badge stays live for as long as
    any injury is open and clears the moment they are all resolved.
    """
    active = [f for f in open_flags if str(f.get("status") or "") in ACTIVE_FLAG_STATUSES]
    if not active:
        return []

    severe = [
        f
        for f in active
        if str(f.get("severity") or "") == "severe" and str(f.get("status") or "") == "open"
    ]
    if severe:
        return [
            make_risk(
                "active_injury_worse",
                text=f"Open severe injury: {_flag_label(severe[0])}. Keep load off it until cleared.",
            )
        ]

    labels = ", ".join(_flag_label(f) for f in active[:2])
    count = len(active)
    noun = "injury" if count == 1 else "injuries"
    return [
        make_risk(
            "reminder",
            text=f"Tracking {count} open {noun}: {labels}. Train around it.",
        )
    ]
