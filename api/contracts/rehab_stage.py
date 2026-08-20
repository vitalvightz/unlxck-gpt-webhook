"""Per-injury rehabilitation stage resolution (PR2).

Rehabilitation stage answers *"what can this injured tissue currently
tolerate?"*. Fight-camp phase (GPP / SPP / TAPER) answers *"where is the athlete
in fight preparation?"*. They are independent dimensions, and this module owns
the first one.

The separation matters because the two used to be conflated. An ankle sprained
in fight week is a brand-new injury that has earned nothing, yet TAPER reads as
"late in the plan"; a six-week-old ankle may have settled, yet GPP reads as
"early". Camp phase is therefore **not an argument to this resolver** — it cannot
be, so it cannot advance or regress a stage. It stays where it belongs:
modifying dose and fatigue exposure downstream.

Stage vocabulary is :data:`fightcamp.rehab_schema.REHAB_STAGES` — the canonical
PR1 enum, not a second one::

    calm -> restore -> load -> dynamic -> return

Two kinds of evidence, and only one of them may progress
-------------------------------------------------------
Everything is derived from records that already exist; this module defines no
new representation of pain, severity, injury status or history. But those
records fall into two categories that must never be confused:

**Injury-specific** — facts about *this* injury, from its own ``injury_flags``
row: ``severity``, ``status``, ``latest_reported_status``, onset
(``created_at``), whether it has been reported on again since onset, and whether
a matching flag was cleared and re-reported. Only these may move a stage *up*.

**Whole-athlete** — ``today_checkins`` (``active_injury``, ``pain``, the
canonical :data:`~api.contracts.checkin_decision.SAFETY_FLAGS`,
``recommendation_state``) and ``session_completions`` (``status``,
``pain_after``). None of it can say *which* injury it belongs to. **It moves no
stage, in either direction.**

Both halves of that matter. A comfortable shoulder session is not evidence that
an ankle tolerated load — and a flaring shoulder is not evidence that the ankle
went backwards. Stage is tissue state, so every movement in it, up or down,
needs evidence attributable to that tissue.

The one thing whole-athlete context does is raise ``medical_gate`` on a
red-flag day. That blocks training and routes medical handling without claiming
anything about a particular body area, so an unrelated injury keeps the stage
its own record supports.

The boundary is structural, not conventional: the stage is computed by
:func:`_progress`, which takes an :class:`InjuryEvidence` and has no access to
:class:`AthleteDayContext` at all — the same trick that keeps camp phase out.

Where the ladder stops
----------------------
``load``, ``dynamic`` and ``return`` each assert that the injured tissue
tolerated something — progressive load, then speed and impact, then near
unrestricted sport. **No such record exists.** Nothing in the system ties an
exposure to a body area. So the ladder stops at :data:`MAX_RESOLVABLE_STAGE` and
says why, with :data:`REASON_INSUFFICIENT_INJURY_SPECIFIC`. Inventing day counts
or session counts to bridge that gap would be writing rehabilitation criteria,
which is not this PR's job.

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
is still ``null``, so rehab selection stays exactly as it is until PR3 migrates
the bank content and PR4 makes stage-aware scoring authoritative.
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
from .injury_signal import HIGH_PAIN_AFTER
from .readiness_message import classify_injury_surface

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

STAGE_CALM, STAGE_RESTORE, STAGE_LOAD, STAGE_DYNAMIC, STAGE_RETURN = REHAB_STAGES

#: Rank of each stage, so "regressed" and "progressed" are orderings rather than
#: string comparisons. Sourced from the canonical enum's own order.
STAGE_RANK: dict[str, int] = {stage: index for index, stage in enumerate(REHAB_STAGES)}

#: The highest stage the current record can justify. Everything above it asserts
#: injury-specific exposure tolerance, which nothing in the system records — see
#: the module docstring. PR4 raises this once that evidence exists.
MAX_RESOLVABLE_STAGE = STAGE_RESTORE

#: Reported day-states that mean this injury is not getting worse.
NON_WORSENING_REPORTS: frozenset[str] = frozenset({"ongoing", "improving", "resolved"})

#: Reported day-states that are this injury's own statement that it is settling.
IMPROVING_REPORTS: frozenset[str] = frozenset({"improving", "resolved"})

#: Flag statuses that only an ``improving`` / ``resolved`` report can produce
#: (see ``injury_checkin._FLAG_STATUS_BY_REPORT``), which makes them per-injury
#: proof that the athlete filed a follow-up on this specific injury.
FOLLOWUP_FLAG_STATUSES: frozenset[str] = frozenset({"monitoring", "resolved"})

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
REASON_NOT_WORSENING = "symptoms_not_worsening"
REASON_FOLLOWUP_REPORT = "injury_specific_followup_report"
REASON_NO_FOLLOWUP_REPORT = "no_injury_specific_followup_report"
REASON_REPORTED_RESOLVED = "injury_reported_resolved"
REASON_UNKNOWN_ONSET = "injury_onset_unknown"

#: The ladder's ceiling reason: this injury has no record of what *it* tolerated.
REASON_INSUFFICIENT_INJURY_SPECIFIC = "insufficient_injury_specific_progression_evidence"


# ---------------------------------------------------------------------------
# Windows
#
# No number below moves a stage. The stage comes entirely from the injury's own
# record (see ``_progress``), in both directions, and has no thresholds at all.
# These bound the reported day counts and the re-report identity check, so the
# worst a wrong value does is mis-describe a decision or start a re-reported
# injury over slightly early.
# ---------------------------------------------------------------------------

#: A logged session at or above the project's existing "high" post-session pain
#: mark reads as a bad day. Reused from ``injury_signal``, not a new number.
SETBACK_PAIN_AFTER_AT_LEAST = HIGH_PAIN_AFTER

#: How many of the most recent reported days are inspected for a setback.
RECENT_WORSENING_WINDOW_DAYS = 3

#: An injury is only described as "newly reported" while this few days have
#: passed since onset. Beyond it, an injury with no follow-up is unobserved
#: rather than new, and says so.
NEW_INJURY_OBSERVATION_DAYS = 1

#: A flag cleared this recently and then re-reported starts from scratch.
RE_REPORT_WINDOW_DAYS = 14

#: How far back day-level context is read at all, so a months-old bad patch
#: cannot be reassembled from sporadic check-ins.
EVIDENCE_LOOKBACK_DAYS = 90


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InjuryEvidence:
    """Facts about ONE injury, read from its own flag record.

    This is the only evidence permitted to progress a stage, because it is the
    only evidence that is actually about this injury.
    """

    reported: str = "ongoing"
    status: str = "open"
    severity: str = "moderate"
    onset_known: bool = False
    #: The athlete filed a further report on THIS injury after it opened.
    followup_reported: bool = False
    #: A matching flag was cleared shortly before this one opened.
    recently_re_reported: bool = False
    #: Days between onset and the most recent reported day, when both are known.
    observed_days: int | None = None

    @property
    def is_worsening(self) -> bool:
        return self.reported == "worse"

    @property
    def is_improving(self) -> bool:
        return self.reported in IMPROVING_REPORTS


@dataclass(frozen=True)
class AthleteDayContext:
    """Whole-athlete day context. Medical gating and explainability ONLY.

    Nothing here knows which injury it belongs to: ``today_checkins`` carries one
    ``active_injury`` answer for the whole day, and a ``session_completions``
    pain reading belongs to a session, not a body area.

    So it moves no stage, in either direction. Letting it progress one would let
    a comfortable body part vouch for another; letting it regress one would let
    a flaring shoulder drag a settled ankle backwards. Only :attr:`red_flags`
    is acted on, and only to raise ``medical_gate`` — which blocks training
    without claiming anything about a particular tissue.

    The day counts are carried for explainability: they are reported on the
    decision and never applied to it. It is never passed to :func:`_progress`.
    """

    red_flags: tuple[str, ...] = ()
    worsening_days: int = 0
    recent_worsening_days: int = 0
    reported_days: int = 0

    @property
    def has_red_flag(self) -> bool:
        return bool(self.red_flags)


@dataclass(frozen=True)
class RehabStageEvidence:
    """Both halves of what a decision was built from, kept visibly apart."""

    injury: InjuryEvidence = field(default_factory=InjuryEvidence)
    athlete: AthleteDayContext = field(default_factory=AthleteDayContext)


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


def _dedupe(reasons: Sequence[str]) -> list[str]:
    """First occurrence wins, so a code cannot be reported twice."""
    return list(dict.fromkeys(reasons))


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


def _active_safety_flags(row: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(flag for flag in SAFETY_FLAGS if bool(row.get(flag)))


_URGENT_TOKEN_PATTERNS: tuple[re.Pattern[str], ...] | None = None


def _urgent_token_patterns() -> tuple[re.Pattern[str], ...]:
    """Word-boundary matchers for the canonical urgent injury vocabulary.

    Built from :func:`fightcamp.injury_taxonomy.derive_urgent_injury_tokens`, so
    this module holds no urgent-injury list of its own. Boundaries matter: a bare
    substring test lets short tokens fire inside unrelated words.
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
# Injury-specific evidence
# ---------------------------------------------------------------------------


