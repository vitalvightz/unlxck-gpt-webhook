from __future__ import annotations

from fightcamp.goal_preservation import reconcile_goal_preservation, validate_goal_preservation
from fightcamp.goal_repair_effective_contact_policy import effective_goal_repair_compression_state


def _compression_brief(*, effective_days, compression_codes, suppressed_codes=None, include_effective=True):
    week = {
        "week_index": 2,
        "intentional_compression": {
            "active": True,
            "reason_codes": list(compression_codes),
            "reason": "compressed",
            "summary": "compressed summary",
        },
        "suppressed_roles": [
            {
                "role_key": "primary_strength_day",
                "compression_reason_codes": list(suppressed_codes or compression_codes),
                "governance": {"hard_suppression_reasons": []},
            }
        ],
    }
    if include_effective:
        week["effective_hard_sparring_days"] = list(effective_days)
    return week


def _live_state(week):
    suppressed = week["suppressed_roles"]
    return effective_goal_repair_compression_state(week, suppressed)


def test_true_two_effective_hard_days_keep_two_hard_spar_authority():
    week = _compression_brief(
        effective_days=["Tuesday", "Friday"],
        compression_codes=["two_hard_spar_days"],
    )
    compression, codes = _live_state(week)
    assert compression["active"] is True
    assert codes == ["two_hard_spar_days", "two_hard_spar_days"]


def test_one_effective_hard_day_clears_stale_two_hard_spar_authority():
    week = _compression_brief(
        effective_days=["Friday"],
        compression_codes=["two_hard_spar_days"],
    )
    compression, codes = _live_state(week)
    assert compression["active"] is False
    assert codes == []


def test_zero_effective_hard_days_clears_stale_two_hard_spar_authority():
    week = _compression_brief(
        effective_days=[],
        compression_codes=["two_hard_spar_days"],
    )
    compression, codes = _live_state(week)
    assert compression["active"] is False
    assert codes == []


def test_other_live_compression_reasons_remain_authoritative():
    week = _compression_brief(
        effective_days=["Friday"],
        compression_codes=["high_fatigue", "two_hard_spar_days"],
        suppressed_codes=["high_fatigue", "two_hard_spar_days"],
    )
    compression, codes = _live_state(week)
    assert compression["active"] is True
    assert compression["reason_codes"] == ["high_fatigue"]
    assert codes == ["high_fatigue", "high_fatigue"]


def test_unresolved_effective_contact_keeps_declared_day_fail_safe_authority():
    week = _compression_brief(
        effective_days=[],
        compression_codes=["two_hard_spar_days"],
        include_effective=False,
    )
    compression, codes = _live_state(week)
    assert compression["active"] is True
    assert codes == ["two_hard_spar_days", "two_hard_spar_days"]


def test_reconcile_restores_strength_after_two_declared_hard_days_resolve_technical():
    candidate = {
        "role_key": "strength_touch_day",
        "category": "strength",
        "strength_session_index": 1,
        "session_index": 1,
    }
    brief = {
        "athlete_snapshot": {
            "key_goals": ["strength"],
            "primary_goal": "strength",
            "days_until_fight": 20,
            "fatigue": "low",
            "training_frequency": 4,
            "hard_sparring_days": ["Tuesday", "Friday"],
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
                    "session_roles": [],
                    "goal_repair_candidates": [candidate],
                    "effective_hard_sparring_days": [],
                    "hard_sparring_plan": [
                        {"day": "Tuesday", "status": "technical_only", "effective_load": "technical"},
                        {"day": "Friday", "status": "technical_only", "effective_load": "technical"},
                    ],
                    "intentional_compression": {
                        "active": True,
                        "reason_codes": ["two_hard_spar_days"],
                        "reason": "compressed",
                        "summary": "compressed summary",
                    },
                    "suppressed_roles": [
                        {
                            "category": "strength",
                            "role_key": "strength_touch_day",
                            "compression_reason_codes": ["two_hard_spar_days"],
                            "governance": {"hard_suppression_reasons": []},
                        }
                    ],
                }
            ]
        },
        "candidate_pools": {
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
        },
        "restrictions": [],
    }

    reconcile_goal_preservation(brief)

    week = brief["weekly_role_map"]["weeks"][0]
    strength = next(entry for entry in brief["goal_preservation"] if entry["goal"] == "strength")
    assert len(week["session_roles"]) == 1
    assert strength["repair_attempts"][0]["result"] == "restored"
    assert strength["satisfied"] is True
    assert validate_goal_preservation(brief) == []
