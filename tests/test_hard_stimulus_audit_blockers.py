from __future__ import annotations

import fightcamp.empty_combat_week_policy as policy
from fightcamp.normal_calendar_placement import fill_missing_session_days


def _athlete(**overrides):
    athlete = {
        "sport": "boxing",
        "fight_format": "boxing",
        "rounds_format": "3 x 3",
        "fatigue": "low",
        "cut_severity_bucket": "low",
        "weight_cut_risk": False,
        "injury_mode": "full_plan",
        "injuries": [],
        "readiness_flags": [],
        "primary_goal": "conditioning",
        "key_goals": ["conditioning"],
        "weaknesses": ["gas_tank"],
        "training_frequency": 5,
        "training_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        "hard_sparring_days": ["Monday"],
        "support_work_days": [],
        "technical_skill_days": [],
    }
    athlete.update(overrides)
    return athlete


def _bridge_week():
    return {
        "phase": "GPP",
        "declared_training_days": ["Monday", "Tuesday", "Wednesday", "Thursday"],
        "calendar_days": [
            {"weekday": "monday", "d_day": 21},
            {"weekday": "tuesday", "d_day": 20},
            {"weekday": "wednesday", "d_day": 19},
            {"weekday": "thursday", "d_day": 18},
        ],
    }


def test_bridge_receives_resolved_effective_hard_contact_count(monkeypatch):
    seen_counts: list[int] = []

    def fake_bridge_rules(**kwargs):
        count = int(kwargs["hard_sparring_days_declared"])
        seen_counts.append(count)
        return {
            "block_full_plan": False,
            "glycolytic_touch_max": 0 if count else 1,
        }

    monkeypatch.setattr(policy, "compute_bridge_rules", fake_bridge_rules)
    athlete = _athlete()

    hard_week = _bridge_week()
    hard_week["hard_sparring_plan"] = [
        {
            "day": "Monday",
            "effective_load": "hard",
            "status": "hard_as_planned",
        }
    ]
    assert policy._bridge_legal_pressure_days(hard_week, athlete) == []
    assert seen_counts and set(seen_counts) == {1}

    seen_counts.clear()
    technical_week = _bridge_week()
    technical_week["hard_sparring_plan"] = [
        {
            "day": "Monday",
            "effective_load": "technical",
            "status": "convert_to_technical_suggested",
        }
    ]
    assert policy._bridge_legal_pressure_days(technical_week, athlete) == [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
    ]
    assert seen_counts and set(seen_counts) == {0}


def test_roomy_gpp_budget_cannot_override_bridge_hard_contact_block():
    athlete = _athlete()
    week = _bridge_week()
    week["hard_sparring_plan"] = [
        {
            "day": "Monday",
            "effective_load": "hard",
            "status": "hard_as_planned",
        }
    ]

    # Weekly budget can legitimately want two total hard exposures in roomy GPP,
    # but the closer-to-fight bridge remains the higher-order safety authority.
    assert policy._weekly_hard_exposure_target(week, athlete) == 2
    assert policy._hard_stimulus_deficit(week, athlete) is True
    assert policy._bridge_legal_pressure_days(week, athlete) == []
    assert policy._eligible_hard_stimulus_deficit(week, athlete) is False


def test_hard_pad_counts_for_weekly_budget_but_not_spar_first_authority():
    athlete = _athlete(
        hard_sparring_days=[],
        session_loads_by_day={"Wednesday": {"session_type": "pads", "rpe": 9}},
    )
    week = {
        "phase": "GPP",
        "hard_sparring_plan": [],
        "intentional_compression": {
            "active": True,
            "reason_codes": ["spar_first_cap"],
            "reason": "spar_first_cap",
            "summary": "Protect sparring first.",
        },
    }
    suppressed = [
        {
            "compression_reason_codes": ["spar_first_cap"],
            "compression_summary": "Protect sparring first.",
            "reasons": ["Protect sparring first."],
        }
    ]

    assert policy._effective_hard_contact_days(week, athlete) == set()
    assert policy._effective_hard_exposure_days(week, athlete) == {"wednesday"}

    policy._scrub_stale_spar_first_state(week, suppressed)
    assert "spar_first_cap" not in week["intentional_compression"]["reason_codes"]
    assert week["intentional_compression"]["active"] is False
    assert "spar_first_cap" not in suppressed[0]["compression_reason_codes"]


def test_calendar_completion_honors_role_allowed_training_days():
    role = {
        "category": "conditioning",
        "role_key": "fight_pace_repeatability_day",
        "preferred_system": "glycolytic",
        "scheduled_day_hint": "",
        "allowed_training_days": ["Tuesday"],
    }
    role_map = {
        "weeks": [
            {
                "week_index": 1,
                "phase": "SPP",
                "declared_training_days": ["Monday", "Tuesday"],
                "declared_hard_sparring_days": [],
                "hard_sparring_plan": [],
                "session_roles": [role],
            }
        ]
    }

    fill_missing_session_days(role_map)
    assert role["scheduled_day_hint"] == "Tuesday"


def test_calendar_completion_keeps_explicitly_ineligible_hard_role_dayless():
    role = {
        "category": "conditioning",
        "role_key": "fight_pace_repeatability_day",
        "preferred_system": "glycolytic",
        "scheduled_day_hint": "",
        "allowed_training_days": [],
    }
    role_map = {
        "weeks": [
            {
                "week_index": 1,
                "phase": "SPP",
                "declared_training_days": ["Monday", "Tuesday"],
                "declared_hard_sparring_days": [],
                "hard_sparring_plan": [],
                "session_roles": [role],
            }
        ]
    }

    fill_missing_session_days(role_map)
    assert role["scheduled_day_hint"] == ""
