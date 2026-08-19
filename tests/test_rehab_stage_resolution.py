"""Rehabilitation stage is resolved from injury evidence, never from camp phase.

The invariant this suite exists to defend: GPP/SPP/TAPER describes where the
athlete is in fight preparation, and cannot move an injury up or down the
CALM -> RESTORE -> LOAD -> DYNAMIC -> RETURN ladder.
"""

from __future__ import annotations

import itertools
from datetime import date, timedelta

import pytest

from api.contracts import rehab_stage as module
from api.contracts.rehab_stage import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MODERATE,
    REASON_INSUFFICIENT_EVIDENCE,
    REASON_NEWLY_REPORTED,
    REASON_NO_CHECKIN_HISTORY,
    REASON_NO_SESSION_HISTORY,
    REASON_RE_REPORTED,
    REASON_RED_FLAG_GATE,
    REASON_REPEATED_WORSENING,
    REASON_REPORTED_WORSE,
    REASON_SEVERE_SEVERITY,
    REASON_SURFACE_PATHWAY,
    REASON_URGENT_INJURY_TYPE,
    STAGE_CALM,
    STAGE_DYNAMIC,
    STAGE_LOAD,
    STAGE_RESTORE,
    STAGE_RETURN,
    resolve_rehab_stage,
    resolve_rehab_stages,
)
from fightcamp.rehab_schema import (
    CARE_TYPE_MUSCULOSKELETAL,
    CARE_TYPE_WOUND_CARE,
    REHAB_STAGES,
)

ONSET = date(2026, 7, 1)
CAMP_PHASES = ("GPP", "SPP", "TAPER")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _injury(**overrides) -> dict:
    """An open, moderate ankle sprain — the ordinary musculoskeletal case."""
    injury = {
        "id": "ankle-1",
        "body_area": "left ankle",
        "description": "ankle sprain",
        "severity": "moderate",
        "status": "open",
        "latest_reported_status": "ongoing",
        "created_at": ONSET.isoformat(),
    }
    injury.update(overrides)
    return injury


def _checkin(day_offset: int, **overrides) -> dict:
    """A ``today_checkins`` row that reports nothing wrong."""
    row = {
        "training_day": (ONSET + timedelta(days=day_offset)).isoformat(),
        "phase": "GPP",
        "active_injury": "stable",
        "pain": "none",
        "previous_session": "normal",
        "recommendation_state": "train_as_planned",
    }
    row.update(overrides)
    return row


def _session(day_offset: int, **overrides) -> dict:
    """A ``session_completions`` row the athlete finished comfortably."""
    row = {
        "training_day": (ONSET + timedelta(days=day_offset)).isoformat(),
        "status": "done",
        "pain_after": 1,
    }
    row.update(overrides)
    return row


def _tolerated(days: int) -> tuple[dict, list[dict]]:
    """``(current, previous)`` check-ins covering ``days`` tolerated days."""
    rows = [_checkin(offset) for offset in range(1, days + 1)]
    return rows[-1], rows[:-1]


def _at_least_load() -> dict:
    """Kwargs whose evidence reaches LOAD, so caps can be shown to bite."""
    current, previous = _tolerated(3)
    return {
        "current_checkin": current,
        "previous_checkins": previous,
        "session_completions": [_session(2)],
    }


def _at_least_dynamic() -> dict:
    current, previous = _tolerated(6)
    return {
        "current_checkin": current,
        "previous_checkins": previous,
        "session_completions": [_session(2), _session(4), _session(6)],
    }


# ---------------------------------------------------------------------------
# One canonical enum
# ---------------------------------------------------------------------------


def test_stage_vocabulary_is_the_canonical_pr1_enum():
    assert module.REHAB_STAGES is REHAB_STAGES
    assert REHAB_STAGES == ("calm", "restore", "load", "dynamic", "return")
    assert (STAGE_CALM, STAGE_RESTORE, STAGE_LOAD, STAGE_DYNAMIC, STAGE_RETURN) == REHAB_STAGES


def test_stage_rank_orders_the_ladder():
    ranks = [module.STAGE_RANK[stage] for stage in REHAB_STAGES]
    assert ranks == sorted(ranks)


# ---------------------------------------------------------------------------
# Camp phase cannot reach the decision
# ---------------------------------------------------------------------------


