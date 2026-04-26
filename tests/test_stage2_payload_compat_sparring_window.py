from fightcamp.stage2_payload import _build_weekly_role_map


def test_stage2_weekly_role_map_passes_projected_fight_window_to_sparring_planner():
    athlete = {
        "sport": "boxing",
        "fatigue": "low",
        "days_until_fight": 40,
        "hard_sparring_days": ["Tuesday", "Thursday"],
    }
    week_by_week = {
        "weeks": [
            {
                "phase": "SPP",
                "stage_key": "specific_density_build",
                "week_index": 1,
                "phase_week_index": 1,
                "phase_week_total": 1,
                "span_days": 10,
                "session_counts": {"strength": 1, "conditioning": 1, "recovery": 1},
                "conditioning_sequence": ["aerobic"],
            }
        ]
    }

    role_map = _build_weekly_role_map(
        athlete_model=athlete,
        week_by_week_progression=week_by_week,
        limiter_profile={"key": "general_fight_readiness"},
    )
    week = role_map["weeks"][0]
    plan = week.get("hard_sparring_plan", [])
    assert plan
    assert all(entry["status"] == "convert_to_technical_suggested" for entry in plan)
    assert all("no_hard_sparring_d14_to_d0" in entry.get("reason_codes", []) for entry in plan)
