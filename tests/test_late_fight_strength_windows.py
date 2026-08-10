"""Late-fight strength/taper window rebalance.

Covers the D-21 -> D-1 progression for the exercises whose late-window
eligibility was rebalanced so suitable movements stay available deeper into
camp while the downstream prescription layer keeps shrinking the dose.

Principle under test:
* Bank/window metadata decides whether an exercise *may* exist in a countdown
  window (``late_windows`` + governance/cost metadata).
* The prescription/countdown layer decides *how much* is performed and keeps
  reducing it as the fight approaches.

These tests read the real ``data/exercise_bank.json`` through
``strength.get_exercise_bank`` so the runtime schema-safety marking (governance
+ cost metadata) is applied exactly as in production.
"""

from __future__ import annotations

import re

import pytest

from fightcamp import conditioning, strength
from fightcamp.strength import (
    _evaluate_strength_late_window,
    _exercise_fatigue_cost,
    _strength_metadata_score_adjustment,
    classify_strength_item,
)
from fightcamp.late_selector_windows import (
    D1,
    D4_TO_D2,
    D6_TO_D5,
    D7,
    D13_TO_D8,
    D21_TO_D14,
)


@pytest.fixture(autouse=True)
def _reset_bank_cache():
    strength._exercise_bank_cache = None
    yield
    strength._exercise_bank_cache = None


def _bank_by_name() -> dict:
    return {entry["name"]: entry for entry in strength.get_exercise_bank()}


def _named(name: str) -> dict:
    item = _bank_by_name().get(name)
    assert item is not None, f"missing exercise bank item: {name}"
    return item


def _eval(name: str, window: str, *, days_until_fight=None, cut_bucket: str = "none") -> dict:
    return _evaluate_strength_late_window(
        _named(name),
        window=window,
        days_until_fight=days_until_fight,
        cut_bucket=cut_bucket,
    )


def _not_blocked(name: str, window: str, *, days_until_fight=None, cut_bucket: str = "none") -> bool:
    return not _eval(name, window, days_until_fight=days_until_fight, cut_bucket=cut_bucket)["blocked"]


def _blocked(name: str, window: str, *, days_until_fight=None, cut_bucket: str = "none") -> bool:
    return _eval(name, window, days_until_fight=days_until_fight, cut_bucket=cut_bucket)["blocked"]


# --- 1. Trap Bar Deadlift: extended into D13-D8, held out of D7+ --------------

def test_trap_bar_deadlift_enters_d13_to_d8_but_not_d7():
    item = _named("Trap Bar Deadlift")
    assert item["late_windows"] == ["d21_to_d14", "d13_to_d8"]

    assert _not_blocked("Trap Bar Deadlift", D21_TO_D14, days_until_fight=17)
    assert _not_blocked("Trap Bar Deadlift", D13_TO_D8, days_until_fight=10)

    # D-7 and everything inside the final week stays blocked (window mismatch).
    assert _blocked("Trap Bar Deadlift", D7, days_until_fight=7)
    assert _blocked("Trap Bar Deadlift", D6_TO_D5, days_until_fight=6)
    assert _blocked("Trap Bar Deadlift", D4_TO_D2, days_until_fight=4)
    assert _blocked("Trap Bar Deadlift", D1, days_until_fight=1)


def test_trap_bar_deadlift_stays_a_governed_familiar_retention_anchor():
    item = _named("Trap Bar Deadlift")
    # Genuine strength-retention anchor: governance is complete so it can
    # legitimately satisfy the maximal-strength-maintenance role.
    assert item["support_only"] is False
    assert item["meaningful_stress"] is True
    assert item["real_strength_maintenance"] is True
    assert "maximal_strength_maintenance" in item["tags"]
    # A foundational hinge is not gated behind the "requires familiarity" late
    # block that guards technically demanding late-introduced movements.
    assert "familiarity_required" not in item["tags"]