def test_resolver_takes_no_camp_phase_argument():
    """The strongest form of the invariant: phase is not an input at all."""
    import inspect

    parameters = set(inspect.signature(resolve_rehab_stage).parameters)
    assert not {"phase", "camp_phase", "current_phase"} & parameters


@pytest.mark.parametrize("phase", CAMP_PHASES)
def test_identical_evidence_resolves_the_same_stage_in_every_camp_phase(phase):
    current, previous = _tolerated(3)
    decision = resolve_rehab_stage(
        _injury(),
        current_checkin={**current, "phase": phase},
        previous_checkins=[{**row, "phase": phase} for row in previous],
        session_completions=[_session(2)],
    )
    assert decision.stage == STAGE_LOAD


def test_camp_phase_is_never_read_from_any_input():
    """Every phase permutation across the whole history yields one stage."""
    current, previous = _tolerated(6)
    stages = set()
    for phases in itertools.product(CAMP_PHASES, repeat=3):
        decision = resolve_rehab_stage(
            _injury(phase=phases[0]),
            current_checkin={**current, "phase": phases[1]},
            previous_checkins=[{**row, "phase": phases[2]} for row in previous],
            session_completions=[_session(2), _session(4)],
        )
        stages.add(decision.stage)
    assert len(stages) == 1


def test_changing_gpp_to_spp_does_not_progress_the_stage():
    kwargs = _at_least_load()
    gpp = resolve_rehab_stage(_injury(), **kwargs)
    spp = resolve_rehab_stage(
        _injury(),
        current_checkin={**kwargs["current_checkin"], "phase": "SPP"},
        previous_checkins=[{**row, "phase": "SPP"} for row in kwargs["previous_checkins"]],
        session_completions=kwargs["session_completions"],
    )
    assert spp.stage == gpp.stage
    assert spp.progressed is gpp.progressed


def test_changing_spp_to_taper_does_not_progress_the_stage():
    kwargs = _at_least_load()
    spp = resolve_rehab_stage(
        _injury(),
        current_checkin={**kwargs["current_checkin"], "phase": "SPP"},
        previous_checkins=[{**row, "phase": "SPP"} for row in kwargs["previous_checkins"]],
        session_completions=kwargs["session_completions"],
    )
    taper = resolve_rehab_stage(
        _injury(),
        current_checkin={**kwargs["current_checkin"], "phase": "TAPER"},
        previous_checkins=[{**row, "phase": "TAPER"} for row in kwargs["previous_checkins"]],
        session_completions=kwargs["session_completions"],
    )
    assert taper.stage == spp.stage
    assert taper.progressed is spp.progressed


@pytest.mark.parametrize("phase", CAMP_PHASES)
def test_new_injury_does_not_inherit_a_stage_from_the_camp_phase(phase):
    decision = resolve_rehab_stage(_injury(), current_checkin=_checkin(0, phase=phase))
    assert decision.stage == STAGE_CALM


def test_new_ankle_sprain_during_taper_resolves_to_calm():
    """Fight week does not make a fresh sprain a late-stage rehab problem."""
    decision = resolve_rehab_stage(
        _injury(created_at=ONSET.isoformat()),
        current_checkin=_checkin(0, phase="TAPER"),
    )
    assert decision.stage == STAGE_CALM
    assert REASON_NEWLY_REPORTED in decision.reasons


def test_settled_injury_during_gpp_resolves_beyond_calm():
    """And early camp does not hold a well-tolerated injury back."""
    decision = resolve_rehab_stage(_injury(), **_at_least_load())
    assert decision.stage == STAGE_LOAD
    assert module.STAGE_RANK[decision.stage] > module.STAGE_RANK[STAGE_CALM]


# ---------------------------------------------------------------------------
# Progression is evidence-based
# ---------------------------------------------------------------------------


def test_time_alone_does_not_progress_the_stage():
    """A months-old injury with nothing reported has earned nothing."""
    decision = resolve_rehab_stage(_injury(created_at="2026-01-01"))
    assert decision.stage == STAGE_CALM
    assert REASON_NO_CHECKIN_HISTORY in decision.reasons
    assert REASON_INSUFFICIENT_EVIDENCE in decision.reasons


def test_an_old_unobserved_injury_is_not_described_as_newly_reported():
    decision = resolve_rehab_stage(_injury(created_at="2026-01-01"))
    assert REASON_NEWLY_REPORTED not in decision.reasons