def _followup_reported(injury: Mapping[str, Any], *, onset: date | None) -> bool:
    """True when the athlete filed a further report on THIS injury after onset.

    Two per-injury signals, either of which is sufficient:

    * ``status`` is ``monitoring`` or ``resolved`` — only an ``improving`` or
      ``resolved`` report produces those, so the flag has been spoken about
      again since it opened;
    * the flag was written on a later day than it was created.

    Deliberately conservative. Same-day edits do not count, and a flag nobody
    has touched since onset counts for nothing at all: silence is not tolerance.
    """
    if _lower(injury.get("status")) in FOLLOWUP_FLAG_STATUSES:
        return True
    updated = _parse_day(injury.get("updated_at"))
    return bool(onset is not None and updated is not None and updated > onset)


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
        if 0 <= (onset - resolved_at).days <= RE_REPORT_WINDOW_DAYS:
            return True
    return False


def _injury_evidence(
    injury: Mapping[str, Any],
    injury_history: Sequence[Mapping[str, Any]],
    *,
    onset: date | None,
    as_of: date | None,
) -> InjuryEvidence:
    observed_days = (as_of - onset).days if (as_of is not None and onset is not None) else None
    return InjuryEvidence(
        reported=_lower(injury.get("latest_reported_status")) or "ongoing",
        status=_lower(injury.get("status")) or "open",
        severity=_lower(injury.get("severity")) or "moderate",
        onset_known=onset is not None,
        followup_reported=_followup_reported(injury, onset=onset),
        recently_re_reported=_was_recently_re_reported(injury, injury_history, onset=onset),
        observed_days=observed_days,
    )


