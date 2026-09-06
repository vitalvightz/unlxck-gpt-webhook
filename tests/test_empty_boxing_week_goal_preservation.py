from __future__ import annotations

from fightcamp.goal_repair_effective_contact_policy import (
    effective_goal_repair_compression_state,
)
from fightcamp.priority_profile import build_priority_profile, describe_priority_focus


def test_zero_effective_sparring_clears_stale_spar_first_cap():
    week = {
        "effective_hard_sparring_days": [],
        "intentional_compression": {
            "active": True,
            "reason_codes": ["spar_first_cap"],
            "reason": "spar_first_cap",
            "summary": "stale spar-first compression",
        },
    }
    suppressed = [
        {
            "role_key": "fight_pace_repeatability_day",
            "compression_reason_codes": ["spar_first_cap"],
        }
    ]

    compression, codes = effective_goal_repair_compression_state(week, suppressed)

    assert compression["active"] is False
    assert compression["reason_codes"] == []
    assert codes == []


def test_one_effective_sparring_day_does_not_erase_spar_first_authority():
    week = {
        "effective_hard_sparring_days": ["Friday"],
        "intentional_compression": {
            "active": True,
            "reason_codes": ["spar_first_cap"],
        },
    }
    suppressed = [
        {
            "role_key": "fight_pace_repeatability_day",
            "compression_reason_codes": ["spar_first_cap"],
        }
    ]

    compression, codes = effective_goal_repair_compression_state(week, suppressed)

    assert compression["active"] is True
    assert compression["reason_codes"] == ["spar_first_cap"]
    assert codes == ["spar_first_cap", "spar_first_cap"]


def test_singular_repeated_hard_efforts_clarification_keeps_glycolytic_intent():
    profile = build_priority_profile(
        {
            "key_goals": ["conditioning", "speed"],
            "primary_goal": "conditioning",
            "weak_areas": ["gas_tank", "trunk_strength"],
            "primary_weak_area": "gas_tank",
        }
    )

    focus = describe_priority_focus(
        profile,
        collision_detail="Repeated hard efforts",
        collision_details=[],
    )

    assert focus["collision_detail"] == "Repeated hard efforts"
    assert focus["derived_clarification_tags"] == [
        "glycolytic",
        "work_capacity",
        "conditioning",
        "mental_toughness",
    ]