def test_a_checkin_on_the_onset_day_is_not_tolerance_evidence():
    decision = resolve_rehab_stage(_injury(), current_checkin=_checkin(0))
    assert decision.stage == STAGE_CALM
    assert decision.evidence.tolerated_checkin_days == 0


def test_one_improved_checkin_does_not_jump_multiple_stages():
    decision = resolve_rehab_stage(
        _injury(severity="mild", latest_reported_status="improving"),
        current_checkin=_checkin(1),
    )
    assert decision.stage == STAGE_RESTORE
    assert module.STAGE_RANK[decision.stage] == module.STAGE_RANK[STAGE_CALM] + 1


def test_loading_requires_a_tolerated_session_not_just_good_days():
    current, previous = _tolerated(6)
    decision = resolve_rehab_stage(
        _injury(), current_checkin=current, previous_checkins=previous
    )
    assert decision.stage == STAGE_RESTORE
    assert REASON_NO_SESSION_HISTORY in decision.reasons


def test_a_completed_session_without_a_pain_reading_proves_nothing():
    """Missing evidence must never read as successful tolerance."""
    current, previous = _tolerated(3)
    decision = resolve_rehab_stage(
        _injury(),
        current_checkin=current,
        previous_checkins=previous,
        session_completions=[_session(2, pain_after=None)],
    )
    assert decision.stage == STAGE_RESTORE
    assert decision.evidence.tolerated_sessions == 0


def test_a_painful_session_is_not_loading_evidence():
    current, previous = _tolerated(3)
    decision = resolve_rehab_stage(
        _injury(),
        current_checkin=current,
        previous_checkins=previous,
        session_completions=[_session(2, pain_after=8)],
    )
    assert decision.stage == STAGE_RESTORE


def test_a_skipped_session_is_not_loading_evidence():
    current, previous = _tolerated(3)
    decision = resolve_rehab_stage(
        _injury(),
        current_checkin=current,
        previous_checkins=previous,
        session_completions=[_session(2, status="skipped")],
    )
    assert decision.stage == STAGE_RESTORE


def test_dynamic_requires_sustained_loading_and_an_improving_report():
    decision = resolve_rehab_stage(
        _injury(severity="mild", latest_reported_status="improving"), **_at_least_dynamic()
    )
    assert decision.stage == STAGE_DYNAMIC


def test_dynamic_is_not_reached_while_the_injury_is_only_ongoing():
    decision = resolve_rehab_stage(_injury(severity="mild"), **_at_least_dynamic())
    assert decision.stage == STAGE_LOAD


def test_return_requires_the_athlete_to_report_the_injury_resolved():
    current, previous = _tolerated(6)
    sessions = [_session(offset) for offset in (1, 2, 3, 4, 5)]
    decision = resolve_rehab_stage(
        _injury(severity="mild", latest_reported_status="resolved"),
        current_checkin=current,
        previous_checkins=previous,
        session_completions=sessions,
    )
    assert decision.stage == STAGE_RETURN


def test_severe_severity_holds_the_stage_below_loading():
    decision = resolve_rehab_stage(_injury(severity="severe"), **_at_least_load())
    assert decision.stage == STAGE_RESTORE
    assert REASON_SEVERE_SEVERITY in decision.reasons


def test_duplicate_rows_for_one_day_cannot_inflate_the_evidence():
    current, previous = _tolerated(3)
    decision = resolve_rehab_stage(
        _injury(),
        current_checkin=current,
        previous_checkins=[*previous, *previous, *previous],
        session_completions=[_session(2), _session(2), _session(2)],
    )
    assert decision.evidence.tolerated_checkin_days == 3
    assert decision.evidence.tolerated_sessions == 1


def test_evidence_older_than_the_lookback_is_ignored():
    stale = [
        _checkin(-offset - module.EVIDENCE_LOOKBACK_DAYS) for offset in range(1, 10)
    ]
    decision = resolve_rehab_stage(
        _injury(created_at="2026-01-01"),
        current_checkin=_checkin(1),
        previous_checkins=stale,
    )
    assert decision.evidence.tolerated_checkin_days == 1


# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------


def test_a_worsening_report_regresses_the_stage():
    kwargs = _at_least_load()
    settled = resolve_rehab_stage(_injury(), **kwargs)
    worse = resolve_rehab_stage(_injury(latest_reported_status="worse"), **kwargs)

    assert settled.stage == STAGE_LOAD
    assert worse.stage == STAGE_RESTORE
    assert REASON_REPORTED_WORSE in worse.reasons


