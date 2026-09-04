"""Real intake -> selection -> calendar -> effective dose -> goal contract."""
import datetime as dt
import json
import logging
from pathlib import Path

import pytest

from fightcamp import input_parsing
from fightcamp.goal_preservation import collect_goal_evidence, validate_goal_preservation
from fightcamp.input_parsing import PlanInput
from fightcamp.plan_pipeline_blocks import generate_plan_blocks
from fightcamp.plan_pipeline_rendering import build_stage2_outputs
from fightcamp.plan_pipeline_runtime import RenderedPlanBundle, build_runtime_context


def _run(monkeypatch, **fixture_overrides):
    fixture = json.loads((Path(__file__).parent / "fixtures/goal_preservation/sheyi_like.json").read_text())
    fixture.update(fixture_overrides)
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: dt.datetime(2026, 1, 4, 12))
    fields = {
        "Full name": "Goal Preservation Regression",
        "Age": "28",
        "Weight (kg)": "77",
        "Target Weight (kg)": "77",
        "Height (cm)": "180",
        "Stance": "Orthodox",
        "Fighting Style (Technical)": fixture["sport"],
        "Professional Status": "amateur",
        "Rounds x Minutes": "3x5",
        "Weekly Training Frequency": str(fixture["training_frequency"]),
        "Fatigue Level": fixture["fatigue"],
        "Equipment Access": ", ".join(fixture["equipment"]),
        "Training Availability": ", ".join(fixture["training_days"]),
        "Hard Sparring Days": ", ".join(fixture["hard_sparring_days"]),
        "What are your key performance goals?": ", ".join(fixture["key_goals"]),
        "Primary goal": fixture["primary_goal"],
        "Fighting Style (Tactical)": fixture.get("tactical_style", ""),
        "Where do you feel weakest right now?": ", ".join(fixture["weaknesses"]),
        "Primary weak area": fixture["primary_weak_area"],
        "When is your next fight?": "2026-01-30",
    }
    plan_input = PlanInput.from_payload({"data": {"fields": [{"label": k, "value": v} for k, v in fields.items()]}})
    assert plan_input.days_until_fight == 26
    logger = logging.getLogger(__name__)
    context = build_runtime_context(plan_input=plan_input, random_seed=1, logger=logger)
    blocks = generate_plan_blocks(context=context, logger=logger, record_timing=lambda *args, **kwargs: None)
    rendered = RenderedPlanBundle(fight_plan_text="", coach_notes="", reason_log={}, html="")
    return build_stage2_outputs(context=context, blocks=blocks, rendered=rendered)


def test_sheyi_like_full_planner_never_credits_a_power_touch_as_strength(monkeypatch):
    payload, brief, handoff = _run(monkeypatch)
    assert {entry["goal"] for entry in brief["goal_preservation"]} == {"speed", "strength"}
    strength = next(entry for entry in brief["goal_preservation"] if entry["goal"] == "strength")
    # It must be an honest, independently revalidated state, even if current
    # safety/compression policy makes this particular camp impossible to cover.
    if strength["state"] == "defer":
        assert strength["constraints"]
        assert not any(e["goal"] == "strength" for e in validate_goal_preservation(brief))
    elif strength["satisfied"]:
        assert strength["evidence"]
        assert all(e["quality_class"] in {"anchor_loaded", "anchor_force_isometric"} for e in strength["evidence"])
    else:
        assert any(e["goal"] == "strength" for e in validate_goal_preservation(brief))
    evidence = collect_goal_evidence(brief)
    for week in brief["weekly_role_map"]["weeks"]:
        for role in week["session_roles"]:
            if role.get("effective_strength_envelope", {}).get("loaded_allowed") is False:
                assert not any(e.get("d_day") == role.get("scheduled_d_day") and e.get("role_key") == role["role_key"]
                               and "meaningful_strength" in e["intents"] for e in evidence)
                if role.get("intent_validation", {}).get("intent") == "meaningful_strength":
                    assert role["intent_validation"]["satisfied"] is False
    assert "goal_preservation" in handoff
    # The full persisted brief remains ordinary JSON; plans.planning_brief is
    # already stored as JSON text, so this addition requires no SQL migration.
    assert json.loads(json.dumps(brief))["goal_preservation"] == brief["goal_preservation"]


