"""Rehabilitation stage is resolved from THIS injury's evidence, nothing else.

Two invariants this suite exists to defend:

1. GPP/SPP/TAPER describes where the athlete is in fight preparation, and cannot
   move an injury up or down the CALM -> RESTORE -> LOAD -> DYNAMIC -> RETURN
   ladder.
2. Whole-athlete records — daily check-ins and session completions — cannot
   progress a stage. They belong to the athlete's day, not to a body area, so a
   comfortable shoulder session must never vouch for an ankle.
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
    MAX_RESOLVABLE_STAGE,
    REASON_INSUFFICIENT_INJURY_SPECIFIC,
    REASON_NEWLY_REPORTED,
    REASON_NO_FOLLOWUP_REPORT,
    REASON_NOT_WORSENING,
    REASON_RE_REPORTED,
    REASON_RED_FLAG_GATE,
    REASON_REPORTED_WORSE,
    REASON_SEVERE_SEVERITY,
    REASON_SURFACE_PATHWAY,
    REASON_UNKNOWN_ONSET,
    REASON_URGENT_INJURY_TYPE,
    STAGE_CALM,
    STAGE_DYNAMIC,
    STAGE_LOAD,
    STAGE_RESTORE,
    STAGE_RETURN,
    AthleteDayContext,
    InjuryEvidence,
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
    """An open, moderate ankle sprain with no follow-up report yet."""
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


def _followed_up(**overrides) -> dict:
    """The same injury after the athlete reported on it again, as improving.

    ``monitoring`` is the status an ``improving`` report produces, so it is
    per-injury proof that a follow-up happened.
    """
    defaults = {"status": "monitoring", "latest_reported_status": "improving"}
    defaults.update(overrides)
    return _injury(**defaults)


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


def _rich_history(days: int = 10) -> dict:
    """As much whole-athlete "everything is fine" evidence as can be fabricated.

    Every test that asserts global data cannot progress a stage passes this, so
    the assertion is made against the strongest possible false signal.
    """
    checkins = [_checkin(offset) for offset in range(1, days + 1)]
    return {
        "current_checkin": checkins[-1],
        "previous_checkins": checkins[:-1],
        "session_completions": [_session(offset) for offset in range(1, days + 1)],
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
# Whole-athlete evidence cannot progress a stage
# ---------------------------------------------------------------------------


def test_progression_cannot_see_whole_athlete_context():
    """The structural guarantee: ``_progress`` takes injury evidence only."""
    import inspect

    parameters = inspect.signature(module._progress).parameters
    assert list(parameters) == ["injury"]
    annotation = parameters["injury"].annotation
    assert annotation in (InjuryEvidence, "InjuryEvidence")


def test_a_decade_of_perfect_global_history_progresses_nothing():
    """The bug this refactor exists to prevent."""
    decision = resolve_rehab_stage(_injury(), **_rich_history(days=30))
    assert decision.stage == STAGE_CALM
    assert REASON_NO_FOLLOWUP_REPORT in decision.reasons
    assert REASON_INSUFFICIENT_INJURY_SPECIFIC in decision.reasons


def test_completed_pain_free_sessions_are_not_tissue_specific_evidence():
    without = resolve_rehab_stage(_injury())
    with_sessions = resolve_rehab_stage(
        _injury(), session_completions=[_session(offset) for offset in range(1, 20)]
    )
    assert with_sessions.stage == without.stage == STAGE_CALM


def test_good_checkin_days_are_not_tissue_specific_evidence():
    without = resolve_rehab_stage(_injury())
    with_checkins = resolve_rehab_stage(
        _injury(), previous_checkins=[_checkin(offset) for offset in range(1, 20)]
    )
    assert with_checkins.stage == without.stage == STAGE_CALM


@pytest.mark.parametrize("days", [0, 1, 3, 6, 10, 30])
def test_whole_athlete_context_does_not_move_the_stage_at_all(days):
    """Not "may only lower" — cannot move it, in either direction."""
    bare = resolve_rehab_stage(_followed_up())
    with_context = resolve_rehab_stage(_followed_up(), **_rich_history(days=days or 1))
    assert with_context.stage == bare.stage


def test_the_removed_progression_thresholds_are_gone():
    """No count of days or sessions may act as a stage gate."""
    for removed in (
        "MIN_TOLERATED_DAYS_FOR_RESTORE",
        "MIN_TOLERATED_DAYS_FOR_LOAD",
        "MIN_TOLERATED_SESSIONS_FOR_LOAD",
        "MIN_TOLERATED_DAYS_FOR_DYNAMIC",
        "MIN_TOLERATED_SESSIONS_FOR_DYNAMIC",
        "MIN_TOLERATED_SESSIONS_FOR_RETURN",
        "TOLERATED_PAIN_AFTER_BELOW",
    ):
        assert not hasattr(module, removed), removed


# ---------------------------------------------------------------------------
# Where the ladder stops
# ---------------------------------------------------------------------------


def test_the_ladder_stops_at_the_highest_defensible_stage():
    assert MAX_RESOLVABLE_STAGE == STAGE_RESTORE


@pytest.mark.parametrize("stage", [STAGE_LOAD, STAGE_DYNAMIC, STAGE_RETURN])
def test_stages_needing_injury_specific_exposure_are_unreachable(stage):
    """Nothing records what a body area tolerated, so nothing may claim it."""
    candidates = [
        resolve_rehab_stage(_followed_up(), **_rich_history(days=30)),
        resolve_rehab_stage(
            _followed_up(severity="mild", latest_reported_status="resolved", status="resolved"),
            **_rich_history(days=30),
        ),
        resolve_rehab_stage(_followed_up(severity="mild"), **_rich_history(days=30)),
    ]
    assert all(decision.stage != stage for decision in candidates)


def test_stopping_short_always_names_the_missing_injury_specific_evidence():
    decision = resolve_rehab_stage(_followed_up(), **_rich_history())
    assert decision.stage == MAX_RESOLVABLE_STAGE
    assert REASON_INSUFFICIENT_INJURY_SPECIFIC in decision.reasons


def test_a_resolved_injury_still_stops_at_restore():
    decision = resolve_rehab_stage(
        _injury(status="resolved", latest_reported_status="resolved", severity="mild"),
        **_rich_history(days=30),
    )
    assert decision.stage == STAGE_RESTORE
    assert module.REASON_REPORTED_RESOLVED in decision.reasons
    assert REASON_INSUFFICIENT_INJURY_SPECIFIC in decision.reasons


# ---------------------------------------------------------------------------
# Camp phase cannot reach the decision
# ---------------------------------------------------------------------------


def test_resolver_takes_no_camp_phase_argument():
    import inspect

    parameters = set(inspect.signature(resolve_rehab_stage).parameters)
    assert not {"phase", "camp_phase", "current_phase"} & parameters


@pytest.mark.parametrize("phase", CAMP_PHASES)
def test_identical_evidence_resolves_the_same_stage_in_every_camp_phase(phase):
    history = _rich_history()
    decision = resolve_rehab_stage(
        _followed_up(),
        current_checkin={**history["current_checkin"], "phase": phase},
        previous_checkins=[{**row, "phase": phase} for row in history["previous_checkins"]],
        session_completions=history["session_completions"],
    )
    assert decision.stage == STAGE_RESTORE


def test_camp_phase_is_never_read_from_any_input():
    history = _rich_history()
    stages = set()
    for phases in itertools.product(CAMP_PHASES, repeat=3):
        decision = resolve_rehab_stage(
            _followed_up(phase=phases[0]),
            current_checkin={**history["current_checkin"], "phase": phases[1]},
            previous_checkins=[{**row, "phase": phases[2]} for row in history["previous_checkins"]],
            session_completions=history["session_completions"],
        )
        stages.add(decision.stage)
    assert len(stages) == 1


def test_changing_gpp_to_spp_does_not_progress_the_stage():
    gpp = resolve_rehab_stage(_followed_up(), current_checkin=_checkin(3, phase="GPP"))
    spp = resolve_rehab_stage(_followed_up(), current_checkin=_checkin(3, phase="SPP"))
    assert spp.stage == gpp.stage
    assert spp.reasons == gpp.reasons


def test_changing_spp_to_taper_does_not_progress_the_stage():
    spp = resolve_rehab_stage(_followed_up(), current_checkin=_checkin(3, phase="SPP"))
    taper = resolve_rehab_stage(_followed_up(), current_checkin=_checkin(3, phase="TAPER"))
    assert taper.stage == spp.stage
    assert taper.reasons == spp.reasons


@pytest.mark.parametrize("phase", CAMP_PHASES)
def test_new_injury_does_not_inherit_a_stage_from_the_camp_phase(phase):
    decision = resolve_rehab_stage(_injury(), current_checkin=_checkin(0, phase=phase))
    assert decision.stage == STAGE_CALM


def test_new_ankle_sprain_during_taper_resolves_to_calm():
    """Fight week does not make a fresh sprain a late-stage rehab problem."""
    decision = resolve_rehab_stage(_injury(), current_checkin=_checkin(0, phase="TAPER"))
    assert decision.stage == STAGE_CALM
    assert REASON_NEWLY_REPORTED in decision.reasons


def test_settled_injury_during_gpp_resolves_beyond_calm():
    """And early camp does not hold a settled injury back."""
    decision = resolve_rehab_stage(_followed_up(), current_checkin=_checkin(5, phase="GPP"))
    assert decision.stage == STAGE_RESTORE
    assert module.STAGE_RANK[decision.stage] > module.STAGE_RANK[STAGE_CALM]


# ---------------------------------------------------------------------------
# Progression is injury-specific
# ---------------------------------------------------------------------------


def test_time_alone_does_not_progress_the_stage():
    decision = resolve_rehab_stage(_injury(created_at="2026-01-01"))
    assert decision.stage == STAGE_CALM
    assert REASON_NO_FOLLOWUP_REPORT in decision.reasons


def test_an_old_unobserved_injury_is_not_described_as_newly_reported():
    decision = resolve_rehab_stage(
        _injury(created_at="2026-01-01"), current_checkin=_checkin(30)
    )
    assert REASON_NEWLY_REPORTED not in decision.reasons


def test_a_followup_report_is_what_reaches_restore():
    assert resolve_rehab_stage(_injury()).stage == STAGE_CALM
    assert resolve_rehab_stage(_followed_up()).stage == STAGE_RESTORE


def test_a_later_write_on_the_flag_counts_as_a_followup():
    decision = resolve_rehab_stage(
        _injury(updated_at=(ONSET + timedelta(days=3)).isoformat())
    )
    assert decision.stage == STAGE_RESTORE
    assert REASON_NOT_WORSENING in decision.reasons


def test_a_same_day_edit_is_not_a_followup():
    decision = resolve_rehab_stage(_injury(updated_at=ONSET.isoformat()))
    assert decision.stage == STAGE_CALM
    assert REASON_NO_FOLLOWUP_REPORT in decision.reasons


def test_one_improved_checkin_does_not_jump_multiple_stages():
    decision = resolve_rehab_stage(_followed_up(), current_checkin=_checkin(1))
    assert module.STAGE_RANK[decision.stage] == module.STAGE_RANK[STAGE_CALM] + 1


def test_severe_severity_holds_the_stage_at_calm():
    decision = resolve_rehab_stage(_followed_up(severity="severe"), **_rich_history())
    assert decision.stage == STAGE_CALM
    assert REASON_SEVERE_SEVERITY in decision.reasons


# ---------------------------------------------------------------------------
# Regression is injury-attributable too
# ---------------------------------------------------------------------------


def test_a_worsening_report_regresses_the_stage():
    """The injury's own report is what regresses it."""
    settled = resolve_rehab_stage(_followed_up())
    worse = resolve_rehab_stage(_followed_up(latest_reported_status="worse"))

    assert settled.stage == STAGE_RESTORE
    assert worse.stage == STAGE_CALM
    assert REASON_REPORTED_WORSE in worse.reasons
    assert worse.regressed is True