# --- 2. Trap-Bar Pin Pull Isometric: extended through D7 ----------------------

def test_trap_bar_pin_pull_isometric_enters_d7():
    item = _named("Trap-Bar Pin Pull Isometric")
    assert set(item["late_windows"]) == {"d21_to_d14", "d13_to_d8", "d7"}

    assert _not_blocked("Trap-Bar Pin Pull Isometric", D7, days_until_fight=7)
    # Note/window contradiction resolved: the note permits very-low-dose D-7 and
    # the window now allows it, while D-6/D-5 and closer stay out.
    assert _blocked("Trap-Bar Pin Pull Isometric", D6_TO_D5, days_until_fight=6)
    assert _blocked("Trap-Bar Pin Pull Isometric", D1, days_until_fight=1)


def test_trap_bar_pin_pull_note_matches_windows():
    item = _named("Trap-Bar Pin Pull Isometric")
    note = str(item.get("notes") or "")
    # Note references D-7 use; the window list must make that possible.
    assert "D-7" in note
    assert "d7" in item["late_windows"]


# --- 3 & 4. Med-ball punch throws reach D4-D2 --------------------------------

@pytest.mark.parametrize(
    "name",
    ["Half-Kneeling Medicine-Ball Punch Throw", "Seated Medicine-Ball Punch Throw"],
)
def test_medicine_ball_punch_throw_enters_d4_to_d2(name):
    item = _named(name)
    assert "d4_to_d2" in item["late_windows"]

    # Eligible at D-4 and D-2 (the ends of the window)...
    assert _not_blocked(name, D4_TO_D2, days_until_fight=4)
    assert _not_blocked(name, D4_TO_D2, days_until_fight=2)
    # ...but the preserved D-3 throw lockout still fires inside the window.
    assert _blocked(name, D4_TO_D2, days_until_fight=3)
    # D-1 is never a lifting/throwing day.
    assert _blocked(name, D1, days_until_fight=1)


# --- 5. Staggered-stance throw: continuous late-window eligibility ------------

def test_staggered_stance_throw_is_continuous_through_the_taper():
    item = _named("Staggered-Stance Medicine-Ball Punch Throw")
    assert item["late_windows"] == ["d13_to_d8", "d7", "d6_to_d5", "d4_to_d2"]

    # No gap: every window from D13-D8 inward is eligible.
    assert _not_blocked("Staggered-Stance Medicine-Ball Punch Throw", D13_TO_D8, days_until_fight=10)
    assert _not_blocked("Staggered-Stance Medicine-Ball Punch Throw", D7, days_until_fight=7)
    assert _not_blocked("Staggered-Stance Medicine-Ball Punch Throw", D6_TO_D5, days_until_fight=6)
    assert _not_blocked("Staggered-Stance Medicine-Ball Punch Throw", D4_TO_D2, days_until_fight=4)


# --- 6. Punch-Specific Max Isometric Hold survives through D6-D5, not later ---

def test_punch_specific_iso_hold_survives_through_d6_d5_only():
    item = _named("Punch-Specific Max Isometric Hold")
    assert item["late_windows"] == ["d21_to_d14", "d13_to_d8", "d7", "d6_to_d5"]

    assert _not_blocked("Punch-Specific Max Isometric Hold", D7, days_until_fight=7)
    assert _not_blocked("Punch-Specific Max Isometric Hold", D6_TO_D5, days_until_fight=6)
    # Held out of D-4..D-1 (window mismatch), per the intended progression.
    assert _blocked("Punch-Specific Max Isometric Hold", D4_TO_D2, days_until_fight=4)
    assert _blocked("Punch-Specific Max Isometric Hold", D1, days_until_fight=1)


def test_punch_specific_iso_hold_movement_cost_is_not_falsely_high():
    # An isometric hold is not a high recovery-cost movement; the misleading
    # "high" movement_cost tag (which hard-blocks every D13-and-under window)
    # was corrected so the exercise can actually occupy its declared windows.
    item = _named("Punch-Specific Max Isometric Hold")
    assert item["movement_cost"] != "high"
    assert item["eccentric_cost"] == "low"
    assert item["landing_cost"] == "none"