# ---------------------------------------------------------------------------
# Whole-athlete day context (regression and gating only)
# ---------------------------------------------------------------------------


def _checkin_day_is_worsening(row: Mapping[str, Any]) -> bool:
    """True when a day reads as things going backwards for the athlete.

    Deliberately broad: this only ever drives *regression*, where
    over-including is the safe error.
    """
    if _lower(row.get("active_injury")) == "worse":
        return True
    if _lower(row.get("pain")) == "high":
        return True
    if _lower(row.get("recommendation_state") or row.get("decision")) == "pull_back":
        return True
    return bool(_active_safety_flags(row))


def _session_day_is_worsening(row: Mapping[str, Any]) -> bool:
    """True when a logged session came back at high post-session pain.

    Only a *completed* session with an explicitly high reading counts. A missing
    reading is not a bad day — and, just as importantly, a good reading is not a
    good one for any particular injury, which is why nothing here can progress.
    """
    if _lower(row.get("status")) not in COMPLETED_SESSION_STATUSES:
        return False
    pain = _pain_after(row.get("pain_after"))
    return pain is not None and pain >= SETBACK_PAIN_AFTER_AT_LEAST


def _worsening_days(
    checkins: Sequence[Mapping[str, Any]],
    session_completions: Sequence[Mapping[str, Any]],
    *,
    as_of: date | None,
) -> tuple[set[date], set[date]]:
    """Return ``(reported_days, worsening_days)`` inside the lookback window.

    One entry per day, so several rows for one day cannot inflate a count.
    """
    reported: set[date] = set()
    worsening: set[date] = set()
    sources = (
        (checkins, _checkin_day_is_worsening),
        (session_completions, _session_day_is_worsening),
    )
    for rows, is_worsening in sources:
        for row in rows or ():
            if not isinstance(row, Mapping):
                continue
            day = _row_day(row)
            if day is None:
                continue
            if as_of is not None:
                delta = (as_of - day).days
                if delta < 0 or delta > EVIDENCE_LOOKBACK_DAYS:
                    continue
            reported.add(day)
            if is_worsening(row):
                worsening.add(day)
    return reported, worsening