def test_severe_severity_regresses_the_stage():
    decision = resolve_rehab_stage(_followed_up(severity="severe"))
    assert decision.stage == STAGE_CALM
    assert REASON_SEVERE_SEVERITY in decision.reasons


def test_a_setback_never_raises_a_stage():
    worse_but_new = resolve_rehab_stage(
        _injury(latest_reported_status="worse"), current_checkin=_checkin(0)
    )
    assert worse_but_new.stage == STAGE_CALM


def test_a_setback_is_never_reported_alongside_not_worsening():
    decision = resolve_rehab_stage(_followed_up(latest_reported_status="worse"))
    assert REASON_NOT_WORSENING not in decision.reasons
    assert REASON_REPORTED_WORSE in decision.reasons


def test_a_followed_up_injury_held_at_calm_is_not_called_newly_reported():
    decision = resolve_rehab_stage(_followed_up(severity="severe"))
    assert REASON_NEWLY_REPORTED not in decision.reasons


# --- whole-athlete signals must not regress anything -----------------------


def _global_setback(signal: dict) -> dict:
    """Three consecutive whole-athlete bad days, however they are expressed."""
    return {
        "current_checkin": _checkin(5, **signal),
        "previous_checkins": [_checkin(4, **signal), _checkin(3, **signal)],
    }


