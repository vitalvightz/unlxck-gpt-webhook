from __future__ import annotations

from copy import deepcopy

from fightcamp.pre_hard_contact_strength import (
    PRE_HARD_CONTACT_STRENGTH_CAP_REASON,
    apply_pre_hard_contact_strength_exposure_cap,
)
from fightcamp.prescription_resolver import apply_effective_strength_prescriptions


def _calendar(*pairs: tuple[str, int]) -> list[dict]:
    return [{"weekday": day, "d_day": d_day} for day, d_day in pairs]


def _strength(day: str, *, session_index: int = 1, strength_session_index: int = 1) -> dict:
    return {
        "category": "strength",
        "role_key": "primary_strength_day" if strength_session_index == 1 else "secondary_strength_day",
        "preferred_pool": "strength_slots",
        "scheduled_day_hint": day,
        "session_index": session_index,
        "strength_session_index": strength_session_index,
    }


def _hard(day: str, *, load: str = "hard", status: str = "hard_as_planned") -> dict:
    return {"day": day, "status": status, "effective_load": load}


def _map(
    *,
    strength_day: str = "Monday",
    strength_d_day: int = 23,
    hard_day: str = "Tuesday",
    hard_d_day: int = 22,
    load: str = "hard",
    extra_roles: list[dict] | None = None,
) -> dict:
    roles = [_strength(strength_day)] + list(extra_roles or [])
    week = {
        "week_index": 1,
        "phase": "GPP",
        "declared_training_days": [strength_day, hard_day, "Thursday"],
        "calendar_days": _calendar(
            (strength_day, strength_d_day),
            (hard_day, hard_d_day),
            ("Thursday", min(strength_d_day, hard_d_day) - 2),
        ),
        "hard_sparring_plan": [
            _hard(
                hard_day,
                load=load,
                status="hard_as_planned" if load == "hard" else "technical_only",
            )
        ],
        "effective_hard_sparring_days": [hard_day] if load == "hard" else [],
        "session_roles": roles,
        "suppressed_roles": [],
    }
    return {"model": "session_role_overlay.v1", "weeks": [week]}


def _anchor_slot(*, prescription: str = "3 x 10 @ 65% 1RM, tempo 3-1-1") -> dict:
    return {
        "slot_id": "gpp-strength-1-anchor",
        "session_index": 1,
        "priority": "primary",
        "role": "hinge",
        "anchor_capable": True,
        "selected": {
            "name": "Romanian Deadlift (RDL)",
            "prescription": prescription,
            "selection_metadata": {
                "eccentric_cost": "high",
                "soreness_risk": "high",
                "impact_cost": "low",
                "landing_cost": "none",
            },
        },
    }


def _high_cost_power_slot() -> dict:
    return {
        "slot_id": "gpp-strength-1-power",
        "session_index": 1,
        "priority": "secondary",
        "role": "jump",
        "quality_class": "anchor_power",
        "selected": {
            "name": "Single-Leg Forward Hops",
            "prescription": "3 x 5",
            "quality_class": "anchor_power",
            "selection_metadata": {
                "impact_cost": "high",
                "landing_cost": "high",
                "eccentric_cost": "moderate",
                "soreness_risk": "moderate",
            },
        },
    }


def _low_cost_support_slot() -> dict:
    return {
        "slot_id": "gpp-strength-1-support",
        "session_index": 1,
        "priority": "support",
        "role": "anti_rotation",
        "support_only": True,
        "selected": {
            "name": "Anti-Rotation Hold",
            "prescription": "2 x 6",
            "support_only": True,
            "selection_metadata": {
                "impact_cost": "none",
                "landing_cost": "none",
                "eccentric_cost": "low",
                "soreness_risk": "low",
            },
        },
    }


def _candidate_pools(*slots: dict) -> dict:
    return {"GPP": {"strength_slots": list(slots)}}


def _role(weekly: dict) -> dict:
    return weekly["weeks"][0]["session_roles"][0]


def test_one_day_before_effective_hard_contact_marks_strength_and_reuses_retention_cap() -> None:
    weekly = _map()
    apply_pre_hard_contact_strength_exposure_cap(weekly)
    role = _role(weekly)
    assert role["pre_hard_contact_managed_stress"] is True
    assert role["pre_hard_contact_effective_hard_distance"] == 1

    apply_effective_strength_prescriptions(
        weekly_role_map=weekly,
        candidate_pools=_candidate_pools(_anchor_slot()),
        athlete_model={"fatigue": "low"},
    )
    role = _role(weekly)
    assert role["strength_dose_cap"] == {
        "max_sets": 3,
        "max_reps": 3,
        "loaded_allowed": True,
    }
    assert role["rpe_cap"] == "6-7"
    assert role["effective_strength_prescriptions"][0]["effective_prescription"] == "3 x 3 @ RPE 6-7 max"


def test_two_days_before_effective_hard_contact_does_not_trigger() -> None:
    weekly = _map(strength_day="Sunday", strength_d_day=24, hard_d_day=22)
    before = deepcopy(weekly)
    apply_pre_hard_contact_strength_exposure_cap(weekly)
    assert weekly == before

    apply_effective_strength_prescriptions(
        weekly_role_map=weekly,
        candidate_pools=_candidate_pools(_anchor_slot()),
        athlete_model={"fatigue": "low"},
    )
    role = _role(weekly)
    assert "pre_hard_contact_managed_stress" not in role
    assert "effective_strength_prescriptions" not in role