def _athlete_context(
    *,
    current_checkin: Mapping[str, Any] | None,
    checkins: Sequence[Mapping[str, Any]],
    session_completions: Sequence[Mapping[str, Any]],
    as_of: date | None,
) -> AthleteDayContext:
    reported, worsening = _worsening_days(checkins, session_completions, as_of=as_of)
    recent = sorted(reported, reverse=True)[:RECENT_WORSENING_WINDOW_DAYS]
    recent_worsening = sum(
        1
        for day in recent
        if day in worsening
        and (as_of is None or (as_of - day).days <= RECENT_WORSENING_WINDOW_DAYS)
    )
    red_flags = (
        _active_safety_flags(current_checkin) if isinstance(current_checkin, Mapping) else ()
    )
    return AthleteDayContext(
        red_flags=red_flags,
        worsening_days=len(worsening),
        recent_worsening_days=recent_worsening,
        reported_days=len(reported),
    )


# ---------------------------------------------------------------------------
# The ladder
# ---------------------------------------------------------------------------


def _restore_unmet(injury: InjuryEvidence) -> str | None:
    """RESTORE: this injury itself has been reported on, and is not worsening.

    That is a genuinely injury-specific statement — the athlete looked at this
    body area again and did not say it had got worse. A severity the athlete
    themselves called ``severe`` holds at CALM regardless: holding an injury
    more protectively is the safe direction, and the severity is per-injury.
    """
    if injury.reported not in NON_WORSENING_REPORTS:
        return REASON_REPORTED_WORSE
    if injury.severity == "severe":
        return REASON_SEVERE_SEVERITY
    if not injury.followup_reported:
        return REASON_NO_FOLLOWUP_REPORT
    return None


def _needs_injury_specific_exposure(_injury: InjuryEvidence) -> str | None:
    """LOAD, DYNAMIC and RETURN all require what PR2 cannot supply.

    Each asserts that *this injured tissue* tolerated something: progressive
    load, then speed and impact, then near unrestricted sport. The only
    tolerance the system records is whole-athlete — a session completion and a
    pain reading that belong to the athlete's day, not to one ankle. Spending it
    here would let a comfortable shoulder session progress an ankle, which is
    exactly the false evidence this ladder must not manufacture.

    So every rung above :data:`MAX_RESOLVABLE_STAGE` reports the same honest
    gap. PR4 replaces this with a real per-injury exposure record.
    """
    return REASON_INSUFFICIENT_INJURY_SPECIFIC