@pytest.mark.parametrize(
    "signal",
    [
        {"active_injury": "worse"},
        {"pain": "high"},
        {"recommendation_state": "pull_back"},
    ],
    ids=["repeated_worsening", "high_pain", "pull_back"],
)
def test_whole_athlete_setbacks_do_not_regress_a_settled_injury(signal):
    """A bad day for the athlete is not a bad day for every tissue they have."""
    settled = resolve_rehab_stage(_followed_up())
    with_setback = resolve_rehab_stage(_followed_up(), **_global_setback(signal))

    assert settled.stage == STAGE_RESTORE
    assert with_setback.stage == STAGE_RESTORE
    assert with_setback.regressed is False


def test_high_session_pain_does_not_regress_a_settled_injury():
    decision = resolve_rehab_stage(
        _followed_up(),
        current_checkin=_checkin(5),
        session_completions=[
            _session(4, pain_after=module.SETBACK_PAIN_AFTER_AT_LEAST),
            _session(5, pain_after=module.SETBACK_PAIN_AFTER_AT_LEAST),
        ],
    )
    assert decision.stage == STAGE_RESTORE
    assert decision.regressed is False


@pytest.mark.parametrize("days", [1, 3, 10, 30])
def test_no_amount_of_whole_athlete_worsening_moves_a_stage(days):
    """Symmetry with the progression guarantee: global data moves nothing."""
    bad = [_checkin(offset, active_injury="worse", pain="high") for offset in range(1, days + 1)]
    decision = resolve_rehab_stage(
        _followed_up(), current_checkin=bad[-1], previous_checkins=bad[:-1]
    )
    assert decision.stage == resolve_rehab_stage(_followed_up()).stage