def test_repeated_worsening_regresses_further_than_a_single_setback():
    current, previous = _tolerated(6)
    single = resolve_rehab_stage(
        _injury(latest_reported_status="worse"),
        current_checkin={**current, "active_injury": "worse"},
        previous_checkins=previous,
        session_completions=[_session(2)],
    )
    repeated = resolve_rehab_stage(
        _injury(latest_reported_status="worse"),
        current_checkin={**current, "active_injury": "worse"},
        previous_checkins=[
            *previous[:-1],
            {**previous[-1], "active_injury": "worse"},
        ],
        session_completions=[_session(2)],
    )

    assert single.stage == STAGE_RESTORE
    assert repeated.stage == STAGE_CALM
    assert REASON_REPEATED_WORSENING in repeated.reasons


def test_a_setback_never_raises_a_stage():
    """The cap is a ceiling; it can only ever pull a stage down."""
    worse_but_new = resolve_rehab_stage(
        _injury(latest_reported_status="worse"), current_checkin=_checkin(0)
    )
    assert worse_but_new.stage == STAGE_CALM


def test_a_setback_is_never_reported_alongside_not_worsening():
    decision = resolve_rehab_stage(_injury(latest_reported_status="worse"), **_at_least_load())
    assert module.REASON_NOT_WORSENING not in decision.reasons


def test_regression_is_reported_as_a_transition():
    current, previous = _tolerated(4)
    decision = resolve_rehab_stage(
        _injury(),
        current_checkin={**current, "active_injury": "worse"},
        previous_checkins=previous,
        session_completions=[_session(2)],
    )
    assert decision.regressed is True
    assert decision.progressed is False


def test_progression_is_reported_as_a_transition():
    current, previous = _tolerated(3)
    decision = resolve_rehab_stage(
        _injury(),
        current_checkin=current,
        previous_checkins=previous,
        session_completions=[_session(2)],
    )
    assert decision.stage == STAGE_LOAD
    assert decision.progressed is True
    assert decision.regressed is False


def test_high_pain_day_regresses_even_without_a_worse_report():
    kwargs = _at_least_load()
    decision = resolve_rehab_stage(
        _injury(),
        current_checkin={**kwargs["current_checkin"], "pain": "high"},
        previous_checkins=kwargs["previous_checkins"],
        session_completions=kwargs["session_completions"],
    )
    assert module.STAGE_RANK[decision.stage] < module.STAGE_RANK[STAGE_LOAD]


def test_a_pull_back_day_counts_as_worsening():
    kwargs = _at_least_load()
    decision = resolve_rehab_stage(
        _injury(),
        current_checkin={**kwargs["current_checkin"], "recommendation_state": "pull_back"},
        previous_checkins=kwargs["previous_checkins"],
        session_completions=kwargs["session_completions"],
    )
    assert decision.stage != STAGE_LOAD


# ---------------------------------------------------------------------------
# Safety precedence
# ---------------------------------------------------------------------------


def test_a_new_red_flag_overrides_the_stage():
    kwargs = _at_least_dynamic()
    decision = resolve_rehab_stage(
        _injury(severity="mild", latest_reported_status="improving"),
        current_checkin={**kwargs["current_checkin"], "neurological_symptoms": True},
        previous_checkins=kwargs["previous_checkins"],
        session_completions=kwargs["session_completions"],
    )
    assert decision.stage == STAGE_CALM
    assert decision.medical_gate is True
    assert REASON_RED_FLAG_GATE in decision.reasons


@pytest.mark.parametrize("flag", module.SAFETY_FLAGS)
def test_every_canonical_safety_flag_gates_the_stage(flag):
    kwargs = _at_least_dynamic()
    decision = resolve_rehab_stage(
        _injury(severity="mild", latest_reported_status="improving"),
        current_checkin={**kwargs["current_checkin"], flag: True},
        previous_checkins=kwargs["previous_checkins"],
        session_completions=kwargs["session_completions"],
    )
    assert decision.stage == STAGE_CALM
    assert decision.medical_gate is True