#: The ladder, in order. Each rung is only tested once every rung below it has
#: been met, which is what makes skipping a stage structurally impossible.
_LADDER: tuple[tuple[str, Any, str], ...] = (
    (STAGE_RESTORE, _restore_unmet, REASON_NOT_WORSENING),
    (STAGE_LOAD, _needs_injury_specific_exposure, REASON_FOLLOWUP_REPORT),
    (STAGE_DYNAMIC, _needs_injury_specific_exposure, REASON_FOLLOWUP_REPORT),
    (STAGE_RETURN, _needs_injury_specific_exposure, REASON_FOLLOWUP_REPORT),
)


def _progress(injury: InjuryEvidence) -> tuple[str, list[str]]:
    """Climb the ladder from CALM using ONLY this injury's own evidence.

    Takes an :class:`InjuryEvidence` and nothing else. Whole-athlete context is
    not a parameter, so — exactly as with camp phase — it cannot contribute to a
    progression even by mistake.

    There are no count thresholds here on purpose. A number of "good days" or
    "good sessions" required before an injury may be loaded is a rehabilitation
    criterion, and PR2 does not write those.
    """
    stage = STAGE_CALM
    reasons: list[str] = []
    for candidate, unmet_check, met_reason in _LADDER:
        unmet = unmet_check(injury)
        if unmet is not None:
            reasons.append(unmet)
            # Every stop that is not a reported setback is an evidence gap, and
            # says so in one consistent code whatever rung it happened on.
            if unmet != REASON_REPORTED_WORSE:
                reasons.append(REASON_INSUFFICIENT_INJURY_SPECIFIC)
            break
        stage = candidate
        reasons.append(met_reason)
    return stage, _dedupe(reasons)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def _confidence(injury: InjuryEvidence) -> str:
    """How much this injury's OWN record says — not how far up the ladder it got."""
    if not injury.onset_known or not injury.followup_reported:
        return CONFIDENCE_LOW
    return CONFIDENCE_HIGH if injury.is_improving else CONFIDENCE_MODERATE


def _transition(injury: InjuryEvidence, stage: str) -> tuple[bool, bool]:
    """Whether this injury has moved off its starting point, and which way.

    ``injury_flags`` keeps a single overwritten ``latest_reported_status``, so
    there is no per-injury timeline and "changed since yesterday" is simply not
    derivable. What IS derivable, and attributable to this injury alone, is
    movement relative to where every injury starts: CALM, with nothing reported
    since onset.

    So a follow-up report that lifted this injury off CALM reads as progression,
    and a follow-up that left it there — because it came back ``worse``, or the
    severity is ``severe`` — reads as regression. An injury nobody has reported
    on again has not moved at all.
    """
    if not injury.followup_reported:
        return False, False
    progressed = STAGE_RANK[stage] > STAGE_RANK[STAGE_CALM]
    return progressed, not progressed