def test_whole_athlete_counts_are_reported_but_not_applied():
    """The day counts stay visible for explainability; they just do not bite."""
    decision = resolve_rehab_stage(_followed_up(), **_global_setback({"active_injury": "worse"}))
    assert decision.evidence.athlete.worsening_days == 3
    assert decision.evidence.athlete.recent_worsening_days == 3
    assert decision.stage == STAGE_RESTORE


def test_duplicate_rows_for_one_day_cannot_inflate_the_day_counts():
    worse_day = _checkin(4, active_injury="worse")
    decision = resolve_rehab_stage(
        _followed_up(),
        current_checkin=worse_day,
        previous_checkins=[worse_day, worse_day, worse_day],
    )
    assert decision.evidence.athlete.recent_worsening_days == 1


# ---------------------------------------------------------------------------
# Safety precedence
# ---------------------------------------------------------------------------


def test_a_new_red_flag_gates_training_without_rewriting_the_tissue_stage():
    """A red-flag day blocks training; it does not mean the ankle went backwards."""
    ungated = resolve_rehab_stage(_followed_up())
    gated = resolve_rehab_stage(
        _followed_up(), current_checkin=_checkin(4, neurological_symptoms=True)
    )
    assert gated.medical_gate is True
    assert REASON_RED_FLAG_GATE in gated.reasons
    assert gated.stage == ungated.stage
    assert gated.regressed is False


@pytest.mark.parametrize("flag", module.SAFETY_FLAGS)
def test_every_canonical_safety_flag_raises_the_medical_gate(flag):
    decision = resolve_rehab_stage(_followed_up(), current_checkin=_checkin(4, **{flag: True}))
    assert decision.medical_gate is True
    assert decision.stage == STAGE_RESTORE


def test_an_urgent_injury_type_does_pin_its_own_stage():
    """Attributable to this flag's own text, so it may hold this tissue."""
    decision = resolve_rehab_stage(_followed_up(description="suspected fracture"))
    assert decision.stage == STAGE_CALM
    assert decision.medical_gate is True
    assert REASON_URGENT_INJURY_TYPE in decision.reasons


@pytest.mark.parametrize(
    "description",
    ["suspected fracture", "achilles rupture", "shoulder dislocation", "concussion"],
)
def test_an_urgent_injury_stays_gated_whatever_the_evidence_says(description):
    decision = resolve_rehab_stage(
        _followed_up(description=description, severity="mild", latest_reported_status="resolved"),
        **_rich_history(days=30),
    )
    assert decision.stage == STAGE_CALM
    assert decision.medical_gate is True
    assert REASON_URGENT_INJURY_TYPE in decision.reasons


