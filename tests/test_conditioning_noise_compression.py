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


def test_bridge_keeps_fight_pace_conditioning_when_limiter_and_safe():
    week = {"phase": "SPP", "resolved_rule_state": {}, "must_keep": []}
    roles = [
        _role("neural_plus_strength_day", "strength", "", "monday"),
        _role("repeatability_support_day", "conditioning", "aerobic", "wednesday"),
        _role("fight_pace_repeatability_day", "conditioning", "glycolytic", "friday"),
    ]
    kept, _ = _apply_high_fatigue_week_compression(week, roles, [], _base_athlete(days_until_fight=16))
    systems = {r.get("preferred_system") for r in kept if r.get("category") == "conditioning"}
    assert "glycolytic" in systems
    assert "aerobic" not in systems



def test_key_goals_activates_fight_pace_priority_with_goals_fallback_shape():
    week = {"phase": "SPP", "resolved_rule_state": {}, "must_keep": []}
    roles = [
        _role("neural_plus_strength_day", "strength", "", "monday"),
        _role("repeatability_support_day", "conditioning", "aerobic", "wednesday"),
        _role("fight_pace_repeatability_day", "conditioning", "glycolytic", "friday"),
    ]
    athlete = _base_athlete(goals=[], key_goals=["conditioning"], weaknesses=["gas_tank"], days_until_fight=16)
    kept, _ = _apply_high_fatigue_week_compression(week, roles, [], athlete)
    systems = {r.get("preferred_system") for r in kept if r.get("category") == "conditioning"}
    assert "glycolytic" in systems
    assert "aerobic" not in systems


def test_realistic_app_shape_preserves_one_low_noise_without_extra_sessions():
    week = {"phase": "SPP", "resolved_rule_state": {}, "must_keep": []}
    roles = [
        _role("neural_plus_strength_day", "strength", "", "monday"),
        _role("repeatability_support_day", "conditioning", "aerobic", "wednesday"),
        _role("fight_pace_repeatability_day", "conditioning", "glycolytic", "friday"),
    ]
    athlete = _base_athlete(
        goals=[],
        key_goals=["conditioning", "power", "mobility"],
        weaknesses=["gas_tank"],
        equipment=["assault_bike", "rower"],
        fatigue="moderate",
        days_until_fight=20,
        weight_cut_risk=True,
        weight_cut_pct=2.6,
        injuries=["right ankle sprain"],
        readiness_flags=["active_weight_cut", "injury_management"],
    )
    kept, _ = _apply_high_fatigue_week_compression(week, roles, [], athlete)
    kept_conditioning = [r for r in kept if r.get("category") == "conditioning"]
    assert len(kept) == athlete["training_frequency"]
    assert len(kept_conditioning) == 1
    assert kept_conditioning[0].get("preferred_system") in {"aerobic", "alactic"}
    assert all(r.get("preferred_system") != "glycolytic" for r in kept_conditioning)

def test_high_fatigue_suppresses_optional_conditioning_even_with_limiter_signal():
    week = {"phase": "SPP", "resolved_rule_state": {}, "must_keep": []}
    roles = [
        _role("neural_plus_strength_day", "strength", "", "monday"),
        _role("repeatability_support_day", "conditioning", "aerobic", "wednesday"),
    ]
    kept, _ = _apply_high_fatigue_week_compression(week, roles, [], _base_athlete(fatigue="high", training_frequency=1))
    assert all(r.get("category") != "conditioning" for r in kept)
