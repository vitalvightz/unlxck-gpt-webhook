from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest

from api.models import PlanRequest
from fightcamp.gap_fill_inserts import build_target_coverage_state, select_gap_fill_insert
from fightcamp.input_parsing import PlanInput
from fightcamp.plan_pipeline_runtime import build_runtime_context


def _runtime_goal(label: str) -> str:
    request = PlanRequest(
        athlete={
            "full_name": "Ari Mensah",
            "technical_style": ["boxing"],
            "tactical_style": [],
        },
        fight_date=(datetime.now(timezone.utc).date() + timedelta(days=42)).isoformat(),
        training_availability=["Monday", "Wednesday", "Friday"],
        key_goals=[label],
        primary_goal=label,
    )
    parsed = PlanInput.from_payload(request.to_payload())
    context = build_runtime_context(
        plan_input=parsed,
        random_seed=1,
        logger=logging.getLogger(__name__),
    )
    assert len(context.training_context.key_goals) == 1
    return context.training_context.key_goals[0]


def _coverage_athlete(runtime_goal: str) -> dict:
    return {
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
        "key_goals": [runtime_goal],
        # Stage 2 resolves the primary against the normalized key-goal list before
        # fillers consume the athlete model. Mirror that canonical state here.
        "primary_goal": runtime_goal,
        "injuries": [],
        "parsed_injuries": [],
        "guided_injury": None,
        "injury_restrictions": [],
        "days_until_fight": 21,
        "plan_creation_weekday": "monday",
    }


@pytest.mark.parametrize("label", ["Speed", "Speed / Reaction"])
def test_runtime_speed_labels_reach_low_cost_speed_target(label: str):
    runtime_goal = _runtime_goal(label)
    assert runtime_goal == "reactive"

    athlete = _coverage_athlete(runtime_goal)
    state = build_target_coverage_state(athlete)[0]
    insert = select_gap_fill_insert(athlete, 12)

    assert state.target == "speed"
    assert state.low_cost_addressable is True
    assert state.remaining_need == 1.0
    assert insert is not None
    assert float((insert.get("support_target_capabilities") or {}).get("speed", 0.0)) > 0


def test_runtime_explosive_label_projects_to_power_without_fake_low_cost_repair():
    runtime_goal = _runtime_goal("Power & Explosiveness")
    assert runtime_goal == "explosive"

    athlete = _coverage_athlete(runtime_goal)
    state = build_target_coverage_state(athlete)[0]
    insert = select_gap_fill_insert(athlete, 12)

    assert state.target == "power"
    assert state.low_cost_addressable is False
    assert state.remaining_need == 1.0
    assert insert is not None
    assert "power" not in (insert.get("support_target_capabilities") or {})