def test_declared_contact_resolved_to_technical_does_not_trigger() -> None:
    weekly = _map(load="technical")
    before = deepcopy(weekly)
    apply_pre_hard_contact_strength_exposure_cap(weekly)
    assert weekly == before


def test_pre_hard_week_keeps_one_strength_role_and_records_suppression() -> None:
    secondary = _strength("Thursday", session_index=2, strength_session_index=2)
    weekly = _map(extra_roles=[secondary])
    apply_pre_hard_contact_strength_exposure_cap(weekly)

    week = weekly["weeks"][0]
    strength_roles = [role for role in week["session_roles"] if role.get("category") == "strength"]
    assert len(strength_roles) == 1
    assert strength_roles[0]["role_key"] == "primary_strength_day"
    assert strength_roles[0]["pre_hard_contact_managed_stress"] is True

    suppressed = [row for row in week["suppressed_roles"] if row.get("category") == "strength"]
    assert len(suppressed) == 1
    assert suppressed[0]["compression_reason_codes"] == [PRE_HARD_CONTACT_STRENGTH_CAP_REASON]
    assert suppressed[0]["governance"]["hard_suppression_reasons"]
    assert PRE_HARD_CONTACT_STRENGTH_CAP_REASON in week["intentional_compression"]["reason_codes"]


def test_pre_hard_retention_cap_stacks_with_existing_high_fatigue_reduction() -> None:
    weekly = _map()
    apply_pre_hard_contact_strength_exposure_cap(weekly)
    apply_effective_strength_prescriptions(
        weekly_role_map=weekly,
        candidate_pools=_candidate_pools(_anchor_slot()),
        athlete_model={"fatigue": "high"},
    )
    assert _role(weekly)["effective_strength_prescriptions"][0]["effective_prescription"] == "2 x 3 @ RPE 6-7 max"


def test_stricter_existing_countdown_cap_wins_over_pre_hard_retention_cap() -> None:
    weekly = _map()
    apply_pre_hard_contact_strength_exposure_cap(weekly)
    role = _role(weekly)
    role.update(
        {
            "strength_dose_cap": {"max_sets": 2, "max_reps": 3, "loaded_allowed": True},
            "rpe_cap": "6-7",
            "dose_adjustment_reason": "late_camp_reduced_strength_maintenance",
        }
    )
    apply_effective_strength_prescriptions(
        weekly_role_map=weekly,
        candidate_pools=_candidate_pools(_anchor_slot()),
        athlete_model={"fatigue": "low"},
    )
    assert _role(weekly)["effective_strength_prescriptions"][0]["effective_prescription"] == "2 x 3 @ RPE 6-7 max"
    assert _role(weekly)["dose_adjustment_reason"] == "late_camp_reduced_strength_maintenance"


def test_pre_hard_allow_list_drops_high_impact_power_but_keeps_anchor() -> None:
    weekly = _map()
    apply_pre_hard_contact_strength_exposure_cap(weekly)
    apply_effective_strength_prescriptions(
        weekly_role_map=weekly,
        candidate_pools=_candidate_pools(_anchor_slot(), _high_cost_power_slot()),
        athlete_model={"fatigue": "low"},
    )
    role = _role(weekly)
    names = [item["name"] for item in role["effective_strength_prescriptions"]]
    assert names == ["Romanian Deadlift (RDL)"]
    envelope = role["effective_strength_envelope"]
    assert envelope["complete_exercise_allow_list"] is True
    assert envelope["allowed_exercise_names"] == ["Romanian Deadlift (RDL)"]
    assert envelope["forbid_slow_eccentric_emphasis"] is True


def test_pre_hard_allow_list_permits_one_low_cost_support_item() -> None:
    weekly = _map()
    apply_pre_hard_contact_strength_exposure_cap(weekly)
    apply_effective_strength_prescriptions(
        weekly_role_map=weekly,
        candidate_pools=_candidate_pools(_anchor_slot(), _low_cost_support_slot()),
        athlete_model={"fatigue": "low"},
    )
    names = [item["name"] for item in _role(weekly)["effective_strength_prescriptions"]]
    assert names == ["Romanian Deadlift (RDL)", "Anti-Rotation Hold"]


def test_clean_week_without_next_day_hard_contact_is_unchanged() -> None:
    weekly = _map(strength_day="Thursday", strength_d_day=20, hard_day="Tuesday", hard_d_day=22)
    before = deepcopy(weekly)
    apply_pre_hard_contact_strength_exposure_cap(weekly)
    assert weekly == before


def test_goal_deferral_contract_recognises_pre_hard_strength_cap() -> None:
    from fightcamp.goal_preservation import _deferral_constraints

    brief = {
        "athlete_snapshot": {"days_until_fight": 24},
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "calendar_days": [{"weekday": "Monday", "d_day": 23}],
                    "session_roles": [],
                    "suppressed_roles": [
                        {
                            "category": "strength",
                            "role_key": "secondary_strength_day",
                            "compression_reason_codes": [
                                PRE_HARD_CONTACT_STRENGTH_CAP_REASON
                            ],
                        }
                    ],
                }
            ]
        },
    }
    missing = [{"min_d_day": 20, "max_d_day": 24}]
    constraints = _deferral_constraints({"goal": "strength"}, brief, missing)
    assert constraints
    assert constraints[0]["reason_code"] == "pre_hard_contact_managed_stress"
    assert constraints[0]["source_reason_code"] == PRE_HARD_CONTACT_STRENGTH_CAP_REASON
