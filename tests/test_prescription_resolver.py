from fightcamp.prescription_resolver import resolve_strength_slot_prescription
import pytest


def _role(max_sets: int, max_reps: int, rpe: str = "6-7") -> dict:
    return {
        "strength_dose_cap": {"max_sets": max_sets, "max_reps": max_reps},
        "rpe_cap": rpe,
    }


def _slot(prescription: str, *, anchor: bool = False, role: str = "hinge") -> dict:
    return {
        "role": role,
        "anchor_capable": anchor,
        "selected": {"name": "Exercise", "prescription": prescription},
    }


def test_anchor_strength_is_capped_by_scheduled_day_envelope():
    result = resolve_strength_slot_prescription(
        role=_role(3, 3),
        slot=_slot("4 x 3 @ RPE 7", anchor=True),
    )
    assert result["effective_prescription"] == "3 sets x 3 reps @ RPE 6"
    assert result["dose_authority"] == "scheduled_countdown_overlay"


def test_secondary_strength_loses_more_volume_than_anchor():
    result = resolve_strength_slot_prescription(
        role=_role(3, 3),
        slot=_slot("3 x 6", anchor=False, role="press"),
    )
    assert result["effective_prescription"] == "2 sets x 5 reps @ RPE 6"
    assert result["dose_role_kind"] == "secondary"


def test_support_work_keeps_reps_but_reduces_sets():
    result = resolve_strength_slot_prescription(
        role=_role(3, 3),
        slot=_slot("3 x 8", role="anti_rotation"),
    )
    assert result["effective_prescription"] == "2 sets x 8 reps @ RPE 6"
    assert result["dose_role_kind"] == "support"


def test_uncapped_strength_keeps_bank_prescription():
    result = resolve_strength_slot_prescription(
        role={},
        slot=_slot("4 x 3 @ RPE 7", anchor=True),
    )
    assert result["effective_prescription"] == "4 sets x 3 reps @ RPE 7"
    assert result["dose_authority"] == "exercise_bank"


def test_capped_strength_keeps_exact_bank_rest():
    result = resolve_strength_slot_prescription(
        role=_role(3, 3),
        slot=_slot("4-5 sets x 5-6 reps @ RPE 7-8; rest 90-120 sec", anchor=True),
    )
    assert result["effective_prescription"] == "3 sets x 3 reps @ RPE 6; rest 120 sec"


@pytest.mark.parametrize(
    ("role", "state", "expected"),
    [
        ({}, None, "4 sets x 5 reps @ RPE 7"),
        (_role(3, 3, "6-7"), None, "3 sets x 3 reps @ RPE 6"),
        (_role(2, 2, "5-6"), {"injury_restricted": True}, "1 set x 2 reps @ RPE 5"),
    ],
)
def test_bank_range_has_exact_gpp_spp_or_injury_taper_dose(role, state, expected):
    result = resolve_strength_slot_prescription(
        role=role,
        slot=_slot("4-5 sets x 5-6 reps @ RPE 7-8", anchor=True),
        athlete_state=state,
    )
    assert result["effective_prescription"] == expected