@pytest.mark.parametrize(
    "description",
    ["suspected fracture", "achilles rupture", "shoulder dislocation", "concussion"],
)
def test_an_urgent_injury_stays_gated_whatever_the_evidence_says(description):
    """Perfect tolerance history cannot talk a red-flag injury into training."""
    decision = resolve_rehab_stage(
        _injury(description=description, severity="mild", latest_reported_status="resolved"),
        **_at_least_dynamic(),
    )
    assert decision.stage == STAGE_CALM
    assert decision.medical_gate is True
    assert REASON_URGENT_INJURY_TYPE in decision.reasons


def test_an_urgent_injury_never_resolves_to_return():
    decision = resolve_rehab_stage(
        _injury(description="suspected fracture", latest_reported_status="resolved"),
        **_at_least_dynamic(),
    )
    assert decision.stage != STAGE_RETURN


def test_an_ordinary_sprain_is_not_mistaken_for_an_urgent_injury():
    decision = resolve_rehab_stage(_injury(), **_at_least_load())
    assert decision.medical_gate is False


# ---------------------------------------------------------------------------
# Surface injuries stay on their own pathway
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("injury_type", ["blister", "graze", "abrasion", "cut", "laceration"])
def test_surface_injuries_are_not_placed_on_the_msk_ladder(injury_type):
    decision = resolve_rehab_stage(
        _injury(description=injury_type, injury_type=injury_type), **_at_least_load()
    )
    assert decision.stage is None
    assert decision.care_pathway == CARE_TYPE_WOUND_CARE
    assert decision.reasons == (REASON_SURFACE_PATHWAY,)
    assert decision.is_wound_care is True


def test_a_musculoskeletal_injury_stays_on_the_msk_pathway():
    decision = resolve_rehab_stage(_injury(), **_at_least_load())
    assert decision.care_pathway == CARE_TYPE_MUSCULOSKELETAL
    assert decision.is_wound_care is False


def test_a_surface_injury_never_reports_a_stage_transition():
    decision = resolve_rehab_stage(
        _injury(description="blister", injury_type="blister"), **_at_least_dynamic()
    )
    assert decision.progressed is False
    assert decision.regressed is False


# ---------------------------------------------------------------------------
# Re-reporting
# ---------------------------------------------------------------------------


def test_a_cleared_then_re_reported_injury_does_not_inherit_progression():
    cleared = _injury(
        id="ankle-0",
        status="resolved",
        resolved_at=(ONSET - timedelta(days=2)).isoformat(),
    )
    decision = resolve_rehab_stage(
        _injury(id="ankle-1"), injury_history=[cleared], **_at_least_load()
    )
    assert decision.stage == STAGE_CALM
    assert REASON_RE_REPORTED in decision.reasons


def test_an_injury_cleared_long_ago_does_not_reset_a_new_one():
    cleared = _injury(
        id="ankle-0",
        status="resolved",
        resolved_at=(ONSET - timedelta(days=module.RE_REPORT_WINDOW_DAYS + 30)).isoformat(),
    )
    decision = resolve_rehab_stage(
        _injury(id="ankle-1"), injury_history=[cleared], **_at_least_load()
    )
    assert decision.stage == STAGE_LOAD


def test_a_cleared_injury_elsewhere_does_not_reset_this_one():
    cleared = _injury(
        id="shoulder-0",
        body_area="right shoulder",
        status="resolved",
        resolved_at=(ONSET - timedelta(days=1)).isoformat(),
    )
    decision = resolve_rehab_stage(
        _injury(id="ankle-1"), injury_history=[cleared], **_at_least_load()
    )
    assert decision.stage == STAGE_LOAD


# ---------------------------------------------------------------------------
# Missing data behaves conservatively
# ---------------------------------------------------------------------------


def test_no_evidence_at_all_resolves_to_the_safest_stage():
    decision = resolve_rehab_stage(_injury())
    assert decision.stage == STAGE_CALM
    assert decision.confidence == CONFIDENCE_LOW


def test_an_unknown_onset_is_reported_rather_than_guessed():
    decision = resolve_rehab_stage(_injury(created_at=""))
    assert decision.stage == STAGE_CALM
    assert module.REASON_UNKNOWN_ONSET in decision.reasons
    assert decision.confidence == CONFIDENCE_LOW