# --- 7. High-eccentric / high-soreness traditional lifts stay blocked ---------

@pytest.mark.parametrize(
    "name",
    [
        "Romanian Deadlift (RDL)",
        "Heavy RDL → Broad Jump",
        "Tempo Split Squat (4-0-1)",
        "Back Squat",
        "Front Squat",
        "Bulgarian Split Squat",
        "Cluster Set Trap Bar Deadlift",
    ],
)
def test_high_cost_traditional_lifts_remain_blocked_late(name):
    item = _bank_by_name().get(name)
    if item is None:
        pytest.skip(f"{name} not present in bank")
    # None of these are late-eligible; they carry no late_windows.
    assert not item.get("late_windows")
    for window, day in ((D13_TO_D8, 10), (D7, 7), (D4_TO_D2, 4)):
        assert _eval(name, window, days_until_fight=day)["blocked"] is True


# --- 8. Cut / fatigue states still remove otherwise late-eligible work --------

def test_high_cut_hard_blocks_a_late_eligible_isometric_in_the_tight_window():
    # Isometric Mid-Thigh Pull is D-7 eligible, but its cut allowance stops at
    # "moderate"; a high cut removes it in the tight D-7 window.
    assert _not_blocked("Isometric Mid-Thigh Pull", D7, days_until_fight=7, cut_bucket="none")

    high_cut = _eval("Isometric Mid-Thigh Pull", D7, days_until_fight=7, cut_bucket="high")
    assert high_cut["blocked"] is True
    assert "late_strength_block_cut_bucket_mismatch" in high_cut["block_codes"]


def test_high_fatigue_penalizes_a_late_eligible_strength_anchor():
    item = _named("Trap Bar Deadlift")
    low = _strength_metadata_score_adjustment(item, fatigue="low", cut_bucket="none")[0]
    high = _strength_metadata_score_adjustment(item, fatigue="high", cut_bucket="none")[0]
    # A moderate-CNS / high-soreness retention lift is deprioritised under high
    # fatigue rather than treated identically to a fresh state.
    assert high < low
    assert high < 0.0


# --- 9. Later-window prescription volume decreases ----------------------------

def _active_cap_upper_minutes(days_until_fight: int) -> int:
    caps = conditioning._late_fight_dosage_caps(days_until_fight)
    match = re.search(r"cap\s+\d+-(\d+)\s+min active", caps)
    assert match, f"no active cap found for D-{days_until_fight}: {caps}"
    return int(match.group(1))


def test_prescription_volume_shrinks_across_the_final_week():
    # The existing countdown dosage caps (not a new taper system) tighten the
    # active-minute ceiling monotonically as the fight approaches.
    sequence = [_active_cap_upper_minutes(d) for d in (10, 7, 6, 5, 4, 3, 2, 1)]
    assert sequence == sorted(sequence, reverse=True)
    assert sequence[0] > sequence[-1]
    # Concretely: a later window is not identical to an earlier one.
    assert _active_cap_upper_minutes(2) < _active_cap_upper_minutes(10)
    assert _active_cap_upper_minutes(5) < _active_cap_upper_minutes(10)


def test_role_morph_softens_late_strength_to_low_volume_neural_maintenance():
    from fightcamp.late_camp_role_morph import apply_late_camp_role_morph

    week = {
        "session_roles": [
            {"role_key": "transfer_strength_day", "category": "strength", "scheduled_day_hint": "monday"}
        ],
        "calendar_days": [{"weekday": "monday", "d_day": 10}],
    }
    apply_late_camp_role_morph({"weeks": [week]})
    role = week["session_roles"][0]
    assert role["rpe_cap"] == "6-7"
    assert role["set_cap"] == "2-3 sets"
    assert "neural maintenance" in role["selection_rule"].lower()


