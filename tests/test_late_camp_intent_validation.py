from fightcamp.late_camp_role_morph import apply_late_camp_role_morph


def _map_for(role, d_day):
    weekday = "tuesday"
    role = dict(role)
    role["scheduled_day_hint"] = weekday
    return {
        "weeks": [
            {
                "calendar_days": [{"weekday": weekday, "d_day": d_day}],
                "session_roles": [role],
            }
        ]
    }


def test_strength_intent_survives_d17_retention_dose():
    role = {"category": "strength", "role_key": "neural_plus_strength_day"}
    result = apply_late_camp_role_morph(_map_for(role, 17))
    final = result["weeks"][0]["session_roles"][0]
    assert final["intent_validation"]["intent"] == "meaningful_strength"
    assert final["intent_validation"]["satisfied"] is True
    assert final["strength_dose_cap"]["max_sets"] >= 2


def test_strength_intent_is_explicitly_unsatisfied_when_morph_becomes_microdose():
    role = {"category": "strength", "role_key": "neural_plus_strength_day"}
    result = apply_late_camp_role_morph(_map_for(role, 5))
    final = result["weeks"][0]["session_roles"][0]
    assert final["intent_validation"]["intent"] == "meaningful_strength"
    assert final["intent_validation"]["satisfied"] is False
    assert final["intent_validation"]["reason_code"] == "countdown_morph_reduced_original_intent"
    assert result["post_morph_intent_validation"]["unsatisfied"] == 1


def test_hard_conditioning_intent_is_not_claimed_after_rhythm_morph():
    role = {
        "category": "conditioning",
        "role_key": "fight_pace_repeatability_day",
        "preferred_system": "glycolytic",
        "counts_toward_conditioning_cap": True,
    }
    result = apply_late_camp_role_morph(_map_for(role, 12))
    final = result["weeks"][0]["session_roles"][0]
    assert final["role_key"] == "light_fight_pace_touch_day"
    assert final["intent_validation"]["intent"] == "hard_conditioning"
    assert final["intent_validation"]["satisfied"] is False


def test_hard_conditioning_intent_survives_before_morph_boundary():
    role = {
        "category": "conditioning",
        "role_key": "fight_pace_repeatability_day",
        "preferred_system": "glycolytic",
        "counts_toward_conditioning_cap": True,
    }
    result = apply_late_camp_role_morph(_map_for(role, 18))
    final = result["weeks"][0]["session_roles"][0]
    assert final["intent_validation"]["satisfied"] is True
    assert result["post_morph_intent_validation"]["unsatisfied"] == 0
