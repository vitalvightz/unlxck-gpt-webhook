"""Minimal programming facts from read-only plan be6c9e91 (16 October 2026).

Only programming and its saved template are retained, never athlete records.
"""
from __future__ import annotations

import copy

from fightcamp.coaching_copy import is_null_progression
from datetime import datetime, timezone

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
from fightcamp.tactical_watch_library import all_watches, watch_metadata
from test_structured_plan_models import _valid_plan
from tests.support import FakeStore


def _reference_row():
    # Keep the actual decisions/doses/identities, without copying an entire
    # saved card or duplicating bank-owned tactical instructions in a snapshot.
    structured = _valid_plan()
    week = structured["weeks"][0]
    day_template = copy.deepcopy(week["days"][0])
    session_template = copy.deepcopy(day_template["sessions"][0])
    names = ["Barbell Thruster", "Med-Ball Rotational Slam", "Trap Bar Jump",
             "Single-Leg Depth Drop (Stick Landing)", "Landmine Anti-Rotation Press",
             "Single-Leg Romanian Deadlift Hold"]
    prescriptions = ["4x2 reps at max speed; full rest 120s."] * 4 + [
        "2 sets x 6 reps or 20s tempo (3-1-3), RPE 6.", "2 x 20s hold @ RPE 6; rest 60s."]
    exercises = [{"name": name, "prescription": dose} for name, dose in zip(names, prescriptions, strict=True)]
    aerobic = {"label": "Aerobic support", "weekday": "Friday", "category": "conditioning",
               "role_key": "aerobic_base_day", "execution_order": 2,
               "exercises": [{"name": "Read & Counter Flow", "prescription": "3 x 180s work / 60s rest"}]}
    strength = {"label": "Strength", "weekday": "Saturday", "category": "strength",
                "role_key": "primary_strength_day", "execution_order": 2, "exercises": exercises}
    decisions = []
    for index, (label, role) in enumerate([
        ("Shot-Line Circle-Off Reset", "footwork_walkthrough"), ("Joint Prep", "joint_prep"),
        ("Fence Exit to Center Rebase", "footwork_walkthrough"), ("Easy Walk Flush", "walk_flush"),
    ], start=1):
        support = {"label": label, "weekday": "Saturday", "category": "support_insert",
                   "role_key": role, "execution_order": 2 if index == 4 else 1}
        lift = copy.deepcopy(strength)
        lift["execution_order"] = 1 if index == 4 else 2
        decisions.append({"week": index, "sessions": [
            {"label": "Hard sparring", "weekday": "Tuesday", "category": "sparring",
             "role_key": "hard_sparring_day", "execution_order": 2 if index in (1, 3) else 1},
            {"label": "Hard sparring", "weekday": "Thursday", "category": "sparring",
             "role_key": "hard_sparring_day", "execution_order": 1},
            {"label": "Light technical combat", "weekday": "Friday", "category": "technical",
             "role_key": "light_combat_day", "coach_owned": True, "execution_order": 1},
            copy.deepcopy(aerobic), *([lift, support] if index == 4 else [support, lift]),
        ]})
    rotation = []
    for index, key in [(1, "mma.counter_striker.gpp.attack_trigger_map"), (3, "mma.counter_striker.gpp.safe_counter_range")]:
        watch = next(watch for watch in all_watches() if watch.key == key)
        rotation.append({"week": index, "label": "Tactical Focus", "name": watch.name,
                         "tactical_watch": watch_metadata(watch)["tactical_watch"]})
    spec = {"plan_type": "open_ongoing_system", "weekly_template": {
        "training_days": ["Monday", "Tuesday", "Thursday", "Friday", "Saturday"],
        "hard_sparring_days": ["Tuesday", "Thursday"], "support_work_days": ["Friday"],
        "coach_owned_days": {"hard_sparring_days": ["Tuesday", "Thursday"], "support_work_days": ["Friday"]}},
        "weekly_session_plan": {"authority": "deterministic_open_development_block", "weeks": decisions},
        "tactical_watch": {"weekly_rotation": rotation}}
    # Explicit actionable AI fixtures for the current movement. Numerical
    # advancement is tested separately against real exposure authority.
    easier_and_stop = [
        (["Use lighter load."], ["Stop if balance or control lost."]),
        (["Ease movement force."], ["Stop if low-back pain appears."]),
        (["Reduce jump height."], ["Stop if landing becomes stiff or uncontrolled."]),
        (["Use a lower landing height."], ["Stop if you cannot land quietly and hold."]),
        (["Use a smaller pain-free range."], ["Stop if twisting at the hips happens."]),
        (["Use a supported stance."], ["Stop if hip drops or sharp hamstring pain."]),
    ]
    source_blocks = []
    for index, name in enumerate(names):
        dose = {"sets": 4, "reps": 2, "rest": {"value": 120, "unit": "seconds"}}
        if index == 4:
            dose = {"sets": 2, "reps": 6, "rest": {"value": 90, "unit": "seconds"},
                    "tempo": {"eccentric": 3, "pause_bottom": 1, "concentric": 3, "pause_top": 0}}
        elif index == 5:
            dose = {"sets": 2, "duration": {"value": 20, "unit": "seconds"}, "rest": {"value": 60, "unit": "seconds"}}
        source_blocks.append({"block_id": f"saved-strength-{index}", "block_type": "strength", "display_name": name,
                              "coaching_cues": [], **dose, "regression_options": easier_and_stop[index][0],
                              "stop_rules": easier_and_stop[index][1], "progression_rule": "At the same dose, refine movement control."})
    sessions = [
        {**copy.deepcopy(session_template), "session_id": "ses-tw-1", "session_type": "skill",
         "title": "Tactical Focus — Attack Trigger Map", "execution_order": 1,
         "blocks": [{"block_id": "saved-watch", "block_type": "mindset", "display_name": rotation[0]["name"],
                     "coaching_cues": [], "progression_rule": rotation[0]["tactical_watch"]["progress"]}]},
        {**copy.deepcopy(session_template), "session_id": "ses-2", "session_type": "conditioning",
         "title": "Aerobic support — Read & Counter Flow", "execution_order": 2,
         "blocks": [{"block_id": "saved-aerobic", "block_type": "conditioning", "display_name": "Read & Counter Flow",
                     "rounds": 3, "work": {"value": 180, "unit": "seconds"}, "rest": {"value": 60, "unit": "seconds"},
                     "coaching_cues": [], "progression_rule": "Progress: none this block.",
                     "regression_options": ["Shorten work to 120 seconds per set"],
                     "stop_rules": ["Stop if breathing uncontrolled.", "Stop if form breaks."]}]},
        {**copy.deepcopy(session_template), "session_id": "ses-footwork", "session_type": "mixed",
         "title": "Shot-Line Circle-Off Reset", "execution_order": 1, "blocks": []},
        {**copy.deepcopy(session_template), "session_id": "ses-strength", "title": "Strength",
         "execution_order": 2, "blocks": source_blocks},
    ]
    week.update(start_date="", end_date="", countdown_start="", countdown_end="", days=[])
    for weekday in ("Mon", "Tue", "Thu", "Fri", "Sat"):
        day = copy.deepcopy(day_template)
        day.update(date="", weekday=weekday, countdown_label="", sessions=[])
        day["day_type"] = "rest" if weekday == "Mon" else "moderate" if weekday == "Fri" else "high"
        if weekday in ("Tue", "Thu", "Fri"):
            day["today_card"]["coach_led_contact"] = "Light technical combat" if weekday == "Fri" else "Hard sparring"
            day["today_card"]["headline"] = day["today_card"]["coach_led_contact"]
        if weekday == "Fri":
            day["sessions"] = sessions[:2]
        elif weekday == "Sat":
            day["sessions"] = sessions[2:]
        week["days"].append(day)
    structured["plan_metadata"]["plan_type"] = "open_ongoing_system"
    structured["event_context"] = {"event_type": "none"}
    structured["countdown_labels"] = []
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "created_at": "2026-10-13T09:00:00Z", "fight_date": None,
        "planning_brief": {"open_plan_spec": spec},
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
    # A written-out "Progress: none this block." is no rule and is not shown.
    original_guidance = {
        block["display_name"]: {key: (None if key == "progression_rule" and is_null_progression(block.get(key))
                                      else block.get(key))
                                for key in ("progression_rule", "regression_options", "stop_rules")}
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
                        assert {key: block.get(key) for key in original_guidance[exercise["name"]]} == original_guidance[exercise["name"]]
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


def test_repeated_open_exercise_keeps_its_appointment_coaching_when_order_changes():
    row = _reference_row()
    week = row["structured_plan"]["weeks"][0]
    day = next(day for day in week["days"] if day["weekday"] == "Sat")
    first = next(session for session in day["sessions"] if session["title"] == "Strength")
    second = copy.deepcopy(first)
    second.update(title="Second strength appointment", session_id="second-strength")
    for block in second["blocks"]:
        block["block_id"] += "-second"
        block["progression_rule"] = "At the same dose, refine balance in this appointment."
        block["regression_options"] = ["Use a smaller pain-free movement."]
    day["sessions"].insert(0, second)  # Exact title must beat the first name match.
    decisions = row["planning_brief"]["open_plan_spec"]["weekly_session_plan"]["weeks"]
    for decision in decisions:
        item = copy.deepcopy(next(session for session in decision["sessions"] if session["category"] == "strength"))
        item["label"] = "Second strength appointment"
        decision["sessions"].append(item)
    _, projected = _project(row)
    for week in projected["weeks"]:
        sessions = [session for day in week["days"] for session in day["sessions"]]
        first = next(session for session in sessions if session["title"] == "Strength")
        second = next(session for session in sessions if session["title"] == "Second strength appointment")
        assert all(block.get("progression_rule") == "At the same dose, refine movement control." for block in first["blocks"])
        assert all(block.get("progression_rule") == "At the same dose, refine balance in this appointment." for block in second["blocks"])
        assert all(block["regression_options"] == ["Use a smaller pain-free movement."] for block in second["blocks"])


def test_source_owned_conversion_preserves_full_open_strength_week_without_model():
    """Six source exercises cannot collapse into a three-exercise JSON card."""
    from api.structured_plan_generation import build_authoritative_open_plan
    from api.stage2_automation import _build_source_owned_structured_card

    row = _reference_row()
    brief = row["planning_brief"]
    card = build_authoritative_open_plan(brief, "# Approved training programme")
    assert card is not None
    assert safe_parse_structured_plan(card).ok
    assert len(card["weeks"]) == 4

    for week in card["weeks"]:
        saturday = next(day for day in week["days"] if day["weekday"] == "Sat")
        strength = next(session for session in saturday["sessions"] if session["title"] == "Strength")
        assert len(strength["blocks"]) == 6
        assert [block["display_name"] for block in strength["blocks"]] == [
            "Barbell Thruster", "Med-Ball Rotational Slam", "Trap Bar Jump",
            "Single-Leg Depth Drop (Stick Landing)", "Landmine Anti-Rotation Press",
            "Single-Leg Romanian Deadlift Hold",
        ]
        assert strength["blocks"][0]["sets"] == 4
        assert strength["blocks"][0]["reps"] == 2

    outcome = _build_source_owned_structured_card(
        planning_brief=brief, plan_text="# Approved training programme"
    )
    assert outcome is not None
    assert outcome.status == "valid"
    assert len(outcome.structured_plan["weeks"]) == 4


def test_source_owned_conversion_never_fills_in_missing_open_prescriptions():
    from api.structured_plan_generation import build_authoritative_open_plan

    row = _reference_row()
    brief = copy.deepcopy(row["planning_brief"])
    decisions = brief["open_plan_spec"]["weekly_session_plan"]["weeks"]
    next(s for s in decisions[0]["sessions"] if s["label"] == "Strength")["exercises"][0]["prescription"] = "2 sets x 6 reps"
    card = build_authoritative_open_plan(brief, "# Approved training programme")
    assert card is not None
    saturday = next(day for day in card["weeks"][0]["days"] if day["weekday"] == "Sat")
    strength = next(session for session in saturday["sessions"] if session["title"] == "Strength")
    assert strength["blocks"][0]["sets"] == 2
    assert strength["blocks"][0]["reps"] == 6


def test_open_structured_generation_does_not_make_a_second_model_request():
    import asyncio
    from api.stage2_automation import OpenAIStage2Automator
    from tests.support import FakeOpenAIClient

    brief = _reference_row()["planning_brief"]
    client = FakeOpenAIClient([])
    automator = OpenAIStage2Automator(client=client, model="gpt-5-mini")
    outcome, costs = asyncio.run(automator._generate_structured_outcome(
        final_plan_text="# Approved training programme",
        planning_brief=brief,
        source="quick_build",
        costs=[],
    ))
    assert outcome.status == "valid"
    assert len(outcome.structured_plan["weeks"]) == 4
    assert costs == []
    assert client.responses.calls == []


def test_direct_open_watch_rotation_uses_distinct_week_session_ids():
    from api.structured_plan_generation import build_authoritative_open_plan

    card = build_authoritative_open_plan(
        _reference_row()["planning_brief"], "# Approved training programme"
    )
    assert card is not None
    watches = [
        (week["week_index"], session["session_id"], session["blocks"][0]["display_name"])
        for week in card["weeks"] for day in week["days"]
        for session in day["sessions"]
        if any(block.get("block_type") == "mindset" for block in session.get("blocks") or [])
        and str(session.get("session_id") or "").startswith("open-tactical")
    ]
    assert [week for week, _, _ in watches] == [1, 3]
    assert len({session_id for _, session_id, _ in watches}) == len(watches)
