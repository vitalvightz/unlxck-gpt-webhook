from fightcamp.prescription_resolver import resolve_strength_slot_prescription


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
    assert result["effective_prescription"] == "3 x 3 @ RPE 6-7 max"
    assert result["dose_authority"] == "scheduled_countdown_overlay"


def test_secondary_strength_loses_more_volume_than_anchor():
    result = resolve_strength_slot_prescription(
        role=_role(3, 3),
        slot=_slot("3 x 6", anchor=False, role="press"),
    )
    assert result["effective_prescription"] == "2 x 5 @ RPE 6-7 max"
    assert result["dose_role_kind"] == "secondary"


def test_support_work_keeps_reps_but_reduces_sets():
    result = resolve_strength_slot_prescription(
        role=_role(3, 3),
        slot=_slot("3 x 8", role="anti_rotation"),
    )
    assert result["effective_prescription"] == "2 x 8 @ RPE 6-7 max"
    assert result["dose_role_kind"] == "support"


def test_uncapped_strength_keeps_bank_prescription():
    result = resolve_strength_slot_prescription(
        role={},
        slot=_slot("4 x 3 @ RPE 7", anchor=True),
    )
    assert result["effective_prescription"] == "4 x 3 @ RPE 7"
    assert result["dose_authority"] == "exercise_bank"
