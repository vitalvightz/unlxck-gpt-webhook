from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from api.models import PlanRequest
from fightcamp.camp_week_fillers import apply_camp_week_fillers
from fightcamp.gap_fill_inserts import (
    build_target_coverage_state,
    select_gap_fill_insert,
)
from fightcamp.input_parsing import PlanInput
from fightcamp.plan_pipeline_runtime import build_runtime_context


def _base_athlete(**overrides):
    athlete = {
        "sport": "boxing",
        "status": "professional",
        "training_days": ["monday", "wednesday", "friday"],
        "hard_sparring_days": [],
        "fatigue": "low",
        "fatigue_level": "low",
        "readiness_flags": [],
        "weight_cut_risk": False,
        "weight_cut_pct": 0.0,
        "weaknesses": [],
        "key_goals": [],
        "injuries": [],
        "parsed_injuries": [],
        "guided_injury": None,
        "injury_restrictions": [],
        "days_until_fight": 21,
        "plan_creation_weekday": "monday",
    }
    athlete.update(overrides)
    return athlete


def _supports(role: dict, target: str) -> bool:
    return float((role.get("support_target_capabilities") or {}).get(target, 0.0)) > 0


def _runtime_weakness(label: str) -> str:
    request = PlanRequest(
        athlete={
            "full_name": "Ari Mensah",
            "technical_style": ["boxing"],
            "tactical_style": [],
        },
        fight_date=(datetime.now(timezone.utc).date() + timedelta(days=42)).isoformat(),
        training_availability=["Monday", "Wednesday", "Friday"],
        weak_areas=[label],
        primary_weak_area=label,
    )
    parsed = PlanInput.from_payload(request.to_payload())
    context = build_runtime_context(
        plan_input=parsed,
        random_seed=1,
        logger=logging.getLogger(__name__),
    )
    assert len(context.training_context.weaknesses) == 1
    return context.training_context.weaknesses[0]


def _fight_dated_spp_week(*, partial_role: dict | None = None) -> dict:
    roles = [
        {
            "role_key": "primary_strength_day",
            "category": "strength",
            "scheduled_day_hint": "Monday",
            "countdown_offset": 14,
            "governance": {"meaningful_stress": True},
        }
    ]
    if partial_role is not None:
        roles.append(partial_role)
    return {
        "phase": "SPP",
        "session_roles": roles,
        "calendar_days": [
            {"weekday": "monday", "d_day": 14},
            {"weekday": "wednesday", "d_day": 12},
        ],
        "declared_training_days": ["Monday", "Wednesday"],
        "intentionally_unused_days": [{"day": "Wednesday", "role": "off_day"}],
    }


def _discretionary_roles(week: dict) -> list[dict]:
    return [
        role
        for role in week["session_roles"]
        if role.get("camp_week_filler") and role.get("role_key") != "tactical_watch"
    ]


def test_real_hip_mobility_intake_reaches_mobility_filler_family():
    runtime_weakness = _runtime_weakness("Hip Mobility")
    assert runtime_weakness == "hip mobility"

    athlete = _base_athlete(
        weaknesses=[runtime_weakness],
        primary_weak_area=runtime_weakness,
    )
    state = build_target_coverage_state(athlete)[0]
    insert = select_gap_fill_insert(athlete, 12)

    assert state.target == "mobility"
    assert state.low_cost_addressable is True
    assert state.remaining_need == 1.0
    assert insert is not None
    assert _supports(insert, "mobility")


def test_live_normal_camp_partial_coverage_lets_coordination_take_the_slot():
    athlete = _base_athlete(
        weaknesses=["mobility", "coordination"],
        primary_weak_area="mobility",
        technical_styles=["boxing"],
        tactical_styles=["distance_striker"],
        equipment=[],
    )
    partial_mobility = {
        "role_key": "joint_prep",
        "category": "support_insert",
        "governance": {"meaningful_stress": False},
    }
    states = build_target_coverage_state(athlete, [partial_mobility])
    by_target = {state.target: state for state in states}

    assert by_target["mobility"].priority_weight == 0.9
    assert by_target["mobility"].remaining_need == 0.25
    assert by_target["coordination"].priority_weight == 0.45
    assert by_target["coordination"].remaining_need == 1.0

    week = _fight_dated_spp_week(partial_role=partial_mobility)
    apply_camp_week_fillers({"weeks": [week]}, athlete)

    discretionary = _discretionary_roles(week)
    assert len(discretionary) == 1
    assert discretionary[0]["role_key"] == "coordination_support"
    assert _supports(discretionary[0], "coordination")


def test_live_normal_camp_keeps_generic_mobility_when_it_has_more_opportunity():
    athlete = _base_athlete(
        weaknesses=["mobility", "coordination"],
        primary_weak_area="mobility",
        technical_styles=["boxing"],
        tactical_styles=["distance_striker"],
        equipment=[],
    )
    week = _fight_dated_spp_week()

    apply_camp_week_fillers({"weeks": [week]}, athlete)

    discretionary = _discretionary_roles(week)
    assert len(discretionary) == 1
    assert discretionary[0]["role_key"] != "coordination_support"
    assert _supports(discretionary[0], "mobility")