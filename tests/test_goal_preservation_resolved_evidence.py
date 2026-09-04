from __future__ import annotations

from fightcamp.goal_preservation import collect_goal_evidence
from fightcamp.prescription_resolver import (
    _role_kind,
    apply_effective_strength_prescriptions,
    resolve_strength_slot_prescription,
)


def _calendar_day(d_day: int, weekday: str = "monday") -> dict:
    return {
        "weekday": weekday,
        "d_day": d_day,
        "is_fight_day": False,
        "is_after_fight_day": False,
    }


def test_alactic_speed_evidence_reads_serialized_selection_metadata():
    brief = {
        "athlete_snapshot": {"days_until_fight": 26},
        "restrictions": [],
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 2,
                    "phase": "SPP",
                    "calendar_days": [_calendar_day(16)],
                    "session_roles": [
                        {
                            "role_key": "alactic_speed_day",
                            "category": "conditioning",
                            "preferred_system": "alactic",
                            "session_index": 1,
                            "scheduled_day_hint": "Monday",
                            "scheduled_countdown_label": "D-16",
                        }
                    ],
                }
            ]
        },
        "candidate_pools": {
            "SPP": {
                "conditioning_slots": [
                    {
                        "slot_id": "spp_alactic_1",
                        "role": "alactic",
                        "session_index": 1,
                        "selected": {
                            "name": "Short Burst Repeat",
                            "prescription": "8 x 3s, full recovery",
                            "movement_patterns": ["speed"],
                            "selection_metadata": {
                                "primary_adaptation": "speed",
                                "secondary_adaptations": ["acceleration"],
                                "work_sec": 3,
                                "rest_sec": 60,
                                "rounds": 8,
                                "total_minutes": None,
                                "rpe": 6,
                                "impact_cost": "low",
                                "lactate_load": "low",
                                "movement_cost": "low",
                            },
                        },
                    }
                ]
            }
        },
    }

    evidence = collect_goal_evidence(brief)
    speed = [row for row in evidence if "speed_quality" in row["intents"]]

    assert len(speed) == 1
    assert speed[0]["d_day"] == 16
    assert speed[0]["work_sec"] == 3
    assert speed[0]["rounds"] == 8
    assert speed[0]["rest_sec"] == 60
    assert speed[0]["development_quality"] is True


def _hybrid_slot() -> dict:
    return {
        "slot_id": "spp_strength_hybrid",
        "session_index": 1,
        "role": "hinge",
        "quality_class": "anchor_power",
        "anchor_capable": True,
        "selected": {
            "name": "Heavy RDL → Broad Jump",
            "quality_class": "anchor_power",
            "anchor_capable": True,
            "support_only": False,
            "base_categories": [
                "lower_body_loaded",
                "lower_body_ballistic",
                "lower_body_power",
            ],
            "movement_patterns": ["hinge", "power", "speed"],
            "prescription": "3–5x3–5 @ 85–90% 1RM with contrast training (pair with explosive move).",
        },
    }


def _pure_power_slot() -> dict:
    return {
        "slot_id": "spp_strength_power",
        "session_index": 1,
        "role": "vertical_jump",
        "quality_class": "anchor_power",
        "anchor_capable": True,
        "selected": {
            "name": "Ballistic Box Jump",
            "quality_class": "anchor_power",
            "anchor_capable": True,
            "support_only": False,
            "base_categories": ["lower_body_ballistic", "lower_body_power"],
            "movement_patterns": ["power", "speed"],
            "prescription": "4–6x2–5 reps at max speed; full rest 60–120s.",
        },
    }


def _strength_role(d_day: int, *, loaded_allowed: bool = True) -> dict:
    return {
        "role_key": "strength_touch_day",
        "category": "strength",
        "strength_session_index": 1,
        "session_index": 1,
        "scheduled_day_hint": "Monday",
        "scheduled_countdown_label": f"D-{d_day}",
        "scheduled_d_day": d_day,
        "strength_dose_cap": {
            "max_sets": 2,
            "max_reps": 3,
            "loaded_allowed": loaded_allowed,
        },
        "rpe_cap": "6-7",
        "dose_adjustment_reason": "late_camp_reduced_strength_maintenance",
    }


def test_loaded_contrast_power_is_hybrid_and_keeps_loaded_authority():
    slot = _hybrid_slot()
    role = _strength_role(13)

    assert _role_kind(slot) == "hybrid"
    resolved = resolve_strength_slot_prescription(role=role, slot=slot)

    assert resolved["dose_role_kind"] == "hybrid"
    assert resolved["effective_loaded"] is True
    assert resolved["effective_max_sets"] == 2
    assert resolved["effective_max_reps"] == 3
    assert resolved["effective_prescription"] == "2 x 3 @ RPE 6-7 max"


def test_pure_ballistic_power_remains_non_loaded():
    slot = _pure_power_slot()
    role = _strength_role(13)

    assert _role_kind(slot) == "power"
    resolved = resolve_strength_slot_prescription(role=role, slot=slot)

    assert resolved["dose_role_kind"] == "power"
    assert resolved["effective_loaded"] is False


def test_loaded_hybrid_still_obeys_no_loaded_lifting_band():
    slot = _hybrid_slot()
    role = _strength_role(7, loaded_allowed=False)

    resolved = resolve_strength_slot_prescription(role=role, slot=slot)

    assert resolved["dose_role_kind"] == "hybrid"
    assert resolved["effective_loaded"] is False
    assert resolved["effective_prescription"].startswith("No loaded lifting")


def test_goal_evidence_counts_loaded_hybrid_as_strength_and_power():
    slot = _hybrid_slot()
    role = _strength_role(13)
    role_map = {
        "weeks": [
            {
                "week_index": 3,
                "phase": "SPP",
                "calendar_days": [_calendar_day(13)],
                "session_roles": [role],
            }
        ]
    }
    pools = {"SPP": {"strength_slots": [slot]}}

    apply_effective_strength_prescriptions(
        weekly_role_map=role_map,
        candidate_pools=pools,
        athlete_model={"fatigue": "low"},
    )
    brief = {
        "athlete_snapshot": {"days_until_fight": 26, "fatigue": "low"},
        "weekly_role_map": role_map,
        "candidate_pools": pools,
        "restrictions": [],
    }

    evidence = collect_goal_evidence(brief)
    witness = next(row for row in evidence if row.get("name") == "Heavy RDL → Broad Jump")

    assert witness["d_day"] == 13
    assert "meaningful_strength" in witness["intents"]
    assert "ballistic_power" in witness["intents"]
    assert witness["minimum_rpe"] == 6
    assert role["effective_strength_envelope"]["loaded_allowed"] is True