def test_an_ordinary_sprain_is_not_mistaken_for_an_urgent_injury():
    assert resolve_rehab_stage(_followed_up()).medical_gate is False


# ---------------------------------------------------------------------------
# Surface injuries stay on their own pathway
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("injury_type", ["blister", "graze", "abrasion", "cut", "laceration"])
def test_surface_injuries_are_not_placed_on_the_msk_ladder(injury_type):
    decision = resolve_rehab_stage(
        _injury(description=injury_type, injury_type=injury_type), **_rich_history()
    )
    assert decision.stage is None
    assert decision.care_pathway == CARE_TYPE_WOUND_CARE
    assert decision.reasons == (REASON_SURFACE_PATHWAY,)
    assert decision.is_wound_care is True


def test_a_musculoskeletal_injury_stays_on_the_msk_pathway():
    decision = resolve_rehab_stage(_followed_up())
    assert decision.care_pathway == CARE_TYPE_MUSCULOSKELETAL
    assert decision.is_wound_care is False


def test_a_surface_injury_never_reports_a_stage_transition():
    decision = resolve_rehab_stage(
        _injury(description="blister", injury_type="blister"), **_rich_history()
    )
    assert decision.progressed is False
    assert decision.regressed is False


# ---------------------------------------------------------------------------
# Re-reporting
# ---------------------------------------------------------------------------


def test_a_cleared_then_re_reported_injury_does_not_inherit_progression():
    cleared = _injury(
        id="ankle-0", status="resolved", resolved_at=(ONSET - timedelta(days=2)).isoformat()
    )
    decision = resolve_rehab_stage(
        _followed_up(id="ankle-1"), injury_history=[cleared], **_rich_history()
    )
    assert decision.stage == STAGE_CALM
    assert REASON_RE_REPORTED in decision.reasons


def test_an_injury_cleared_long_ago_does_not_reset_a_new_one():
    cleared = _injury(
        id="ankle-0",
        status="resolved",
        resolved_at=(ONSET - timedelta(days=module.RE_REPORT_WINDOW_DAYS + 30)).isoformat(),
    )
    decision = resolve_rehab_stage(_followed_up(id="ankle-1"), injury_history=[cleared])
    assert decision.stage == STAGE_RESTORE


def test_a_cleared_injury_elsewhere_does_not_reset_this_one():
    cleared = _injury(
        id="shoulder-0",
        body_area="right shoulder",
        status="resolved",
        resolved_at=(ONSET - timedelta(days=1)).isoformat(),
    )
    decision = resolve_rehab_stage(_followed_up(id="ankle-1"), injury_history=[cleared])
    assert decision.stage == STAGE_RESTORE


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
    assert REASON_UNKNOWN_ONSET in decision.reasons
    assert decision.confidence == CONFIDENCE_LOW


def test_confidence_tracks_what_the_injury_record_itself_says():
    assert resolve_rehab_stage(_injury()).confidence == CONFIDENCE_LOW
    assert (
        resolve_rehab_stage(
            _injury(updated_at=(ONSET + timedelta(days=3)).isoformat())
        ).confidence
        == CONFIDENCE_MODERATE
    )
    assert resolve_rehab_stage(_followed_up()).confidence == CONFIDENCE_HIGH


def test_confidence_does_not_rise_with_whole_athlete_history():
    bare = resolve_rehab_stage(_injury())
    padded = resolve_rehab_stage(_injury(), **_rich_history(days=30))
    assert padded.confidence == bare.confidence


def test_a_non_mapping_injury_fails_closed():
    decision = resolve_rehab_stage(None)  # type: ignore[arg-type]
    assert decision.stage == STAGE_CALM
    assert REASON_INSUFFICIENT_INJURY_SPECIFIC in decision.reasons


def test_junk_rows_in_the_history_are_ignored_not_trusted():
    decision = resolve_rehab_stage(
        _followed_up(),
        current_checkin=_checkin(3),
        previous_checkins=[None, "nonsense", {"training_day": "not-a-date"}],
        session_completions=[None, 42],
    )
    assert decision.stage == STAGE_RESTORE


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_resolution_is_idempotent():
    history = _rich_history()
    first = resolve_rehab_stage(_followed_up(), **history)
    for _ in range(5):
        again = resolve_rehab_stage(_followed_up(), **history)
        assert again.stage == first.stage
        assert again.reasons == first.reasons
        assert again.progressed == first.progressed
        assert again.regressed == first.regressed


