from types import SimpleNamespace

from fightcamp.stage2_planning_brief import (
    _apply_sparse_conditioning_quota_boost,
    _sparse_conditioning_quota_boost_requested,
)
from fightcamp.stage2_role_map import _build_weekly_role_map


def _context(*, goals=None, weaknesses=None, hard=None, support=None, technical=None):
    return SimpleNamespace(
        key_goals=goals or [],
        weaknesses=weaknesses or [],
        hard_sparring_days=hard or [],
        support_work_days=support or [],
        technical_skill_days=technical or [],
    )


def test_sparse_conditioning_goal_adds_exactly_one_quota_slot():
    context = _context(goals=["conditioning"])
    counts, active = _apply_sparse_conditioning_quota_boost(
        {"strength": 1, "conditioning": 2, "recovery": 1}, context, "GPP"
    )
    assert active is True
    assert counts == {"strength": 1, "conditioning": 3, "recovery": 1}


def test_gas_tank_weakness_triggers_but_two_gym_days_do_not():
    sparse = _context(weaknesses=["gas_tank"], support=["monday"])
    assert _sparse_conditioning_quota_boost_requested(sparse, "SPP") is True

    not_sparse = _context(
        weaknesses=["gas_tank"], hard=["tuesday"], technical=["thursday"]
    )
    assert _sparse_conditioning_quota_boost_requested(not_sparse, "SPP") is False


def test_taper_never_receives_sparse_conditioning_quota_boost():
    context = _context(goals=["conditioning"])
    assert _sparse_conditioning_quota_boost_requested(context, "TAPER") is False


def test_quota_boost_survives_role_cap_and_is_non_aerobic():
    athlete_model = {
        "sport": "boxing",
        "training_frequency": 4,
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "saturday"],
        "fight_date": "2027-07-18",
        "fatigue": "low",
        "cut_severity_bucket": "low",
        "injury_mode": "full_plan",
        "key_goals": ["conditioning"],
        "weaknesses": ["gas_tank"],
        "hard_sparring_days": [],
        "support_work_days": [],
        "technical_skill_days": [],
    }
    progression = {
        "weeks": [
            {
                "week_index": 1,
                "phase": "GPP",
                "stage_key": "general_capacity",
                "span_days": 7,
                "session_counts": {"strength": 1, "conditioning": 3, "recovery": 0},
                "conditioning_sequence": ["aerobic", "glycolytic", "alactic"],
                "conditioning_quota_boost": {"count": 1, "required_system": "glycolytic"},
            },
            {
                "week_index": 2,
                "phase": "GPP",
                "stage_key": "general_capacity",
                "span_days": 7,
                "session_counts": {"strength": 1, "conditioning": 2, "recovery": 1},
                "conditioning_sequence": ["aerobic", "glycolytic"],
            },
            {
                "week_index": 3,
                "phase": "SPP",
                "stage_key": "fight_specific",
                "span_days": 7,
                "session_counts": {"strength": 1, "conditioning": 2, "recovery": 1},
                "conditioning_sequence": ["glycolytic", "alactic"],
            },
            {
                "week_index": 4,
                "phase": "TAPER",
                "stage_key": "taper",
                "span_days": 7,
                "session_counts": {"strength": 1, "conditioning": 1, "recovery": 1},
                "conditioning_sequence": ["alactic"],
            },
        ]
    }

    role_map = _build_weekly_role_map(
        athlete_model, progression, {"key": "conditioning_endurance"}
    )
    first_week = role_map["weeks"][0]
    systems = [
        role.get("preferred_system")
        for role in first_week["session_roles"]
        if role.get("category") == "conditioning"
    ]
    assert len(systems) == 3
    assert systems[0] == "glycolytic"
    assert systems[0] != "aerobic"
    assert len(first_week["session_roles"]) <= len(athlete_model["training_days"])