def test_confidence_tracks_the_evidence_actually_available():
    current, previous = _tolerated(3)
    assert resolve_rehab_stage(_injury()).confidence == CONFIDENCE_LOW
    assert (
        resolve_rehab_stage(
            _injury(), current_checkin=current, previous_checkins=previous
        ).confidence
        == CONFIDENCE_MODERATE
    )
    assert resolve_rehab_stage(_injury(), **_at_least_load()).confidence == CONFIDENCE_HIGH


def test_a_non_mapping_injury_fails_closed():
    decision = resolve_rehab_stage(None)  # type: ignore[arg-type]
    assert decision.stage == STAGE_CALM


def test_junk_rows_in_the_history_are_ignored_not_trusted():
    current, previous = _tolerated(3)
    decision = resolve_rehab_stage(
        _injury(),
        current_checkin=current,
        previous_checkins=[*previous, None, "nonsense", {"training_day": "not-a-date"}],
        session_completions=[_session(2), None, 42],
    )
    assert decision.stage == STAGE_LOAD


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_resolution_is_idempotent():
    kwargs = _at_least_load()
    first = resolve_rehab_stage(_injury(), **kwargs)
    for _ in range(5):
        again = resolve_rehab_stage(_injury(), **kwargs)
        assert again.stage == first.stage
        assert again.reasons == first.reasons
        assert again.progressed == first.progressed
        assert again.regressed == first.regressed


def test_re_resolving_never_walks_the_stage_up():
    """There is no stored stage, so a refresh cannot accumulate progression."""
    kwargs = _at_least_load()
    stages = {resolve_rehab_stage(_injury(), **kwargs).stage for _ in range(10)}
    assert stages == {STAGE_LOAD}


# ---------------------------------------------------------------------------
# Multiple injuries
# ---------------------------------------------------------------------------


def test_injuries_resolve_independently():
    ankle = _injury(id="ankle-1", body_area="left ankle", created_at=ONSET.isoformat())
    shoulder = _injury(
        id="shoulder-1",
        body_area="right shoulder",
        description="shoulder strain",
        created_at=(ONSET - timedelta(days=30)).isoformat(),
    )
    kwargs = _at_least_load()
    decisions = resolve_rehab_stages([ankle, shoulder], **kwargs)

    assert decisions["ankle-1"].stage == STAGE_LOAD
    assert decisions["shoulder-1"].stage == STAGE_LOAD
    assert set(decisions) == {"ankle-1", "shoulder-1"}


def test_two_injuries_can_hold_different_stages_at_once():
    settled = _injury(id="shoulder-1", body_area="right shoulder", description="shoulder strain")
    fresh = _injury(
        id="ankle-1",
        body_area="left ankle",
        created_at=(ONSET + timedelta(days=3)).isoformat(),
    )
    kwargs = _at_least_load()
    decisions = resolve_rehab_stages([settled, fresh], **kwargs)

    assert decisions["shoulder-1"].stage == STAGE_LOAD
    assert decisions["ankle-1"].stage == STAGE_CALM
    assert decisions["shoulder-1"].stage != decisions["ankle-1"].stage


def test_clearing_one_injury_does_not_alter_another_stage():
    ankle = _injury(id="ankle-1", body_area="left ankle")
    shoulder = _injury(id="shoulder-1", body_area="right shoulder", description="shoulder strain")
    kwargs = _at_least_load()

    before = resolve_rehab_stages([ankle, shoulder], **kwargs)
    after = resolve_rehab_stages(
        [{**ankle, "status": "resolved", "latest_reported_status": "resolved"}, shoulder],
        **kwargs,
    )
    assert after["shoulder-1"].stage == before["shoulder-1"].stage
    assert after["shoulder-1"].reasons == before["shoulder-1"].reasons


def test_a_worsening_shoulder_does_not_gate_a_separate_ankle():
    ankle = _injury(id="ankle-1", body_area="left ankle")
    shoulder = _injury(
        id="shoulder-1",
        body_area="right shoulder",
        description="shoulder strain",
        latest_reported_status="worse",
    )
    decisions = resolve_rehab_stages([ankle, shoulder], **_at_least_load())

    assert decisions["shoulder-1"].stage == STAGE_RESTORE
    assert decisions["ankle-1"].stage == STAGE_LOAD


def test_a_surface_injury_alongside_an_msk_injury_keeps_both_pathways():
    blister = _injury(id="blister-1", description="blister", injury_type="blister")
    decisions = resolve_rehab_stages([blister, _injury()], **_at_least_load())

    assert decisions["blister-1"].care_pathway == CARE_TYPE_WOUND_CARE
    assert decisions["ankle-1"].care_pathway == CARE_TYPE_MUSCULOSKELETAL