def test_re_resolving_never_walks_the_stage_up():
    history = _rich_history()
    stages = {resolve_rehab_stage(_followed_up(), **history).stage for _ in range(10)}
    assert stages == {STAGE_RESTORE}


# ---------------------------------------------------------------------------
# Concurrent injuries are isolated
# ---------------------------------------------------------------------------


def _ankle(**overrides) -> dict:
    return _injury(id="ankle-1", body_area="left ankle", description="ankle sprain", **overrides)


def _shoulder(**overrides) -> dict:
    defaults = {
        "id": "shoulder-1",
        "body_area": "right shoulder",
        "description": "shoulder strain",
    }
    defaults.update(overrides)
    return _injury(**defaults)


def test_evidence_for_one_body_area_cannot_progress_another():
    """The isolation this refactor is for: a settled shoulder is not an ankle."""
    settled_shoulder = _shoulder(status="monitoring", latest_reported_status="improving")
    fresh_ankle = _ankle()
    decisions = resolve_rehab_stages([settled_shoulder, fresh_ankle], **_rich_history(days=30))

    assert decisions["shoulder-1"].stage == STAGE_RESTORE
    assert decisions["ankle-1"].stage == STAGE_CALM
    assert REASON_NO_FOLLOWUP_REPORT in decisions["ankle-1"].reasons


def test_adding_a_settled_injury_never_moves_an_unsettled_one():
    alone = resolve_rehab_stages([_ankle()], **_rich_history())
    together = resolve_rehab_stages(
        [_ankle(), _shoulder(status="monitoring", latest_reported_status="improving")],
        **_rich_history(),
    )
    assert together["ankle-1"].stage == alone["ankle-1"].stage
    assert together["ankle-1"].reasons == alone["ankle-1"].reasons


def test_a_shoulder_follow_up_does_not_become_ankle_evidence():
    """Follow-up state is read off each flag, never off a sibling."""
    decisions = resolve_rehab_stages(
        [
            _shoulder(status="monitoring", latest_reported_status="improving"),
            _ankle(status="open", latest_reported_status="ongoing"),
        ]
    )
    assert decisions["shoulder-1"].evidence.injury.followup_reported is True
    assert decisions["ankle-1"].evidence.injury.followup_reported is False


def test_many_settled_injuries_cannot_out_vote_one_unsettled_injury():
    settled = [
        _injury(
            id=f"settled-{index}",
            body_area=f"region {index}",
            description="strain",
            status="monitoring",
            latest_reported_status="improving",
        )
        for index in range(6)
    ]
    decisions = resolve_rehab_stages([*settled, _ankle()], **_rich_history(days=30))
    assert decisions["ankle-1"].stage == STAGE_CALM
    assert all(decisions[f"settled-{index}"].stage == STAGE_RESTORE for index in range(6))


def test_two_injuries_can_hold_different_stages_at_once():
    decisions = resolve_rehab_stages(
        [_shoulder(status="monitoring", latest_reported_status="improving"), _ankle()],
        **_rich_history(),
    )
    assert decisions["shoulder-1"].stage != decisions["ankle-1"].stage


def test_clearing_one_injury_does_not_alter_another_stage():
    ankle, shoulder = _ankle(), _shoulder(status="monitoring", latest_reported_status="improving")
    history = _rich_history()

    before = resolve_rehab_stages([ankle, shoulder], **history)
    after = resolve_rehab_stages(
        [{**ankle, "status": "resolved", "latest_reported_status": "resolved"}, shoulder],
        **history,
    )
    assert after["shoulder-1"].stage == before["shoulder-1"].stage
    assert after["shoulder-1"].reasons == before["shoulder-1"].reasons


def test_a_worsening_shoulder_does_not_gate_a_separate_settled_ankle():
    decisions = resolve_rehab_stages(
        [
            _shoulder(status="monitoring", latest_reported_status="worse"),
            _ankle(status="monitoring", latest_reported_status="improving"),
        ]
    )
    assert decisions["shoulder-1"].stage == STAGE_CALM
    assert decisions["ankle-1"].stage == STAGE_RESTORE


# --- cross-injury regression isolation -------------------------------------


def _settled_ankle() -> dict:
    return _ankle(status="monitoring", latest_reported_status="improving")


