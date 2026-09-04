"""Risk-aware eligibility must agree across planning, placement, and rendering."""
import pytest

from api.structured_plan_sparring_reconcile import _ban_clamped_load, _role_contact_load
from fightcamp.sparring_advisories import build_plan_advisories
from fightcamp.sparring_dose_planner import compute_hard_sparring_plan, hard_sparring_cutoff
from fightcamp.stage2_payload_late_fight import (
    _hard_spar_status_for_countdown_offset, _countdown_weekday_map,
    ensure_declared_coach_combat_spine,
)
from fightcamp.stage2_role_map import _lock_declared_hard_sparring_roles


def _single_day(d_day, **state):
    week = {
        "phase": "TAPER", "stage_key": "taper_sharpen",
        "declared_hard_sparring_days": ["Sunday"],
        "fight_weekday": "sunday", "span_days": 1,
        "projected_days_until_fight_end": d_day,
    }
    # Sunday on this one-day calendar must be the declared date, whatever D-day.
    weekdays = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
    week["fight_weekday"] = weekdays[d_day % 7]
    athlete = {"days_until_fight": 40, "fatigue": "low", **state}
    return week, athlete, compute_hard_sparring_plan(week=week, athlete_snapshot=athlete)[0]


@pytest.mark.parametrize("d_day", [30, 23, 18, 17, 16, 15, 14, 13, 9, 2])
@pytest.mark.parametrize("elevated", [False, True])
def test_scheduled_day_owns_dynamic_cutoff_across_consumers(d_day, elevated):
    _, athlete, entry = _single_day(d_day, fatigue="high" if elevated else "low")
    cutoff = 17 if elevated else 14
    expected = "technical" if d_day <= cutoff else "hard"
    assert entry["d_day"] == d_day
    assert entry["effective_load"] == expected
    assert _ban_clamped_load("hard", d_day, athlete) == expected
    assert _hard_spar_status_for_countdown_offset(d_day, athlete) == (
        "downgrade" if expected == "technical" else "hard_allowed"
    )
    if expected == "technical":
        assert f"d{cutoff}_hard_sparring_ban" in entry["reason_codes"]


@pytest.mark.parametrize("state", [
    {"fatigue": "high"}, {"fatigue": "extreme"},
    {"injuries": ["moderate knee strain"]},
    {"cut_severity_bucket": "high"},
    {"readiness_flags": ["poor_recovery"]},
    {"readiness_flags": ["high_contact_load"]},
    {"readiness_flags": ["aggressive_weight_cut"]},
    {"reduced_contact_requested": True},
])
def test_elevated_signals_bring_cutoff_forward(state):
    assert hard_sparring_cutoff(state) == 17
    assert _single_day(16, **state)[2]["effective_load"] == "technical"


@pytest.mark.parametrize("state", [
    {"injuries": ["concussion last week"]},
    {"injuries": ["got rocked in sparring"]},
    {"parsed_injuries": [{"triage_category": "concussion", "flags": ["suspected_concussion"]}]},
    {"injuries": ["concussion improving"]},
    {"injuries_raw_text": "Doctor said no contact until cleared"},
    {"medical_contact_restriction": True},
    {"readiness_flags": ["neurological_symptoms"]},
])
@pytest.mark.parametrize("d_day", [30, 16, 2])
def test_serious_safety_blocks_contact_regardless_of_countdown(state, d_day):
    week, athlete, entry = _single_day(d_day, **state)
    assert entry["effective_load"] == "none"
    assert entry["status"] == "blocked"
    assert "medical" in entry["coach_note"]
    assert _ban_clamped_load("technical", d_day, athlete) == "none"
    assert _role_contact_load({"downgraded": True}, d_day, athlete) == "none"
    roles, suppressed = _lock_declared_hard_sparring_roles(
        week, [], [], athlete, hard_sparring_plan=[entry],
    )
    assert not any(role["role_key"] == "hard_sparring_day" for role in roles)
    assert suppressed[0]["hard_sparring_status"] == "blocked"
    advice = build_plan_advisories(planning_brief={
        "athlete_model": athlete, "weekly_role_map": {"weeks": [{**week, "hard_sparring_plan": [entry]}]},
    })
    assert advice[0]["title"] == "No contact or sparring"
    assert "technical rounds" not in advice[0]["suggestion"]


def test_negated_concussion_does_not_create_medical_hold():
    assert _single_day(16, injuries=["no concussion symptoms, just tired"])[2]["effective_load"] == "hard"


def test_earlier_injury_downgrade_is_never_restored_by_calendar():
    _, _, entry = _single_day(30, injuries=["knee giving way and worsening"])
    assert entry["effective_load"] != "hard"
    assert "coach_owned_hard_spar_lock" not in entry["reason_codes"]


def test_normal_weekly_pattern_preserves_d16_and_converts_d9():
    loads = [_single_day(day)[2]["effective_load"] for day in [23, 16, 9, 2]]
    assert loads == ["hard", "hard", "technical", "technical"]


def test_existing_reduced_and_technical_entries_are_never_upgraded():
    for d_day in [30, 17, 16, 15]:
        assert _ban_clamped_load("reduced", d_day, {}) == "reduced"
        assert _ban_clamped_load("technical", d_day, {}) == "technical"


def test_rebuilt_spine_does_not_restore_earlier_readiness_reduction():
    athlete = {"days_until_fight": 20, "plan_creation_weekday": "friday",
               "hard_sparring_days": ["Tuesday", "Friday"], "fatigue": "high"}
    roles = ensure_declared_coach_combat_spine([], athlete, _countdown_weekday_map("friday", 20))
    friday = next(role for role in roles if role.get("countdown_offset") == 20)
    assert friday["hard_sparring_status"] == "deload_suggested"
    assert friday["downgraded"] is True


@pytest.mark.parametrize("elevated,expected", [(False, "hard"), (True, "technical")])
def test_unresolved_calendar_uses_active_cutoff(elevated, expected):
    plan = compute_hard_sparring_plan(
        week={"phase": "SPP", "declared_hard_sparring_days": ["Tuesday"], "projected_days_until_fight_end": 15},
        athlete_snapshot={"days_until_fight": 30, "fatigue": "high" if elevated else "low"},
    )
    assert plan[0]["effective_load"] == expected
