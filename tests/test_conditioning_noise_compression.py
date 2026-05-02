from fightcamp.stage2_role_map import _apply_high_fatigue_week_compression


def _base_athlete(**overrides):
    athlete = {
        "fatigue": "moderate",
        "injury_mode": "full_plan",
        "days_until_fight": 20,
        "goals": ["conditioning"],
        "weaknesses": ["gas_tank"],
        "equipment": ["assault_bike", "rower"],
        "training_days": ["monday", "wednesday", "friday"],
        "training_frequency": 2,
        "hard_sparring_days": [],
        "readiness_flags": [],
    }
    athlete.update(overrides)
    return athlete


def _role(role_key, category, system, day):
    return {"role_key": role_key, "category": category, "preferred_system": system, "scheduled_day_hint": day}


def test_bridge_keeps_one_low_noise_conditioning_when_limiter_and_safe():
    week = {"phase": "SPP", "resolved_rule_state": {}, "must_keep": []}
    roles = [
        _role("neural_plus_strength_day", "strength", "", "monday"),
        _role("repeatability_support_day", "conditioning", "aerobic", "wednesday"),
        _role("fight_pace_repeatability_day", "conditioning", "glycolytic", "friday"),
    ]
    kept, _ = _apply_high_fatigue_week_compression(week, roles, [], _base_athlete(days_until_fight=16))
    systems = {r.get("preferred_system") for r in kept if r.get("category") == "conditioning"}
    assert "aerobic" in systems
    assert "glycolytic" not in systems


def test_high_fatigue_suppresses_optional_conditioning_even_with_limiter_signal():
    week = {"phase": "SPP", "resolved_rule_state": {}, "must_keep": []}
    roles = [
        _role("neural_plus_strength_day", "strength", "", "monday"),
        _role("repeatability_support_day", "conditioning", "aerobic", "wednesday"),
    ]
    kept, _ = _apply_high_fatigue_week_compression(week, roles, [], _base_athlete(fatigue="high", training_frequency=1))
    assert all(r.get("category") != "conditioning" for r in kept)