def test_repeated_shoulder_worsening_cannot_regress_a_settled_ankle():
    """The headline case: one tissue flaring must not drag another backwards."""
    flaring_shoulder = _shoulder(status="monitoring", latest_reported_status="worse")
    worsening_days = {
        "current_checkin": _checkin(5, active_injury="worse"),
        "previous_checkins": [
            _checkin(4, active_injury="worse"),
            _checkin(3, active_injury="worse"),
        ],
    }
    decisions = resolve_rehab_stages([flaring_shoulder, _settled_ankle()], **worsening_days)

    assert decisions["shoulder-1"].stage == STAGE_CALM
    assert REASON_REPORTED_WORSE in decisions["shoulder-1"].reasons
    assert decisions["ankle-1"].stage == STAGE_RESTORE
    assert decisions["ankle-1"].regressed is False
    assert REASON_REPORTED_WORSE not in decisions["ankle-1"].reasons


def test_global_high_pain_cannot_regress_a_settled_ankle():
    alone = resolve_rehab_stages([_settled_ankle()])
    with_pain = resolve_rehab_stages(
        [_shoulder(status="monitoring", latest_reported_status="worse"), _settled_ankle()],
        current_checkin=_checkin(5, pain="high"),
        previous_checkins=[_checkin(4, pain="high"), _checkin(3, pain="high")],
    )
    assert with_pain["ankle-1"].stage == alone["ankle-1"].stage == STAGE_RESTORE
    assert with_pain["ankle-1"].regressed is False


def test_global_pull_back_cannot_regress_a_settled_ankle():
    alone = resolve_rehab_stages([_settled_ankle()])
    with_pull_back = resolve_rehab_stages(
        [_shoulder(status="monitoring", latest_reported_status="worse"), _settled_ankle()],
        current_checkin=_checkin(5, recommendation_state="pull_back"),
        previous_checkins=[
            _checkin(4, recommendation_state="pull_back"),
            _checkin(3, recommendation_state="pull_back"),
        ],
    )
    assert with_pull_back["ankle-1"].stage == alone["ankle-1"].stage == STAGE_RESTORE
    assert with_pull_back["ankle-1"].regressed is False


def test_global_high_session_pain_cannot_regress_a_settled_ankle():
    decisions = resolve_rehab_stages(
        [_shoulder(status="monitoring", latest_reported_status="worse"), _settled_ankle()],
        current_checkin=_checkin(5),
        session_completions=[
            _session(4, pain_after=module.SETBACK_PAIN_AFTER_AT_LEAST),
            _session(5, pain_after=module.SETBACK_PAIN_AFTER_AT_LEAST),
        ],
    )
    assert decisions["ankle-1"].stage == STAGE_RESTORE
    assert decisions["ankle-1"].regressed is False


def test_many_flaring_injuries_cannot_out_vote_one_settled_injury():
    flaring = [
        _injury(
            id=f"flaring-{index}",
            body_area=f"region {index}",
            description="strain",
            status="monitoring",
            latest_reported_status="worse",
        )
        for index in range(6)
    ]
    decisions = resolve_rehab_stages(
        [*flaring, _settled_ankle()],
        current_checkin=_checkin(5, active_injury="worse", pain="high"),
        previous_checkins=[_checkin(4, active_injury="worse", pain="high")],
    )
    assert all(decisions[f"flaring-{index}"].stage == STAGE_CALM for index in range(6))
    assert decisions["ankle-1"].stage == STAGE_RESTORE


def test_an_urgent_shoulder_does_not_gate_or_regress_a_separate_ankle():
    """Urgent-injury text belongs to its own flag, not to the athlete."""
    decisions = resolve_rehab_stages(
        [_shoulder(description="suspected fracture"), _settled_ankle()]
    )
    assert decisions["shoulder-1"].stage == STAGE_CALM
    assert decisions["shoulder-1"].medical_gate is True
    assert decisions["ankle-1"].stage == STAGE_RESTORE
    assert decisions["ankle-1"].medical_gate is False


def test_resolving_an_injury_alone_or_alongside_others_gives_the_same_stage():
    """No sibling, settled or flaring, may change another injury's decision."""
    ankle = _settled_ankle()
    alone = resolve_rehab_stage(ankle)
    crowd = [
        _shoulder(status="monitoring", latest_reported_status="worse"),
        _injury(id="knee-1", body_area="left knee", description="knee pain", severity="severe"),
        _injury(id="wrist-1", body_area="right wrist", description="suspected fracture"),
        ankle,
    ]
    together = resolve_rehab_stages(crowd, **_rich_history())

    assert together["ankle-1"].stage == alone.stage
    assert together["ankle-1"].reasons == alone.reasons
    assert together["ankle-1"].medical_gate == alone.medical_gate


