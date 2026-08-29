from fightcamp.prescription_resolver import resolve_strength_prescription


def _role(max_sets=3, max_reps=3, rpe_cap="6-7"):
    return {
        "strength_dose_cap": {"max_sets": max_sets, "max_reps": max_reps},
        "rpe_cap": rpe_cap,
    }


def test_anchor_respects_countdown_cap_without_increasing_bank_dose():
    option = {
        "name": "Trap Bar Deadlift",
        "prescription": "4 x 3 @ RPE 7",
        "anchor_capable": True,
    }
    resolved = resolve_strength_prescription(option=option, role=_role())
    assert resolved["base_prescription"] == "4 x 3 @ RPE 7"
    assert resolved["effective_prescription"] == "3 x 3 @ RPE 7"
    assert resolved["prescription"] == resolved["effective_prescription"]
    assert resolved["dose_authority"] == "scheduled_countdown_overlay"


def test_secondary_loses_sets_but_keeps_moderate_rep_character():
    option = {
        "name": "Landmine Split-Stance Punch Press",
        "prescription": "3 x 6 @ RPE 6",
        "anchor_capable": False,
        "movement_patterns": ["press"],
    }
    resolved = resolve_strength_prescription(option=option, role=_role())
    assert resolved["effective_prescription"].startswith("2 x 5")


def test_support_is_not_forced_into_anchor_rep_cap():
    option = {
        "name": "Pallof Press Anti-Rotation",
        "prescription": "3 x 8 @ RPE 4",
        "anchor_capable": False,
        "movement_patterns": ["anti_rotation"],
    }
    resolved = resolve_strength_prescription(option=option, role=_role())
    assert resolved["effective_prescription"].startswith("2 x 8")


def test_high_fatigue_only_reduces_further():
    option = {
        "name": "Trap Bar Deadlift",
        "prescription": "4 x 3 @ RPE 7",
        "anchor_capable": True,
    }
    low = resolve_strength_prescription(
        option=option,
        role=_role(),
        athlete_model={"fatigue_level": "low"},
    )
    high = resolve_strength_prescription(
        option=option,
        role=_role(),
        athlete_model={"fatigue_level": "high"},
    )
    assert low["effective_prescription"].startswith("3 x 3")
    assert high["effective_prescription"].startswith("2 x 3")


def test_high_cut_only_reduces_further():
    option = {
        "name": "Trap Bar Deadlift",
        "prescription": "4 x 3 @ RPE 7",
        "anchor_capable": True,
    }
    resolved = resolve_strength_prescription(
        option=option,
        role=_role(),
        athlete_model={"cut_severity": "aggressive"},
    )
    assert resolved["effective_prescription"].startswith("2 x 3")


def test_no_cap_leaves_base_prescription_untouched():
    option = {
        "name": "Trap Bar Deadlift",
        "prescription": "4 x 3 @ RPE 7",
        "anchor_capable": True,
    }
    resolved = resolve_strength_prescription(option=option, role={})
    assert resolved["prescription"] == "4 x 3 @ RPE 7"
    assert "effective_prescription" not in resolved
