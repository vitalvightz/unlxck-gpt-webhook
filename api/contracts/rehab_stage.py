"""Per-injury rehabilitation stage resolution (PR2).

Rehabilitation stage answers *"what can this injured tissue currently
tolerate?"*. Fight-camp phase (GPP / SPP / TAPER) answers *"where is the athlete
in fight preparation?"*. They are independent dimensions, and this module owns
the first one.

The separation matters because the two used to be conflated. An ankle sprained
in fight week is a brand-new injury that has earned nothing, yet TAPER reads as
"late in the plan"; a six-week-old ankle that has been trained on without
complaint may deserve real loading, yet GPP reads as "early". Camp phase is
therefore **not an argument to this resolver** — it cannot be, so it cannot
advance or regress a stage. It stays where it belongs: modifying dose and
fatigue exposure downstream.

Stage vocabulary is :data:`fightcamp.rehab_schema.REHAB_STAGES` — the canonical
PR1 enum, not a second one::

    calm -> restore -> load -> dynamic -> return

Evidence
--------
Everything is derived from records that already exist. This module defines no
new representation of pain, severity, injury status or history:

* ``injury_flags`` — severity, status, ``latest_reported_status``, onset
  (``created_at``), and the structured surface answers.
* prior ``injury_flags`` rows for the same body area — a cleared injury that is
  re-reported starts over rather than inheriting what the old one earned.
* ``today_checkins`` — ``active_injury``, ``pain``, the canonical
  :data:`~api.contracts.checkin_decision.SAFETY_FLAGS` red-flag toggles, and
  ``recommendation_state``. The ``phase`` column on these rows is deliberately
  never read.
* ``session_completions`` — ``status`` and ``pain_after``, the only record of
  what the athlete actually tolerated under load.

Derived, not stored
-------------------
There is no rehab-stage column, and deliberately so: a stored stage is a second
source of truth that drifts from the injury record the moment a flag is edited,
cleared or re-reported. Every call recomputes from the authoritative history, so
the resolver is pure, deterministic and idempotent — refreshing or retrying can
never advance a stage.

``progressed`` / ``regressed`` are reported the same way: the resolver runs
itself a second time over the evidence *as it stood before today's check-in* and
compares. No transition log required.

Scope note (PR2)
----------------
This module resolves the stage. It does not select drills: PR1's bank metadata
is still mostly ``null``, so rehab selection stays exactly as it is until PR3
migrates the bank content and PR4 makes stage-aware scoring authoritative.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Mapping, Sequence

from fightcamp.injury_taxonomy import derive_urgent_injury_tokens
from fightcamp.rehab_schema import (
    CARE_TYPE_MUSCULOSKELETAL,
    CARE_TYPE_WOUND_CARE,
    REHAB_STAGES,
)

from .checkin_decision import SAFETY_FLAGS
from .injury_signal import ELEVATED_PAIN_AFTER
from .readiness_message import classify_injury_surface

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

STAGE_CALM, STAGE_RESTORE, STAGE_LOAD, STAGE_DYNAMIC, STAGE_RETURN = REHAB_STAGES

#: Rank of each stage, so "regressed" and "progressed" are orderings rather than
#: string comparisons. Sourced from the canonical enum's own order.
STAGE_RANK: dict[str, int] = {stage: index for index, stage in enumerate(REHAB_STAGES)}

#: Reported day-states that count as evidence the injury is settling.
IMPROVING_REPORTS: frozenset[str] = frozenset({"improving", "resolved"})

#: Completion statuses that mean the athlete actually did the session.
COMPLETED_SESSION_STATUSES: frozenset[str] = frozenset({"done", "modified"})

#: The two care pathways an injury can be on, in the canonical PR1 vocabulary.
CARE_PATHWAYS: tuple[str, ...] = (CARE_TYPE_MUSCULOSKELETAL, CARE_TYPE_WOUND_CARE)

CONFIDENCE_LOW, CONFIDENCE_MODERATE, CONFIDENCE_HIGH = "low", "moderate", "high"


# ---------------------------------------------------------------------------
# Reason codes
#
# Machine-readable and stable. They name the evidence, never a diagnosis, and
# carry no athlete-facing medical claim — the copy layers own wording.
# ---------------------------------------------------------------------------

REASON_SURFACE_PATHWAY = "surface_injury_wound_care_pathway"
REASON_RED_FLAG_GATE = "red_flag_medical_gate"
REASON_URGENT_INJURY_TYPE = "urgent_injury_type"
REASON_SEVERE_SEVERITY = "severe_severity_holds_calm"
REASON_NEWLY_REPORTED = "newly_reported_injury"
REASON_RE_REPORTED = "injury_recently_re_reported"
REASON_REPORTED_WORSE = "injury_reported_worse"
REASON_REPEATED_WORSENING = "repeated_worsening_reported"
REASON_RECENT_WORSENING = "recent_worsening_reported"
REASON_NOT_WORSENING = "symptoms_not_worsening"
REASON_BASIC_TOLERANCE = "basic_activity_tolerated"
REASON_LOADING_TOLERANCE = "loading_tolerated_in_session"
REASON_DYNAMIC_TOLERANCE = "sustained_loading_tolerated"
REASON_REPORTED_RESOLVED = "injury_reported_resolved"
REASON_INSUFFICIENT_EVIDENCE = "insufficient_progression_evidence"
REASON_NO_CHECKIN_HISTORY = "no_checkin_history_since_onset"
REASON_NO_SESSION_HISTORY = "no_session_tolerance_recorded"
REASON_UNKNOWN_ONSET = "injury_onset_unknown"


# ---------------------------------------------------------------------------
# Evidence floors
#
# These are ARCHITECTURAL minimums — how many independent reports the system
# insists on seeing before it will describe tissue as tolerating more. They are
# not clinical criteria and are not claimed to be: nothing here asserts a
# healing timeline or a return-to-sport clearance. They exist so that a single
# good day, or a run of days with no training in them, cannot walk an injury up
# the ladder. PR3/PR4 may tighten them against migrated bank content.
#
# The pain floor is deliberately NOT a new number: it reuses the project's
# existing post-session pain vocabulary from ``injury_signal``.
# ---------------------------------------------------------------------------

#: A logged session counts as tolerated only below the existing "elevated" mark.
TOLERATED_PAIN_AFTER_BELOW = ELEVATED_PAIN_AFTER

MIN_TOLERATED_DAYS_FOR_RESTORE = 1
MIN_TOLERATED_DAYS_FOR_LOAD = 3
MIN_TOLERATED_SESSIONS_FOR_LOAD = 1
MIN_TOLERATED_DAYS_FOR_DYNAMIC = 6
MIN_TOLERATED_SESSIONS_FOR_DYNAMIC = 3
MIN_TOLERATED_SESSIONS_FOR_RETURN = 5

#: Worsening reported within this many of the most recent check-in days blocks
#: progression outright, whatever the longer-run counts say.
RECENT_WORSENING_WINDOW_DAYS = 3

#: Two or more worsening days inside the recent window is a setback, not a blip.
REPEATED_WORSENING_COUNT = 2

#: An injury is only described as "newly reported" while this few days have
#: passed since onset. Beyond it, an injury with no reports is unobserved rather
#: than new, and says so.
NEW_INJURY_OBSERVATION_DAYS = 1

#: A flag cleared this recently and then re-reported starts from scratch.
RE_REPORT_WINDOW_DAYS = 14

#: How far back evidence is counted at all, so a months-old streak cannot be
#: reassembled from sporadic check-ins.
EVIDENCE_LOOKBACK_DAYS = 90


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RehabStageEvidence:
    """The counts a decision was actually built from.

    Exposed so a decision can be explained and tested without re-deriving it,
    and so a reviewer can see *why* a stage did not advance.
    """

    tolerated_checkin_days: int = 0
    worsening_checkin_days: int = 0
    recent_worsening_days: int = 0
    tolerated_sessions: int = 0
    has_checkin_history: bool = False
    has_session_history: bool = False
    onset_known: bool = False


@dataclass(frozen=True)
class RehabStageDecision:
    """One injury's resolved rehabilitation stage.

    ``stage`` is ``None`` only on the wound-care pathway, where the MSK ladder
    does not apply at all.

    ``medical_gate`` marks a decision the red-flag / urgent pathway owns. The
    stage is then pinned to the most protective value and carries no permission
    to train — the existing urgent handling remains authoritative above it.
    """

    stage: str | None
    care_pathway: str
    reasons: tuple[str, ...] = ()
    progressed: bool = False
    regressed: bool = False
    confidence: str = CONFIDENCE_LOW
    medical_gate: bool = False
    evidence: RehabStageEvidence = field(default_factory=RehabStageEvidence)

    @property
    def is_wound_care(self) -> bool:
        return self.care_pathway == CARE_TYPE_WOUND_CARE

    def as_dict(self) -> dict[str, Any]:
        """Machine-readable form for payloads and diagnostics."""
        return {
            "stage": self.stage,
            "care_pathway": self.care_pathway,
            "reasons": list(self.reasons),
            "progressed": self.progressed,
            "regressed": self.regressed,
            "confidence": self.confidence,
            "medical_gate": self.medical_gate,
        }


# ---------------------------------------------------------------------------
# Small readers
# ---------------------------------------------------------------------------


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _clean(value).lower()


def _parse_day(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    text = _clean(value)[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _row_day(row: Mapping[str, Any]) -> date | None:
    """The day a check-in or completion row belongs to."""
    for key in ("training_day", "checkin_date", "created_at"):
        day = _parse_day(row.get(key))
        if day is not None:
            return day
    return None


def _pain_after(value: Any) -> int | None:
    if isinstance(value, bool):  # bool is an int subclass — never a pain score
        return None
    try:
        score = int(float(value))
    except (TypeError, ValueError, OverflowError):
        return None
    return score if 0 <= score <= 10 else None


def _has_safety_flag(row: Mapping[str, Any]) -> bool:
    """True when the row carries any canonical red-flag toggle."""
    return any(bool(row.get(flag)) for flag in SAFETY_FLAGS)


def _active_safety_flags(row: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(flag for flag in SAFETY_FLAGS if bool(row.get(flag)))


_URGENT_TOKEN_PATTERNS: tuple[re.Pattern[str], ...] | None = None


def _urgent_token_patterns() -> tuple[re.Pattern[str], ...]:
    """Word-boundary matchers for the canonical urgent injury vocabulary.

    Built from :func:`fightcamp.injury_taxonomy.derive_urgent_injury_tokens`, so
    this module holds no urgent-injury list of its own. Boundaries matter: a bare
    ``in`` test makes "graze" match "grazed rib fracture" but also makes short
    tokens fire inside unrelated words.
    """
    global _URGENT_TOKEN_PATTERNS
    if _URGENT_TOKEN_PATTERNS is None:
        _URGENT_TOKEN_PATTERNS = tuple(
            re.compile(rf"\b{re.escape(token)}\b")
            for token in sorted(derive_urgent_injury_tokens())
            if token
        )
    return _URGENT_TOKEN_PATTERNS


def _is_urgent_injury(injury: Mapping[str, Any]) -> bool:
    """True when the injury text names something the urgent pathway owns."""
    text = " ".join(
        _lower(injury.get(field))
        for field in ("body_area", "description", "injury_type", "rehab_type")
    )
    text = text.replace("_", " ").replace("-", " ")
    if not text.strip():
        return False
    return any(pattern.search(text) for pattern in _urgent_token_patterns())


def _is_surface_injury(injury: Mapping[str, Any]) -> bool:
    """True when the canonical surface classifier routes this to wound care."""
    try:
        return classify_injury_surface(injury) != "non_surface"
    except Exception:  # pragma: no cover - classifier must never decide safety by raising
        # Unknown is not "not skin": fall back to the musculoskeletal ladder,
        # whose gates are the stricter of the two.
        return False


# ---------------------------------------------------------------------------
# Evidence gathering
# ---------------------------------------------------------------------------


def _checkin_day_is_worsening(row: Mapping[str, Any]) -> bool:
    """True when a check-in day reads as the injury going backwards.

    Deliberately broad: worsening drives *regression*, and over-including there
    is the safe direction. Mirrors the readiness engine's own poor-day signals
    (declared worse, high pain, any red-flag toggle, a pull-back decision).
    """
    if _lower(row.get("active_injury")) == "worse":
        return True
    if _lower(row.get("pain")) == "high":
        return True
    if _lower(row.get("recommendation_state") or row.get("decision")) == "pull_back":
        return True
    return _has_safety_flag(row)


def _checkin_day_is_tolerated(row: Mapping[str, Any]) -> bool:
    """True when a check-in day is positive evidence rather than merely not bad.

    A day only counts once it is free of every worsening signal. Silence is not
    tolerance: a row with no check-in never reaches this function at all.
    """
    return not _checkin_day_is_worsening(row)


def _relevant_days(
    rows: Sequence[Mapping[str, Any]],
    *,
    onset: date | None,
    as_of: date | None,
) -> list[tuple[date, Mapping[str, Any]]]:
    """One row per day, newest first, inside the evidence window after onset.

    Deduplicated by day so several rows for one day cannot inflate a count, and
    bounded by ``onset`` so evidence an injury never lived through is not spent
    on it. The onset day is excluded too: a check-in filed the day an injury is
    reported says nothing about how that injury has since held up.
    """
    best_by_day: dict[date, Mapping[str, Any]] = {}
    for row in rows or ():
        if not isinstance(row, Mapping):
            continue
        day = _row_day(row)
        if day is None:
            continue
        if onset is not None and day <= onset:
            continue
        if as_of is not None:
            delta = (as_of - day).days
            if delta < 0 or delta > EVIDENCE_LOOKBACK_DAYS:
                continue
        # A worsening row wins its day: if the athlete reported a setback at any
        # point that day, the day is not tolerance evidence.
        existing = best_by_day.get(day)
        if existing is None or (_checkin_day_is_worsening(row) and not _checkin_day_is_worsening(existing)):
            best_by_day[day] = row
    return sorted(best_by_day.items(), key=lambda item: item[0], reverse=True)


def _session_is_tolerated(row: Mapping[str, Any]) -> bool:
    """True when a logged session is evidence of tolerated load.

    Requires both that the session actually happened and that a pain reading was
    recorded below the project's existing "elevated" mark. A completion with no
    ``pain_after`` proves nothing about tolerance and is not counted — missing
    evidence never reads as success.
    """
    if _lower(row.get("status")) not in COMPLETED_SESSION_STATUSES:
        return False
    pain = _pain_after(row.get("pain_after"))
    return pain is not None and pain < TOLERATED_PAIN_AFTER_BELOW


def _gather_evidence(
    *,
    onset: date | None,
    as_of: date | None,
    checkins: Sequence[Mapping[str, Any]],
    session_completions: Sequence[Mapping[str, Any]],
) -> RehabStageEvidence:
    days = _relevant_days(checkins, onset=onset, as_of=as_of)
    tolerated = sum(1 for _day, row in days if _checkin_day_is_tolerated(row))
    worsening = sum(1 for _day, row in days if _checkin_day_is_worsening(row))

    recent_worsening = 0
    for day, row in days[:RECENT_WORSENING_WINDOW_DAYS]:
        if as_of is not None and (as_of - day).days > RECENT_WORSENING_WINDOW_DAYS:
            continue
        if _checkin_day_is_worsening(row):
            recent_worsening += 1

    session_days = _relevant_days(session_completions, onset=onset, as_of=as_of)
    tolerated_sessions = sum(1 for _day, row in session_days if _session_is_tolerated(row))

    return RehabStageEvidence(
        tolerated_checkin_days=tolerated,
        worsening_checkin_days=worsening,
        recent_worsening_days=recent_worsening,
        tolerated_sessions=tolerated_sessions,
        has_checkin_history=bool(days),
        has_session_history=bool(session_days),
        onset_known=onset is not None,
    )


# ---------------------------------------------------------------------------
# The ladder
# ---------------------------------------------------------------------------


def _restore_unmet(evidence: RehabStageEvidence, _injury_state: Mapping[str, Any]) -> str | None:
    # The "nothing reported yet" gate above already guarantees both of these, so
    # in practice this rung always passes. It is stated anyway so the ladder is
    # total: every rung declares what it needs, and reading one does not require
    # knowing which caller filtered what.
    if not evidence.has_checkin_history:
        return REASON_NO_CHECKIN_HISTORY
    if evidence.tolerated_checkin_days < MIN_TOLERATED_DAYS_FOR_RESTORE:
        return REASON_INSUFFICIENT_EVIDENCE
    return None


def _load_unmet(evidence: RehabStageEvidence, injury_state: Mapping[str, Any]) -> str | None:
    if injury_state["severity"] == "severe":
        return REASON_SEVERE_SEVERITY
    if evidence.tolerated_checkin_days < MIN_TOLERATED_DAYS_FOR_LOAD:
        return REASON_INSUFFICIENT_EVIDENCE
    if not evidence.has_session_history:
        return REASON_NO_SESSION_HISTORY
    if evidence.tolerated_sessions < MIN_TOLERATED_SESSIONS_FOR_LOAD:
        return REASON_INSUFFICIENT_EVIDENCE
    return None


def _dynamic_unmet(evidence: RehabStageEvidence, injury_state: Mapping[str, Any]) -> str | None:
    if injury_state["severity"] != "mild":
        return REASON_INSUFFICIENT_EVIDENCE
    if injury_state["reported"] not in IMPROVING_REPORTS:
        return REASON_INSUFFICIENT_EVIDENCE
    if evidence.tolerated_checkin_days < MIN_TOLERATED_DAYS_FOR_DYNAMIC:
        return REASON_INSUFFICIENT_EVIDENCE
    if evidence.tolerated_sessions < MIN_TOLERATED_SESSIONS_FOR_DYNAMIC:
        return REASON_INSUFFICIENT_EVIDENCE
    return None


def _return_unmet(evidence: RehabStageEvidence, injury_state: Mapping[str, Any]) -> str | None:
    if injury_state["reported"] != "resolved":
        return REASON_INSUFFICIENT_EVIDENCE
    if evidence.tolerated_sessions < MIN_TOLERATED_SESSIONS_FOR_RETURN:
        return REASON_INSUFFICIENT_EVIDENCE
    return None


#: The ladder, in order. Each rung is only tested once every rung below it has
#: been met, which is what makes skipping a stage structurally impossible.
_LADDER: tuple[tuple[str, Any, str], ...] = (
    (STAGE_RESTORE, _restore_unmet, REASON_NOT_WORSENING),
    (STAGE_LOAD, _load_unmet, REASON_BASIC_TOLERANCE),
    (STAGE_DYNAMIC, _dynamic_unmet, REASON_LOADING_TOLERANCE),
    (STAGE_RETURN, _return_unmet, REASON_DYNAMIC_TOLERANCE),
)


def _climb(evidence: RehabStageEvidence, injury_state: Mapping[str, Any]) -> tuple[str, list[str]]:
    """Walk the ladder from CALM, stopping at the first unmet requirement."""
    stage = STAGE_CALM
    reasons: list[str] = []
    for candidate, unmet_check, met_reason in _LADDER:
        unmet = unmet_check(evidence, injury_state)
        if unmet is not None:
            reasons.append(unmet)
            break
        stage = candidate
        reasons.append(met_reason)
    return stage, reasons


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def _injury_state(injury: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "severity": _lower(injury.get("severity")) or "moderate",
        "status": _lower(injury.get("status")) or "open",
        "reported": _lower(injury.get("latest_reported_status")) or "ongoing",
    }


def _was_recently_re_reported(
    injury: Mapping[str, Any],
    injury_history: Sequence[Mapping[str, Any]],
    *,
    onset: date | None,
) -> bool:
    """True when a matching injury was cleared shortly before this one opened.

    Identity is the stored ``body_area``, which is what the check-in
    reconciliation itself keys an injury on. Without an onset date there is no
    interval to measure, so the check is skipped rather than guessed.
    """
    if onset is None:
        return False
    body_area = _lower(injury.get("body_area"))
    if not body_area:
        return False
    injury_id = _clean(injury.get("id"))
    for prior in injury_history or ():
        if not isinstance(prior, Mapping):
            continue
        if _clean(prior.get("id")) == injury_id:
            continue
        if _lower(prior.get("body_area")) != body_area:
            continue
        if _lower(prior.get("status")) != "resolved":
            continue
        resolved_at = _parse_day(prior.get("resolved_at")) or _parse_day(prior.get("updated_at"))
        if resolved_at is None:
            continue
        gap = (onset - resolved_at).days
        if 0 <= gap <= RE_REPORT_WINDOW_DAYS:
            return True
    return False


def _confidence(evidence: RehabStageEvidence) -> str:
    if not evidence.has_checkin_history or not evidence.onset_known:
        return CONFIDENCE_LOW
    if not evidence.has_session_history:
        return CONFIDENCE_MODERATE
    return CONFIDENCE_HIGH


def _decide(
    injury: Mapping[str, Any],
    *,
    injury_history: Sequence[Mapping[str, Any]],
    current_checkin: Mapping[str, Any] | None,
    previous_checkins: Sequence[Mapping[str, Any]],
    session_completions: Sequence[Mapping[str, Any]],
) -> RehabStageDecision:
    """Resolve one stage from one snapshot of evidence.

    Shared by the live decision and by the "before today" replay that produces
    ``progressed`` / ``regressed``, so both are computed by identical rules.
    """
    # 1. Skin is not musculoskeletal. The wound-care pathway owns it end to end
    #    and the CALM->RETURN ladder never applies.
    if _is_surface_injury(injury):
        return RehabStageDecision(
            stage=None,
            care_pathway=CARE_TYPE_WOUND_CARE,
            reasons=(REASON_SURFACE_PATHWAY,),
            confidence=CONFIDENCE_HIGH,
        )

    checkins: list[Mapping[str, Any]] = [
        row for row in (current_checkin, *(previous_checkins or ())) if isinstance(row, Mapping)
    ]
    onset = _parse_day(injury.get("created_at"))
    as_of = _row_day(current_checkin) if isinstance(current_checkin, Mapping) else None
    if as_of is None:
        as_of = max((day for day, _row in _relevant_days(checkins, onset=None, as_of=None)), default=None)

    evidence = _gather_evidence(
        onset=onset,
        as_of=as_of,
        checkins=checkins,
        session_completions=session_completions,
    )
    state = _injury_state(injury)
    confidence = _confidence(evidence)

    # 2. Medical gates. These sit ABOVE the ladder: an urgent injury or a
    #    red-flag day pins the stage to the most protective value, and the
    #    existing urgent handling — not this stage — decides what happens next.
    gate_reasons: list[str] = []
    if _is_urgent_injury(injury):
        gate_reasons.append(REASON_URGENT_INJURY_TYPE)
    if isinstance(current_checkin, Mapping) and _active_safety_flags(current_checkin):
        gate_reasons.append(REASON_RED_FLAG_GATE)
    if gate_reasons:
        return RehabStageDecision(
            stage=STAGE_CALM,
            care_pathway=CARE_TYPE_MUSCULOSKELETAL,
            reasons=tuple(gate_reasons),
            confidence=confidence,
            medical_gate=True,
            evidence=evidence,
        )

    # 3. Setbacks cap the ladder. A cap never RAISES a stage — a worsening
    #    report cannot be the reason an injury moves up — so it is applied to
    #    whatever the evidence earns rather than replacing it.
    cap: str | None = None
    setback_reasons: list[str] = []
    if state["reported"] == "worse" or evidence.recent_worsening_days:
        setback_reasons.append(
            REASON_REPORTED_WORSE if state["reported"] == "worse" else REASON_RECENT_WORSENING
        )
        repeated = evidence.recent_worsening_days >= REPEATED_WORSENING_COUNT
        if repeated:
            setback_reasons.append(REASON_REPEATED_WORSENING)
        if state["severity"] == "severe":
            setback_reasons.append(REASON_SEVERE_SEVERITY)
        cap = STAGE_CALM if (repeated or state["severity"] == "severe") else STAGE_RESTORE

    # 4. A freshly re-reported injury starts over. Whatever the cleared flag
    #    earned belonged to that episode, not this one.
    if _was_recently_re_reported(injury, injury_history, onset=onset):
        return RehabStageDecision(
            stage=STAGE_CALM,
            care_pathway=CARE_TYPE_MUSCULOSKELETAL,
            reasons=(REASON_RE_REPORTED, REASON_INSUFFICIENT_EVIDENCE, *setback_reasons),
            confidence=confidence,
            evidence=evidence,
        )

    # 5. Nothing reported since the injury opened: it is new, and new earns
    #    nothing. Silence is never read as tolerance.
    if not evidence.has_checkin_history or evidence.tolerated_checkin_days < MIN_TOLERATED_DAYS_FOR_RESTORE:
        observed_days = (as_of - onset).days if (as_of is not None and onset is not None) else None
        new_reasons: list[str] = []
        if not evidence.onset_known:
            new_reasons.append(REASON_UNKNOWN_ONSET)
        elif observed_days is not None and observed_days <= NEW_INJURY_OBSERVATION_DAYS:
            new_reasons.append(REASON_NEWLY_REPORTED)
        if not evidence.has_checkin_history:
            new_reasons.append(REASON_NO_CHECKIN_HISTORY)
        new_reasons.append(REASON_INSUFFICIENT_EVIDENCE)
        return RehabStageDecision(
            stage=STAGE_CALM,
            care_pathway=CARE_TYPE_MUSCULOSKELETAL,
            reasons=(*new_reasons, *setback_reasons),
            confidence=confidence,
            evidence=evidence,
        )

    # 6. Climb the ladder on evidence alone, then apply any setback cap.
    stage, reasons = _climb(evidence, state)
    if state["reported"] == "resolved" and stage == STAGE_RETURN:
        reasons.append(REASON_REPORTED_RESOLVED)
    if cap is not None:
        if STAGE_RANK[cap] < STAGE_RANK[stage]:
            # The cap, not the ladder, decides — so the rungs the evidence had
            # reached are no longer why the athlete is here. The setback is the
            # whole explanation.
            stage, reasons = cap, list(setback_reasons)
        else:
            # The cap did not bite, but it still contradicts the "not worsening"
            # rung, which must never be reported next to a setback.
            reasons = [
                *setback_reasons,
                *(reason for reason in reasons if reason != REASON_NOT_WORSENING),
            ]
    return RehabStageDecision(
        stage=stage,
        care_pathway=CARE_TYPE_MUSCULOSKELETAL,
        reasons=tuple(reasons),
        confidence=confidence,
        evidence=evidence,
    )


def resolve_rehab_stage(
    injury: Mapping[str, Any],
    injury_history: Sequence[Mapping[str, Any]] = (),
    current_checkin: Mapping[str, Any] | None = None,
    previous_checkins: Sequence[Mapping[str, Any]] = (),
    session_completions: Sequence[Mapping[str, Any]] = (),
) -> RehabStageDecision:
    """Resolve one injury's rehabilitation stage from its own evidence.

    Parameters
    ----------
    injury:
        The ``injury_flags`` row being staged.
    injury_history:
        Other flags for this athlete, used only to notice that a cleared injury
        has been re-reported.
    current_checkin:
        Today's ``today_checkins`` row, when one exists.
    previous_checkins:
        Earlier ``today_checkins`` rows, any order.
    session_completions:
        ``session_completions`` rows, the record of tolerated load.

    There is deliberately **no camp-phase parameter**. GPP/SPP/TAPER describes
    fight preparation, not tissue state, so it cannot reach this decision even by
    accident — the ``phase`` column present on check-in rows is never read.

    Pure and deterministic: the same inputs always produce the same decision, so
    calling it again on a refresh or a retry can never advance a stage.
    """
    if not isinstance(injury, Mapping):
        return RehabStageDecision(
            stage=STAGE_CALM,
            care_pathway=CARE_TYPE_MUSCULOSKELETAL,
            reasons=(REASON_INSUFFICIENT_EVIDENCE,),
        )

    decision = _decide(
        injury,
        injury_history=injury_history,
        current_checkin=current_checkin,
        previous_checkins=previous_checkins,
        session_completions=session_completions,
    )
    if decision.is_wound_care:
        return decision

    # Replay the same rules over the evidence as it stood before today, so the
    # transition is derived rather than stored.
    as_of = _row_day(current_checkin) if isinstance(current_checkin, Mapping) else None
    previous = _decide(
        injury,
        injury_history=injury_history,
        current_checkin=None,
        previous_checkins=[
            row
            for row in (previous_checkins or ())
            if isinstance(row, Mapping) and (as_of is None or _row_day(row) != as_of)
        ],
        session_completions=[
            row
            for row in (session_completions or ())
            if isinstance(row, Mapping) and (as_of is None or (_row_day(row) or as_of) < as_of)
        ],
    )
    if previous.stage is None or decision.stage is None:
        return decision

    before, after = STAGE_RANK[previous.stage], STAGE_RANK[decision.stage]
    return RehabStageDecision(
        stage=decision.stage,
        care_pathway=decision.care_pathway,
        reasons=decision.reasons,
        progressed=after > before,
        regressed=after < before,
        confidence=decision.confidence,
        medical_gate=decision.medical_gate,
        evidence=decision.evidence,
    )


def resolve_rehab_stages(
    injuries: Sequence[Mapping[str, Any]],
    current_checkin: Mapping[str, Any] | None = None,
    previous_checkins: Sequence[Mapping[str, Any]] = (),
    session_completions: Sequence[Mapping[str, Any]] = (),
) -> dict[str, RehabStageDecision]:
    """Resolve every injury independently, keyed by flag id.

    There is no athlete-level stage. A left ankle at ``restore`` and a right
    shoulder at ``load`` are both true at once, and clearing one changes nothing
    about the other: each decision only ever reads its own flag's facts, with the
    shared day-level history applied identically to all of them.
    """
    rows = [row for row in (injuries or ()) if isinstance(row, Mapping)]
    decisions: dict[str, RehabStageDecision] = {}
    for injury in rows:
        flag_id = _clean(injury.get("id"))
        if not flag_id:
            continue
        decisions[flag_id] = resolve_rehab_stage(
            injury,
            injury_history=rows,
            current_checkin=current_checkin,
            previous_checkins=previous_checkins,
            session_completions=session_completions,
        )
    return decisions