# --- 10. Low-eccentric never buys a zero-fatigue bypass -----------------------

@pytest.mark.parametrize(
    "name",
    [
        "Trap Bar Deadlift",
        "Isometric Mid-Thigh Pull",
        "Trap-Bar Pin Pull Isometric",
        "Punch-Specific Max Isometric Hold",
        "Half-Kneeling Medicine-Ball Punch Throw",
        "Suitcase Carry Holds",
    ],
)
def test_low_eccentric_does_not_zero_out_fatigue_cost(name):
    item = _named(name)
    quality_profile = classify_strength_item(item)
    fatigue_cost = _exercise_fatigue_cost(item, quality_profile)
    # Being low-eccentric / low-impact never drives the recovery-cost proxy to
    # zero (or negative); scoring restraint still applies.
    assert fatigue_cost > 0.0


# --- 11. Final-week / D-1 safety still holds ----------------------------------

@pytest.mark.parametrize(
    "name",
    [
        "Trap Bar Deadlift",
        "Isometric Mid-Thigh Pull",
        "Trap-Bar Pin Pull Isometric",
        "Punch-Specific Max Isometric Hold",
        "Landmine Split-Stance Punch Press",
        "Half-Kneeling Medicine-Ball Punch Throw",
        "Seated Medicine-Ball Punch Throw",
        "Staggered-Stance Medicine-Ball Punch Throw",
        "Suitcase Carry Holds",
        "Kettlebell Suitcase Carry Hold",
    ],
)
def test_no_rebalanced_exercise_leaks_into_d1(name):
    item = _named(name)
    assert "d1" not in item["late_windows"]
    assert _eval(name, D1, days_until_fight=1)["blocked"] is True


# --- Suitcase carries: extended as honest support, not maximal-strength -------

@pytest.mark.parametrize(
    "name",
    ["Suitcase Carry Holds", "Kettlebell Suitcase Carry Hold"],
)
def test_suitcase_carries_extend_to_d6_d5_as_support_not_anchor(name):
    item = _named(name)
    assert item["late_windows"] == ["d21_to_d14", "d13_to_d8", "d7", "d6_to_d5"]
    # Low-cost grip/trunk support: it no longer over-claims maximal-strength
    # maintenance, and is governed as support-only.
    assert "maximal_strength_maintenance" not in item["tags"]
    assert item["support_only"] is True
    assert item["meaningful_stress"] is False

    assert _not_blocked(name, D7, days_until_fight=7)
    assert _not_blocked(name, D6_TO_D5, days_until_fight=6)
    # No external-load carry into the final sharpening days.
    assert _blocked(name, D4_TO_D2, days_until_fight=4)


# --- Landmine press: extended to D7 only, not into D6-D5 ----------------------

def test_landmine_split_stance_press_extends_to_d7_only():
    item = _named("Landmine Split-Stance Punch Press")
    assert item["late_windows"] == ["d21_to_d14", "d13_to_d8", "d7"]
    assert _not_blocked("Landmine Split-Stance Punch Press", D7, days_until_fight=7)
    # Still carries external load + moderate recovery cost: not auto-carried
    # into D-6/D-5.
    assert _blocked("Landmine Split-Stance Punch Press", D6_TO_D5, days_until_fight=6)


# --- Trap Bar Jump (Light): deliberately left conservative -------------------

def test_trap_bar_jump_light_stays_conservative():
    item = _named("Trap Bar Jump (Light)")
    # Despite the "Light" name it keeps real landing / eccentric / CNS cost, so
    # it gains no late windows.
    assert not item.get("late_windows")
    assert item["landing_cost"] != "none"
    assert item["cns_load"] == "high"
    assert item["soreness_risk"] == "high"
    assert _eval("Trap Bar Jump (Light)", D13_TO_D8, days_until_fight=10)["blocked"] is True