@pytest.mark.parametrize("fatigue", ["Low", "Moderate"])
def test_dense_three_hard_week_full_planner_respects_three_session_budget(monkeypatch, fatigue):
    _, brief, _ = _run(
        monkeypatch,
        sport="Boxing",
        training_frequency=3,
        training_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
        hard_sparring_days=["Monday", "Wednesday", "Friday"],
        fatigue=fatigue,
    )
    dense_weeks = [
        week for week in brief["weekly_role_map"]["weeks"]
        if {day.lower() for day in week.get("effective_hard_sparring_days", [])}
        == {"monday", "wednesday", "friday"}
        and min(day["d_day"] for day in week["calendar_days"]) > 13
    ]
    assert dense_weeks, "Exercise a normal-camp week with three resolved hard contacts"
    for week in dense_weeks:
        roles = week["session_roles"]
        assert len([role for role in roles if role["role_key"] == "hard_sparring_day"]) == 3
        assert not any(role.get("category") == "strength" for role in roles)
        assert any(
            role.get("category") == "strength" and role.get("compression_reason_codes")
            for role in week["suppressed_roles"]
        )


def test_sheyi_speed_audit_holds_unresolved_goal_failure(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    import api.stage2_automation as automation
    from api.generation.persistence import _apply_plan_contract_validation
    from api.state_machine import job_status_for_plan_status
    from support import FakeOpenAIClient

    payload, brief, handoff = _run(
        monkeypatch,
        hard_sparring_days=["Tuesday", "Friday"],
        tactical_style="pressure_fighter",
    )
    finding = {
        "code": "goal_preservation_failed",
        "goal": "speed",
        "satisfied": False,
        "missing_coverage": ["D14-D20"],
    }
    monkeypatch.setattr(automation, "validate_goal_preservation", lambda _: [finding])
    # Isolate deterministic goal failure from renderer divergence.
    monkeypatch.setattr(
        automation,
        "review_stage2_output",
        lambda **_: {
            "status": "PASS",
            "needs_retry": False,
            "validator_report": {"errors": [], "warnings": []},
        },
    )
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "0")
    text = """# MMA pressure fighter camp — Week 2
D-19 (Friday) — Hard sparring
D-18 (Saturday) — Tactical support
D-17 (Sunday) — Recovery
D-16 (Monday) — alactic_speed_day
D-15 (Tuesday) — Contact converted to technical
D-14 (Wednesday) — Conditioning
D-13 (Thursday) — Late-tail strength touch
"""
    client = FakeOpenAIClient(
        [SimpleNamespace(id="speed-regression", output_text=text)]
    )
    result = asyncio.run(
        automation.OpenAIStage2Automator(client=client, model="test").finalize(
            stage1_result={
                "plan_text": "Internal draft",
                "planning_brief": brief,
                "stage2_payload": payload,
                "stage2_handoff_text": handoff,
            }
        )
    )
    persisted = _apply_plan_contract_validation(
        result,
        fight_date=brief.get("fight_date"),
        athlete_id="test",
        job_id="test",
        emit_milestone=lambda *args, **kwargs: None,
    )
    assert persisted["plan_text"] == ""
    assert persisted["final_plan_text"] == text.strip()
    assert persisted["status"] == "review_required"
    assert job_status_for_plan_status(persisted["status"]) == "review_required"
    assert finding in persisted["stage2_validator_report"]["errors"]
    assert persisted["stage2_validator_report"]["is_athlete_releasable"] is False
    assert persisted["stage2_validator_report"]["release_decision"] == "hold"
    assert len(client.responses.calls) == 1
    assert persisted["stage2_attempt_count"] == 1
