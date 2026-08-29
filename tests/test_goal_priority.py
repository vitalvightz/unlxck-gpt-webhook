from fightcamp.goal_priority import goal_priority_scores, role_goal_priority


def _strength_role():
    return {"category": "strength", "role_key": "neural_plus_strength_day"}


def _conditioning_role(system="glycolytic"):
    return {
        "category": "conditioning",
        "role_key": "fight_pace_repeatability_day",
        "preferred_system": system,
    }


def test_primary_power_outweighs_secondary_conditioning():
    athlete = {
        "primary_goal": "power",
        "key_goals": ["power", "conditioning"],
        "weak_areas": ["conditioning"],
    }
    assert role_goal_priority(_strength_role(), athlete) > role_goal_priority(
        _conditioning_role(), athlete
    )


def test_primary_conditioning_outweighs_secondary_power():
    athlete = {
        "primary_goal": "conditioning",
        "key_goals": ["conditioning", "power"],
        "weak_areas": ["power"],
    }
    assert role_goal_priority(_conditioning_role(), athlete) > role_goal_priority(
        _strength_role(), athlete
    )


def test_speed_is_only_secondary_bonus_for_alactic_conditioning():
    athlete = {
        "primary_goal": "speed",
        "key_goals": ["speed"],
    }
    alactic = _conditioning_role("alactic")
    glycolytic = _conditioning_role("glycolytic")
    assert role_goal_priority(alactic, athlete) > role_goal_priority(glycolytic, athlete)


def test_scores_preserve_primary_over_key_goal_over_weakness():
    scores = goal_priority_scores(
        {
            "primary_goal": "power",
            "key_goals": ["conditioning"],
            "weak_areas": ["speed"],
        }
    )
    assert scores["strength"] > scores["conditioning"] > scores["speed"]