def test_a_surface_injury_alongside_an_msk_injury_keeps_both_pathways():
    blister = _injury(id="blister-1", description="blister", injury_type="blister")
    decisions = resolve_rehab_stages([blister, _ankle()], **_rich_history())

    assert decisions["blister-1"].care_pathway == CARE_TYPE_WOUND_CARE
    assert decisions["ankle-1"].care_pathway == CARE_TYPE_MUSCULOSKELETAL


def test_injuries_without_an_id_are_skipped_rather_than_merged():
    decisions = resolve_rehab_stages([_injury(id=""), _ankle()], **_rich_history())
    assert set(decisions) == {"ankle-1"}


def test_there_is_no_athlete_level_stage():
    decisions = resolve_rehab_stages([_ankle(), _shoulder()], **_rich_history())
    assert isinstance(decisions, dict)
    assert len(decisions) == 2


def test_a_shared_red_flag_gates_every_injury_without_moving_any_stage():
    """The gate is athlete-wide; the stages stay whatever each record supports."""
    injuries = [_shoulder(status="monitoring", latest_reported_status="improving"), _ankle()]
    ungated = resolve_rehab_stages(injuries)
    gated = resolve_rehab_stages(injuries, current_checkin=_checkin(4, neurological_symptoms=True))

    assert all(decision.medical_gate for decision in gated.values())
    assert {key: value.stage for key, value in gated.items()} == {
        key: value.stage for key, value in ungated.items()
    }


# ---------------------------------------------------------------------------
# The critical invariant, exhaustively
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("severity", ["mild", "moderate", "severe"])
@pytest.mark.parametrize("reported", ["ongoing", "improving", "worse", "resolved"])
@pytest.mark.parametrize("history_days", [0, 1, 3, 6])
def test_camp_phase_never_changes_the_resolved_stage(severity, reported, history_days):
    """camp_phase x severity x injury_state x history_state, all combinations."""
    if history_days:
        history = _rich_history(days=history_days)
        current, previous = history["current_checkin"], history["previous_checkins"]
        sessions = history["session_completions"]
    else:
        current, previous, sessions = None, [], []

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
    scenarios = {
        STAGE_CALM: (_injury(), {"current_checkin": _checkin(0, phase=phase)}),
        STAGE_RESTORE: (_followed_up(), {"current_checkin": _checkin(3, phase=phase)}),
    }
    for expected, (injury, kwargs) in scenarios.items():
        assert resolve_rehab_stage(injury, **kwargs).stage == expected, expected


# ---------------------------------------------------------------------------
# Evidence surface
# ---------------------------------------------------------------------------


def test_evidence_keeps_the_two_kinds_visibly_apart():
    decision = resolve_rehab_stage(_followed_up(), **_rich_history())
    assert isinstance(decision.evidence.injury, InjuryEvidence)
    assert isinstance(decision.evidence.athlete, AthleteDayContext)


def test_injury_evidence_carries_no_whole_athlete_counts():
    fields = set(InjuryEvidence.__dataclass_fields__)
    assert not {"worsening_days", "recent_worsening_days", "reported_days", "red_flags"} & fields


def test_athlete_context_carries_no_injury_identity():
    fields = set(AthleteDayContext.__dataclass_fields__)
    assert not {"reported", "status", "severity", "followup_reported"} & fields


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def test_decision_serialises_to_machine_readable_reasons():
    payload = resolve_rehab_stage(_followed_up(), **_rich_history()).as_dict()
    assert payload["stage"] == STAGE_RESTORE
    assert payload["care_pathway"] == CARE_TYPE_MUSCULOSKELETAL
    assert isinstance(payload["reasons"], list)
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
    decision = resolve_rehab_stage(_followed_up(), **_rich_history())
    for reason in decision.reasons:
        assert reason == reason.lower()
        assert " " not in reason


def test_reason_codes_are_never_repeated():
    decision = resolve_rehab_stage(
        _followed_up(latest_reported_status="worse"),
        current_checkin=_checkin(4, active_injury="worse"),
        previous_checkins=[_checkin(3, active_injury="worse")],
    )
    assert len(decision.reasons) == len(set(decision.reasons))
