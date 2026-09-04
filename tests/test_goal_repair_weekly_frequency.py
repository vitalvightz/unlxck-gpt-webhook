from __future__ import annotations

from fightcamp.goal_preservation import reconcile_goal_preservation
from fightcamp.goal_repair_effective_contact_policy import (
    counts_toward_weekly_frequency,
    resolved_weekly_frequency_count,
)


def _candidate() -> dict:
    return {
        "role_key": "strength_touch_day",
        "category": "strength",
        "strength_session_index": 1,
        "session_index": 1,
    }


def _strength_pool() -> dict:
    return {
        "SPP": {
            "strength_slots": [
                {
                    "slot_id": "loaded-hinge",
                    "session_index": 1,
                    "role": "hinge",
                    "quality_class": "anchor_loaded",
                    "anchor_capable": True,
                    "selected": {
                        "name": "Romanian Deadlift",
                        "quality_class": "anchor_loaded",
                        "prescription": "3 x 5 @ RPE 7",
                        "movement_patterns": ["hinge"],
                    },
                }
            ]
        }
    }


def _brief(*, roles: list[dict], frequency: int) -> dict:
    candidate = _candidate()
    return {
        "athlete_snapshot": {
            "key_goals": ["strength"],
            "primary_goal": "strength",
            "days_until_fight": 20,
            "fatigue": "low",
            "training_frequency": frequency,
            "hard_sparring_days": [],
        },
        "priority_focus": {"primary_goal": "strength", "secondary_goals": []},
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "phase": "SPP",
                    "declared_training_days": ["Monday", "Thursday"],
                    "calendar_days": [
                        {"weekday": "monday", "d_day": 18},
                        {"weekday": "thursday", "d_day": 15},
                    ],
                    "session_roles": roles,
                    "goal_repair_candidates": [candidate],
                    "effective_hard_sparring_days": [],
                    "intentional_compression": {"active": False, "reason_codes": []},
                    "suppressed_roles": [],
                }
            ]
        },
        "candidate_pools": _strength_pool(),
        "restrictions": [],
    }


def test_fillers_and_zero_load_support_do_not_consume_frequency():
    roles = [
        {"role_key": "tactical_watch", "camp_week_filler": True},
        {"role_key": "tactical_cue_card", "camp_week_filler": True},
        {"role_key": "neural_visualization", "camp_week_filler": True},
        {"role_key": "recovery_reset_day", "category": "recovery", "camp_week_filler": True},
        {"role_key": "footwork_walkthrough", "camp_week_filler": True},
    ]
    assert resolved_weekly_frequency_count(roles) == 0


def test_technical_only_downgraded_contact_does_not_consume_full_session_slot():
    role = {
        "role_key": "hard_sparring_day",
        "category": "sparring",
        "effective_load": "technical",
        "camp_week_filler": False,
    }
    assert counts_toward_weekly_frequency(role) is False


def test_neural_microdose_does_not_consume_full_session_slot():
    role = {
        "role_key": "alactic_speed_day",
        "category": "conditioning",
        "preferred_system": "alactic",
    }
    assert counts_toward_weekly_frequency(role) is False


def test_genuine_hard_reduced_strength_and_conditioning_consume_frequency():
    roles = [
        {"role_key": "hard_sparring_day", "effective_load": "hard"},
        {"role_key": "hard_sparring_day", "effective_load": "reduced"},
        {"role_key": "primary_strength_day", "category": "strength"},
        {"role_key": "fight_pace_repeatability_day", "category": "conditioning", "preferred_system": "glycolytic"},
    ]
    assert [counts_toward_weekly_frequency(role) for role in roles] == [True, True, True, True]
    assert resolved_weekly_frequency_count(roles) == 4


def test_unknown_non_filler_role_fails_safe_and_counts():
    assert counts_toward_weekly_frequency({"role_key": "future_unknown_role"}) is True
    assert counts_toward_weekly_frequency({"role_key": "future_unknown_role", "camp_week_filler": True}) is False


def test_goal_repair_ignores_filler_and_technical_only_false_capacity():
    roles = [
        {
            "role_key": "hard_sparring_day",
            "category": "sparring",
            "effective_load": "technical",
            "scheduled_day_hint": "Tuesday",
            "scheduled_countdown_label": "D-17",
            "session_index": 1,
        },
        {
            "role_key": "tactical_watch",
            "camp_week_filler": True,
            "scheduled_day_hint": "Wednesday",
            "scheduled_countdown_label": "D-16",
            "session_index": 2,
        },
        {
            "role_key": "recovery_reset_day",
            "category": "recovery",
            "camp_week_filler": True,
            "scheduled_day_hint": "Wednesday",
            "scheduled_countdown_label": "D-16",
            "session_index": 3,
        },
    ]
    brief = _brief(roles=roles, frequency=1)

    reconcile_goal_preservation(brief)

    strength = next(entry for entry in brief["goal_preservation"] if entry["goal"] == "strength")
    assert strength["repair_attempts"]
    assert strength["repair_attempts"][0]["result"] == "restored"
    assert strength["satisfied"] is True
    assert resolved_weekly_frequency_count(brief["weekly_role_map"]["weeks"][0]["session_roles"]) == 1


def test_four_genuine_sessions_still_block_a_fifth_repair():
    roles = [
        {
            "role_key": "hard_sparring_day",
            "category": "sparring",
            "effective_load": "hard",
            "scheduled_day_hint": "Tuesday",
            "scheduled_countdown_label": "D-17",
            "session_index": 1,
        },
        {
            "role_key": "hard_sparring_day",
            "category": "sparring",
            "effective_load": "reduced",
            "scheduled_day_hint": "Friday",
            "scheduled_countdown_label": "D-14",
            "session_index": 2,
        },
        {
            "role_key": "fight_pace_repeatability_day",
            "category": "conditioning",
            "preferred_system": "glycolytic",
            "scheduled_day_hint": "Wednesday",
            "scheduled_countdown_label": "D-16",
            "session_index": 3,
        },
        {
            "role_key": "threshold_conditioning_day",
            "category": "conditioning",
            "preferred_system": "glycolytic",
            "scheduled_day_hint": "Thursday",
            "scheduled_countdown_label": "D-15",
            "session_index": 4,
        },
    ]
    brief = _brief(roles=roles, frequency=4)

    reconcile_goal_preservation(brief)

    strength = next(entry for entry in brief["goal_preservation"] if entry["goal"] == "strength")
    assert strength["repair_attempts"]
    assert strength["repair_attempts"][0]["result"] == "session_cap"
    assert resolved_weekly_frequency_count(brief["weekly_role_map"]["weeks"][0]["session_roles"]) == 4