def _decide(
    injury: Mapping[str, Any],
    *,
    injury_history: Sequence[Mapping[str, Any]],
    current_checkin: Mapping[str, Any] | None,
    previous_checkins: Sequence[Mapping[str, Any]],
    session_completions: Sequence[Mapping[str, Any]],
) -> RehabStageDecision:
    """Resolve one injury's stage from its own record, gated by today's context."""
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
        days = [day for day in (_row_day(row) for row in checkins) if day is not None]
        as_of = max(days, default=None)

    injury_evidence = _injury_evidence(injury, injury_history, onset=onset, as_of=as_of)
    athlete = _athlete_context(
        current_checkin=current_checkin,
        checkins=checkins,
        session_completions=session_completions,
        as_of=as_of,
    )
    evidence = RehabStageEvidence(injury=injury_evidence, athlete=athlete)
    confidence = _confidence(injury_evidence)

    def _decision(
        stage: str | None,
        reasons: Sequence[str],
        *,
        medical_gate: bool = False,
        progressed: bool = False,
        regressed: bool = False,
    ) -> RehabStageDecision:
        return RehabStageDecision(
            stage=stage,
            care_pathway=CARE_TYPE_MUSCULOSKELETAL,
            reasons=tuple(_dedupe(reasons)),
            progressed=progressed,
            regressed=regressed,
            confidence=confidence,
            medical_gate=medical_gate,
            evidence=evidence,
        )

    # 2. Medical gates, and the difference between them.
    #
    #    An URGENT injury type is read off THIS flag's own text, so it is
    #    attributable to this tissue and pins this injury to the most protective
    #    stage.
    #
    #    A red-flag check-in is whole-athlete. It gates training and medical
    #    handling — that is what ``medical_gate`` is for — but it says nothing
    #    about any particular body area, so it must NOT rewrite the stage of an
    #    unrelated injury. Sprained ankle plus a headache today is a gated day,
    #    not an ankle that suddenly went backwards.
    if _is_urgent_injury(injury):
        return _decision(STAGE_CALM, [REASON_URGENT_INJURY_TYPE], medical_gate=True)

    gate_reasons: list[str] = []
    medical_gate = False
    if athlete.has_red_flag:
        gate_reasons.append(REASON_RED_FLAG_GATE)
        medical_gate = True

    # 3. A freshly re-reported injury starts over. Whatever the cleared flag
    #    earned belonged to that episode, not this one.
    if injury_evidence.recently_re_reported:
        return _decision(
            STAGE_CALM,
            [REASON_RE_REPORTED, REASON_INSUFFICIENT_INJURY_SPECIFIC, *gate_reasons],
            medical_gate=medical_gate,
        )

    # 4. The stage itself comes from this injury's record and nothing else —
    #    upward and downward alike. A ``worse`` report, or a ``severe``
    #    severity, holds it at CALM from inside ``_progress``; no whole-athlete
    #    signal participates.
    stage, reasons = _progress(injury_evidence)

    if stage == STAGE_CALM and not injury_evidence.is_worsening:
        # Name *why* nothing has been earned yet, rather than only the rung.
        # An injury that has been followed up is never "newly reported", however
        # protectively it is being held.
        if not injury_evidence.onset_known:
            reasons.insert(0, REASON_UNKNOWN_ONSET)
        elif not injury_evidence.followup_reported and (
            injury_evidence.observed_days is None
            or injury_evidence.observed_days <= NEW_INJURY_OBSERVATION_DAYS
        ):
            reasons.insert(0, REASON_NEWLY_REPORTED)
    if stage == MAX_RESOLVABLE_STAGE and injury_evidence.reported == "resolved":
        reasons.append(REASON_REPORTED_RESOLVED)

    progressed, regressed = _transition(injury_evidence, stage)
    return _decision(
        stage,
        [*gate_reasons, *reasons],
        medical_gate=medical_gate,
        progressed=progressed,
        regressed=regressed,
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
        The ``injury_flags`` row being staged. The only source of progression
        evidence.
    injury_history:
        Other flags for this athlete, used only to notice that a cleared injury
        has been re-reported.
    current_checkin, previous_checkins, session_completions:
        Whole-athlete context. Used for medical gating and for regression only —
        never to progress a stage, because none of it can say which injury it
        belongs to.

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
            reasons=(REASON_INSUFFICIENT_INJURY_SPECIFIC,),
        )

    return _decide(
        injury,
        injury_history=injury_history,
        current_checkin=current_checkin,
        previous_checkins=previous_checkins,
        session_completions=session_completions,
    )


def resolve_rehab_stages(
    injuries: Sequence[Mapping[str, Any]],
    current_checkin: Mapping[str, Any] | None = None,
    previous_checkins: Sequence[Mapping[str, Any]] = (),
    session_completions: Sequence[Mapping[str, Any]] = (),
) -> dict[str, RehabStageDecision]:
    """Resolve every injury independently, keyed by flag id.

    There is no athlete-level stage. A left ankle at ``restore`` and a right
    shoulder at ``calm`` are both true at once, and clearing one changes nothing
    about the other.

    The whole-athlete context passed here is shared, and deliberately so: it can
    only gate or lower a stage, never raise one, so sharing it cannot let one
    body area's good day vouch for another's.
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