def test_injuries_without_an_id_are_skipped_rather_than_merged():
    decisions = resolve_rehab_stages([_injury(id=""), _injury(id="ankle-1")], **_at_least_load())
    assert set(decisions) == {"ankle-1"}


def test_there_is_no_athlete_level_stage():
    """The API returns a decision per flag id, never one stage for the athlete."""
    decisions = resolve_rehab_stages(
        [_injury(id="a"), _injury(id="b", body_area="right knee", description="knee pain")],
        **_at_least_load(),
    )
    assert isinstance(decisions, dict)
    assert len(decisions) == 2


# ---------------------------------------------------------------------------
# The critical invariant, exhaustively
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("severity", ["mild", "moderate", "severe"])
@pytest.mark.parametrize("reported", ["ongoing", "improving", "worse", "resolved"])
@pytest.mark.parametrize("history_days", [0, 1, 3, 6])
def test_camp_phase_never_changes_the_resolved_stage(severity, reported, history_days):
    """camp_phase x severity x injury_state x history_state, all combinations."""
    if history_days:
        current, previous = _tolerated(history_days)
    else:
        current, previous = None, []
    sessions = [_session(offset) for offset in range(1, history_days + 1)]

    resolved = {
        phase: resolve_rehab_stage(
            _injury(severity=severity, latest_reported_status=reported),
            current_checkin={**current, "phase": phase} if current else None,
            previous_checkins=[{**row, "phase": phase} for row in previous],
            session_completions=sessions,
        )
        for phase in CAMP_PHASES
    }
    stages = {decision.stage for decision in resolved.values()}
    reasons = {decision.reasons for decision in resolved.values()}
    assert len(stages) == 1, f"camp phase changed the stage: {resolved}"
    assert len(reasons) == 1, f"camp phase changed the reasoning: {resolved}"


@pytest.mark.parametrize("phase", CAMP_PHASES)
def test_every_reachable_stage_is_reachable_in_every_camp_phase(phase):
    """No stage is the property of a particular part of the camp."""
    current6, previous6 = _tolerated(6)
    current3, previous3 = _tolerated(3)
    scenarios = {
        STAGE_CALM: (_injury(), {"current_checkin": _checkin(0, phase=phase)}),
        STAGE_RESTORE: (_injury(), {"current_checkin": _checkin(1, phase=phase)}),
        STAGE_LOAD: (
            _injury(),
            {
                "current_checkin": {**current3, "phase": phase},
                "previous_checkins": [{**row, "phase": phase} for row in previous3],
                "session_completions": [_session(2)],
            },
        ),
        STAGE_DYNAMIC: (
            _injury(severity="mild", latest_reported_status="improving"),
            {
                "current_checkin": {**current6, "phase": phase},
                "previous_checkins": [{**row, "phase": phase} for row in previous6],
                "session_completions": [_session(2), _session(4), _session(6)],
            },
        ),
        STAGE_RETURN: (
            _injury(severity="mild", latest_reported_status="resolved"),
            {
                "current_checkin": {**current6, "phase": phase},
                "previous_checkins": [{**row, "phase": phase} for row in previous6],
                "session_completions": [_session(offset) for offset in (1, 2, 3, 4, 5)],
            },
        ),
    }
    for expected, (injury, kwargs) in scenarios.items():
        assert resolve_rehab_stage(injury, **kwargs).stage == expected, expected


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def test_decision_serialises_to_machine_readable_reasons():
    payload = resolve_rehab_stage(_injury(), **_at_least_load()).as_dict()
    assert payload["stage"] == STAGE_LOAD
    assert payload["care_pathway"] == CARE_TYPE_MUSCULOSKELETAL
    assert isinstance(payload["reasons"], list)
    assert all(reason.islower() and " " not in reason for reason in payload["reasons"])
    assert set(payload) == {
        "stage",
        "care_pathway",
        "reasons",
        "progressed",
        "regressed",
        "confidence",
        "medical_gate",
    }


def test_reason_codes_carry_no_athlete_facing_prose():
    decision = resolve_rehab_stage(_injury(), **_at_least_load())
    for reason in decision.reasons:
        assert reason == reason.lower()
        assert " " not in reason
