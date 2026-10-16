"""Read-only, identity-free snapshot of plan be6c9e91 (16 October 2026).

Only programming and its saved template are retained, never athlete records.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

from api.services.effective_structured_plan import resolve_effective_structured_plan
from api.plan_mappers import _map_plan_detail
from api.services.open_plan_timeline import WEEKDAYS, project_open_structured_plan
from api.services.today_service import _structured_day_for_training_day, _structured_today_session_entry, upsert_session_completion
from api.services.week_progress import _planned_session_ids
from api.structured_plan_deterministic_fallback import _exact_working_dose, _lift_dose_fields
from api.structured_plan_generation import _merge_locked_content, _open_plan_contract_errors
from api.structured_plan_models import safe_parse_structured_plan
from fightcamp.weekly_schedule_view import normalize_weekday
from test_structured_plan_models import _valid_plan
from tests.support import FakeStore


def _reference_row():
    reference = json.loads((Path(__file__).parent / "fixtures/open_plan_development_reference.json").read_text(encoding="utf-8"))
    structured = _valid_plan()
    structured["weeks"] = [reference["stored_week"]]
    structured["plan_metadata"]["plan_type"] = "open_ongoing_system"
    structured["event_context"] = {"event_type": "none"}
    structured["countdown_labels"] = []
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "created_at": "2026-10-13T09:00:00Z", "fight_date": None,
        "planning_brief": {"open_plan_spec": reference["open_plan_spec"]},
        "structured_plan": structured,
    }


def _project(row):
    effective = resolve_effective_structured_plan(row)
    assert effective is not None
    assert safe_parse_structured_plan(effective).ok
    projected, context = project_open_structured_plan(row, effective, current_training_day="2026-10-13")
    assert context["projection_status"] == "projected"
    return effective, projected


def test_reference_keeps_each_weeks_actual_sessions_exercises_doses_and_flexible_guidance():
    row = _reference_row()
    original = copy.deepcopy(row)
    effective, projected = _project(row)
    decisions = row["planning_brief"]["open_plan_spec"]["weekly_session_plan"]["weeks"]
    original_guidance = {
        block["display_name"]: block["progression_rule"]
        for day in row["structured_plan"]["weeks"][0]["days"]
        for session in day["sessions"] for block in session["blocks"]
    }
    for week, decision in zip(projected["weeks"], decisions, strict=True):
        assert [day["weekday"] for day in week["days"]] == list(WEEKDAYS)
        for day in week["days"]:
            planned = [s for s in decision["sessions"] if normalize_weekday(s["weekday"]) == day["weekday"]]
            app = [s for s in planned if not s.get("coach_owned") and s.get("category") != "sparring"]
            actual = [s for s in day["sessions"] if not s["title"].startswith("Tactical Focus")]
            assert [s["title"] for s in actual] == [s["label"] for s in app]
            assert len({s["session_id"] for s in day["sessions"]}) == len(day["sessions"])
            for session, programmed in zip(actual, app, strict=True):
                exercises = programmed.get("exercises") or []
                if not exercises:  # Legacy support carries its label, no invented dose.
                    assert session["blocks"] == []
                else:
                    assert [b["display_name"] for b in session["blocks"]] == [e["name"] for e in exercises]
                    for block, exercise in zip(session["blocks"], exercises, strict=True):
                        dose, _ = _lift_dose_fields(_exact_working_dose(exercise["prescription"]))
                        assert all(block.get(key) == value for key, value in dose.items())
                        assert block["progression_rule"] == original_guidance[exercise["name"]]
            if day["weekday"] in {"Wed", "Sun"}:
                assert day["sessions"] == []
                assert day["today_card"]["headline"] == "Unavailable"
            if day["weekday"] == "Mon":
                assert day["sessions"] == []
                assert day["today_card"]["headline"] == "No session planned"
            if day["weekday"] in {"Tue", "Thu", "Fri"}:
                assert day["today_card"]["coach_led_contact"]
    assert row == original  # Response-only repair; saved plans are never mutated.
    assert resolve_effective_structured_plan({**row, "structured_plan": effective}) == effective


def test_new_conversion_persists_four_weeks_and_preserves_tactical_rotation():
    row = _reference_row()
    converted = _merge_locked_content(row["structured_plan"], row["planning_brief"])
    assert _open_plan_contract_errors(converted, row["planning_brief"]) == []
    assert safe_parse_structured_plan(converted).ok
    watches = [
        (week["week_index"], day["weekday"], block["display_name"])
        for week in converted["weeks"] for day in week["days"] for session in day["sessions"]
        if session["title"].startswith("Tactical Focus") for block in session["blocks"]
    ]
    assert watches == [(1, "Fri", "Attack Trigger Map (MMA)"), (3, "Fri", "Safe Counter Range (MMA)")]


@pytest.mark.parametrize("stored_week_count", [1, 4])
def test_week_specific_doses_come_from_the_planner_without_automatic_progression(stored_week_count):
    row = _reference_row()
    row["structured_plan"]["weeks"] = [
        {**copy.deepcopy(row["structured_plan"]["weeks"][0]), "week_index": index + 1}
        for index in range(stored_week_count)
    ]
    decisions = row["planning_brief"]["open_plan_spec"]["weekly_session_plan"]["weeks"]
    strength = next(s for s in decisions[1]["sessions"] if s["category"] == "strength")
    strength["exercises"][0]["prescription"] = "2x3 reps at max speed; full rest 120s."
    _, projected = _project(row)
    doses = [next(b for day in week["days"] for s in day["sessions"] for b in s["blocks"]
                  if b["display_name"] == "Barbell Thruster") for week in projected["weeks"]]
    assert [(b["sets"], b["reps"]) for b in doses] == [(4, 2), (2, 3), (4, 2), (4, 2)]
    assert len({b["progression_rule"] for b in doses}) == 1


def test_explicit_recovery_day_survives_deterministic_week_reconciliation():
    row = _reference_row()
    day = row["structured_plan"]["weeks"][0]["days"][0]
    day["day_type"] = "recovery"
    day["today_card"]["headline"] = "Prescribed recovery"
    _, projected = _project(row)
    assert all(week["days"][0]["day_type"] == "recovery" for week in projected["weeks"])
    assert all(week["days"][0]["today_card"]["headline"] == "Prescribed recovery" for week in projected["weeks"])


def test_new_support_sessions_keep_their_planner_authored_instruction():
    row = _reference_row()
    decision = row["planning_brief"]["open_plan_spec"]["weekly_session_plan"]["weeks"][1]
    support = next(s for s in decision["sessions"] if s["role_key"] == "joint_prep")
    instruction = "Use the prescribed joint preparation at an easy pace."
    support["display_text"] = instruction
    _, projected = _project(row)
    session = next(s for day in projected["weeks"][1]["days"] for s in day["sessions"] if s["title"] == "Joint Prep")
    assert session["objective"] == instruction
    assert not session["blocks"]


def test_restoring_a_dropped_exercise_keeps_the_existing_session_identity():
    row = _reference_row()
    strength = next(s for day in row["structured_plan"]["weeks"][0]["days"] for s in day["sessions"] if s["title"] == "Strength")
    existing_id = strength["session_id"]
    strength["blocks"].pop()
    _, projected = _project(row)
    for week in projected["weeks"]:
        session = next(s for day in week["days"] for s in day["sessions"] if s["title"] == "Strength")
        assert session["session_id"] == existing_id
        assert len(session["blocks"]) == 6


def test_completion_and_week_xp_ignore_empty_days_and_use_the_correct_week():
    row = _reference_row()
    effective, projected = _project(row)
    for week in projected["weeks"]:
        expected_ids = {s["session_id"] for day in week["days"] for s in day["sessions"]}
        assert _planned_session_ids(week) == expected_ids
        for day in week["days"]:
            resolved = _structured_day_for_training_day(row, day["date"])
            assert resolved is not None
            assert resolved[0]["sessions"] == day["sessions"]
            if day["weekday"] in {"Mon", "Wed", "Sun"}:
                assert _structured_today_session_entry(row, day["date"]) is None
    # Adding display-only calendar rows never changes an existing session id.
    original_ids = {s["title"]: s["session_id"] for day in row["structured_plan"]["weeks"][0]["days"] for s in day["sessions"]}
    for day in effective["weeks"][0]["days"]:
        for session in day["sessions"]:
            if session["title"] in original_ids:
                assert session["session_id"] == original_ids[session["title"]]


@pytest.mark.parametrize("day", ["2026-10-14", "2026-10-18"])
def test_unavailable_calendar_days_reject_completion_without_session_or_xp_writes(day):
    row = {**_reference_row(), "athlete_id": "athlete-1", "status": "ready"}
    store = FakeStore()
    store.plans[row["id"]] = row
    store.set_active_plan_id("athlete-1", row["id"])
    with pytest.raises(HTTPException) as error:
        upsert_session_completion(
            store, athlete_id="athlete-1", athlete_timezone="",
            payload={"plan_id": row["id"], "session_id": day, "status": "done"},
            now=datetime.fromisoformat(day + "T12:00:00").replace(tzinfo=timezone.utc),
        )
    assert error.value.status_code in {409, 422}
    assert not store.session_completions.get("athlete-1")
    assert not store.xp_awards.get("athlete-1")


@pytest.mark.parametrize("four_weeks", [False, True])
def test_legacy_templates_preserve_recovery_and_never_invent_gap_sessions(four_weeks):
    row = _reference_row()
    del row["planning_brief"]["open_plan_spec"]["weekly_session_plan"]
    recovery = row["structured_plan"]["weeks"][0]["days"][0]
    recovery["day_type"] = "recovery"
    recovery["today_card"]["headline"] = "Prescribed recovery"
    if four_weeks:
        row["structured_plan"]["weeks"] *= 4
    _, projected = _project(row)
    assert len(projected["weeks"]) == 4
    for week in projected["weeks"]:
        assert [day["weekday"] for day in week["days"]] == list(WEEKDAYS)
        assert week["days"][0]["today_card"]["headline"] == "Prescribed recovery"
        assert week["days"][0]["day_type"] == "recovery"
        assert week["days"][2]["sessions"] == week["days"][6]["sessions"] == []


@pytest.mark.parametrize("available", [
    ["Mon", "Tue", "Thu", "Fri"],
    ["Mon", "Tue", "Thu", "Fri", "Sat"],
    ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
    list(WEEKDAYS),
])
def test_plan_detail_calendar_is_complete_for_historical_availability_shapes(available):
    row = {**_reference_row(), "athlete_id": "athlete-1", "status": "ready"}
    spec = row["planning_brief"]["open_plan_spec"]
    spec.pop("weekly_session_plan")
    spec.pop("tactical_watch")
    spec["weekly_template"] = {"training_days": available}
    week = row["structured_plan"]["weeks"][0]
    empty = copy.deepcopy(week["days"][0])
    strength = copy.deepcopy(next(s for d in week["days"] for s in d["sessions"] if s["title"] == "Strength"))
    week["days"] = [{**copy.deepcopy(empty), "weekday": weekday} for weekday in available]
    week["days"][0].update(day_type="high", sessions=[strength])
    original = copy.deepcopy(row)
    detail = _map_plan_detail(row, include_admin=False, current_training_day="2026-10-13")
    assert detail.schedule_context.projection_status == "projected"
    for resolved in detail.outputs.structured_plan.weeks:
        assert [day.weekday for day in resolved.days] == list(WEEKDAYS)
        for day in resolved.days:
            if day.weekday not in available:
                assert day.sessions == []
                assert day.today_card.headline == "Unavailable"
        assert resolved.days[0].sessions[0].session_id == strength["session_id"]
    assert row == original


@pytest.mark.parametrize("saved_contact_flag", [True, False])
def test_final_plan_detail_preserves_coach_led_sparring_headline_and_load(saved_contact_flag):
    row = {**_reference_row(), "athlete_id": "athlete-1", "status": "ready"}
    if not saved_contact_flag:
        for day in row["structured_plan"]["weeks"][0]["days"]:
            day["today_card"].pop("coach_led_contact", None)
    detail = _map_plan_detail(row, include_admin=False, current_training_day="2026-10-13")
    assert detail.schedule_context.projection_status == "projected"
    for week in detail.outputs.structured_plan.weeks:
        for day in week.days:
            if day.weekday in {"Tue", "Thu"}:
                assert day.day_type == "high"
                assert day.today_card.headline == "Hard sparring"
                if saved_contact_flag:
                    assert day.today_card.coach_led_contact == "Hard sparring"
                assert day.sessions == []
