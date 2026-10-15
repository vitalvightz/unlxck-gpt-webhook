"""Compact coaching: one cue, concise dose adjustments, full safety meaning."""
from fightcamp.coaching_copy import concise_coaching, compact_progress
from fightcamp.exercise_coaching import exercise_coaching


def test_compact_card_has_one_cue_and_an_authorised_numeric_advance():
    result = concise_coaching({
        "coaching_cues": [
            "Drive through the legs and brace the trunk; avoid grinding repetitions.",
            "Drive through the legs and brace the trunk.",
        ],
        "regression_options": [
            "Reduce sets to 2 instead of 3; keep effort and rests unchanged.",
            "Reduce load to a comfortable level.",
        ],
        "progression_rule": "Next D-21: add 5 kg. Only if controlled and recovered.",
        "stop_rules": ["End the set if pain appears or you lose trunk or joint control."],
    })
    assert len(result["coaching_cues"]) == 1
    assert result["progression_rule"] == "Add +5kg"
    assert result["regression_options"] == ["Reduce sets to 2 instead of 3"]
    assert all(len(line.split()) <= 9 for line in [
        result["coaching_cues"][0], result["progression_rule"],
        result["regression_options"][0], result["stop_rules"][0],
    ])


def test_no_weight_is_invented_from_an_unsupported_progression():
    assert compact_progress("Repeat current dose.") == "Repeat current dose."
    guidance = exercise_coaching(
        {"name": "Incline DB Press", "slot_group": "strength_slots",
         "base_prescription": "2x6 @ RPE 6"},
        {"role_key": "primary_strength_day", "category": "strength"},
        phase="GPP", d_day=31,
    )
    assert guidance["progression_rule"] == "Repeat prescribed dose."
    assert len(guidance["coaching_cues"]) == 1


def test_taper_never_promises_extra_load():
    guidance = exercise_coaching(
        {"name": "Barbell Thruster", "slot_group": "strength_slots",
         "effective_prescription": "2x2 @ RPE 6"},
        {"role_key": "strength_touch_day", "category": "strength"},
        phase="TAPER", d_day=5,
    )
    assert "progression_rule" not in guidance


def test_medical_stop_keeps_critical_text_even_if_long():
    source = "Stop and seek immediate medical help for chest pain or unusual breathlessness."
    result = concise_coaching({"stop_rules": [source]})
    assert "medical help" in result["stop_rules"][0]
    assert "chest pain" in result["stop_rules"][0]
