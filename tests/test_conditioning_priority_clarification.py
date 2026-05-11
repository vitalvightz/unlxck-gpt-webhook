from __future__ import annotations

from fightcamp import conditioning


def test_no_clarification_tags_has_no_bonus():
    bonus, hits = conditioning._conditioning_clarification_bonus(
        ["glycolytic", "conditioning", "work_capacity"],
        [],
    )
    assert bonus == 0.0
    assert hits == []


def test_late_round_fatigue_tags_bump_matching_drill_tags():
    derived_tags = ["glycolytic", "conditioning", "work_capacity", "mental_toughness"]

    bonus_a, hits_a = conditioning._conditioning_clarification_bonus(
        ["glycolytic", "conditioning", "work_capacity"],
        derived_tags,
    )
    bonus_b, hits_b = conditioning._conditioning_clarification_bonus(
        ["aerobic", "recovery"],
        derived_tags,
    )

    assert bonus_a > 0
    assert set(hits_a) == {"glycolytic", "conditioning", "work_capacity"}
    assert bonus_b == 0.0
    assert hits_b == []


def test_recovery_between_bursts_bumps_recovery_tags_only():
    derived_tags = conditioning.derive_clarification_tags(
        [{"tag": "conditioning", "detail": "Recovery between bursts"}]
    )
    assert set(derived_tags) == {"anaerobic_alactic", "aerobic", "recovery", "cns_freshness"}

    bonus_a, hits_a = conditioning._conditioning_clarification_bonus(
        ["anaerobic_alactic", "recovery"],
        derived_tags,
    )
    bonus_b, hits_b = conditioning._conditioning_clarification_bonus(
        ["glycolytic", "mental_toughness"],
        derived_tags,
    )

    assert bonus_a > 0
    assert set(hits_a) == {"anaerobic_alactic", "recovery"}
    assert bonus_b == 0.0
    assert hits_b == []


def test_bonus_is_capped():
    derived_tags = ["glycolytic", "conditioning", "work_capacity", "mental_toughness"]
    bonus, hits = conditioning._conditioning_clarification_bonus(
        ["glycolytic", "conditioning", "work_capacity", "mental_toughness"],
        derived_tags,
    )

    assert len(hits) == 4
    assert bonus <= conditioning.CONDITIONING_MAX_CLARIFICATION_TAG_BONUS
    assert bonus == conditioning.CONDITIONING_MAX_CLARIFICATION_TAG_BONUS


def test_fallback_uses_collision_details_when_priority_focus_missing_tags():
    resolved = conditioning._conditioning_resolve_derived_clarification_tags(
        {
            "goal_weakness_collision_details": [
                {"tag": "conditioning", "detail": "Repeated hard efforts"}
            ]
        }
    )

    assert set(resolved) == {"glycolytic", "work_capacity", "conditioning", "mental_toughness"}


def test_priority_focus_derived_tags_are_preferred_over_fallback():
    resolved = conditioning._conditioning_resolve_derived_clarification_tags(
        {
            "priority_focus": {"derived_clarification_tags": ["aerobic", "recovery"]},
            "goal_weakness_collision_details": [
                {"tag": "conditioning", "detail": "Late-round fatigue"}
            ],
        }
    )

    assert resolved == ["aerobic", "recovery"]
