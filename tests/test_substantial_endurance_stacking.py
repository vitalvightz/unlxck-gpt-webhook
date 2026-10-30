"""Saved 29 October regression: three available days cannot hold four workouts."""

from __future__ import annotations

import json
import copy
from pathlib import Path

import pytest

from fightcamp.combat_load_policy import (
    CalendarEvent,
    CalendarLoadProfile,
    DayOccupancy,
    LoadClass,
    evaluate_candidate_at_position,
    role_load_profile,
)
from fightcamp.session_composition import (
    apply_realised_load_calendar_revalidation,
    conditioning_assignment_from_slot,
)
from fightcamp.session_workload import (
    UNSAFE_STACKING_CODE,
    raw_stacking_findings,
    substantial_endurance,
    structured_stacking_findings,
)
from fightcamp.stage2_policy import apply_stage2_release_policy
from fightcamp.stage2_validator import validate_stage2_output
from fightcamp.calendar_context import role_d_day
from api.structured_plan_safety import audit_structured_plan, split_findings


@pytest.fixture
def saved_case():
    return json.loads(
        (
            Path(__file__).parent / "fixtures/open_ongoing_unsafe_stacking.json"
        ).read_text()
    )


def _endurance(name="5K Steady Run", **dose):
    return {
        "name": name,
        "slot_group": "conditioning_slots",
        "rpe": 3,
        "lactate_load": "low",
        **dose,
    }


def _endurance_role(item=None):
    return {
        "role_key": "aerobic_base_day",
        "category": "conditioning",
        "preferred_system": "aerobic",
        "scheduled_day_hint": "Wednesday",
        "scheduled_d_day": 82,
        "scheduled_countdown_label": "D-82",
        "session_index": 3,
        "selected_exercise_assignments": [
            item or _endurance(distance_m=5000, modality="run")
        ],
    }


def _strength_role():
    return {
        "role_key": "primary_strength_day",
        "category": "strength",
        "scheduled_day_hint": "Wednesday",
        "scheduled_d_day": 82,
        "scheduled_countdown_label": "D-82",
        "session_index": 2,
        "selected_exercise_assignments": [
            {
                "name": "Tire Flip",
                "slot_group": "strength_slots",
                "effective_prescription": "4x2",
                "mechanical_risk_tags": ["mech_ballistic"],
            },
            {
                "name": "Tempo Split Squat",
                "slot_group": "strength_slots",
                "effective_prescription": "3x6",
                "mechanical_risk_tags": ["mech_lower_lunge"],
            },
        ],
    }


def _decision(candidate, *occupants):
    return evaluate_candidate_at_position(
        candidate,
        candidate_position=0,
        events=[CalendarEvent(0, occupant) for occupant in occupants],
    )


@pytest.mark.parametrize(
    "item",
    [
        _endurance(effective_prescription="5 km continuous; easy pace"),
        _endurance("Continuous swim", modality="swim", total_minutes=40),
        _endurance("Steady cycling", modality="cycle", distance_m=20000),
        _endurance("Long row", modality="row", distance_m=6000),
    ],
)
def test_substantial_endurance_cannot_share_full_strength_in_either_order(item):
    assert substantial_endurance(item)
    endurance = role_load_profile(_endurance_role(item))
    strength = role_load_profile(_strength_role())
    assert _decision(endurance, strength).reason_code == UNSAFE_STACKING_CODE
    assert not _decision(endurance, strength).allowed
    assert not _decision(strength, endurance).allowed


@pytest.mark.parametrize(
    "item",
    [
        _endurance("Easy bike flush", modality="cycle", total_minutes=10),
        _endurance(effective_prescription="10 min easy run"),
        _endurance(duration_min=10),
        _endurance(duration="10 min easy run"),
        _endurance(distance_m=1000),
        _endurance(
            "Run intervals",
            modality="run",
            duration="6 x 800 m",
            rounds=6,
            distance_m=4800,
        ),
        _endurance(
            "Power row", modality="row", duration="6 x 5 sec", rounds=6, work_sec=5
        ),
    ],
)
def test_short_easy_cardio_and_power_intervals_remain_compatible(item):
    assert not substantial_endurance(item)
    assert _decision(
        role_load_profile(_endurance_role(item)), role_load_profile(_strength_role())
    ).allowed


def test_long_endurance_and_downgraded_technical_are_compatible():
    endurance = role_load_profile(_endurance_role())
    assert _decision(endurance).allowed
    technical = role_load_profile({"role_key": "light_combat_day"})
    assert _decision(endurance, technical).allowed
    assert _decision(technical, endurance).allowed


def test_hard_sparring_stays_exclusive():
    hard = CalendarLoadProfile(LoadClass.HARD_CONTACT, DayOccupancy.EXCLUSIVE_PHYSICAL)
    assert not _decision(role_load_profile(_endurance_role()), hard).allowed
    assert not _decision(role_load_profile(_strength_role()), hard).allowed


def _calendar(extra_day=False, reverse=False):
    strength, endurance = _strength_role(), _endurance_role()
    roles = [endurance, strength] if reverse else [strength, endurance]
    roles.insert(
        0,
        {
            "role_key": "light_combat_day",
            "category": "technical",
            "coach_owned": True,
            "declared_day_locked": True,
            "scheduled_day_hint": "Wednesday",
            "scheduled_d_day": 82,
        },
    )
    return {
        "weeks": [
            {
                "week_index": 1,
                "phase": "GPP",
                "declared_training_days": ["monday", "wednesday", "thursday"]
                + (["saturday"] if extra_day else []),
                "calendar_days": [
                    {"weekday": day, "d_day": 84 - i}
                    for i, day in enumerate(
                        [
                            "monday",
                            "tuesday",
                            "wednesday",
                            "thursday",
                            "friday",
                            "saturday",
                            "sunday",
                        ]
                    )
                ],
                "session_roles": roles,
                "hard_sparring_plan": [
                    {"scheduled_d_day": d, "day": day, "effective_load": "hard"}
                    for d, day in [(84, "Monday"), (81, "Thursday")]
                ],
            }
        ]
    }


@pytest.mark.parametrize("reverse", [False, True])
def test_no_free_compatible_day_defers_endurance_without_replacing_it(reverse):
    calendar = _calendar(reverse=reverse)
    apply_realised_load_calendar_revalidation(calendar)
    week = calendar["weeks"][0]
    assert {r["role_key"] for r in week["session_roles"]} == {
        "light_combat_day",
        "primary_strength_day",
    }
    assert all(role_d_day(week, r) == 82 for r in week["session_roles"])
    suppressed = week["suppressed_roles"]
    assert len(suppressed) == 1
    assert suppressed[0]["role_key"] == "aerobic_base_day"
    assert suppressed[0]["reason_code"] == UNSAFE_STACKING_CODE


def test_move_only_to_an_available_compatible_day():
    calendar = _calendar(extra_day=True)
    apply_realised_load_calendar_revalidation(calendar)
    roles = calendar["weeks"][0]["session_roles"]
    endurance = next(r for r in roles if r["role_key"] == "aerobic_base_day")
    assert endurance["scheduled_day_hint"].lower() == "saturday"
    assert (
        role_d_day(
            calendar["weeks"][0], next(r for r in roles if r["category"] == "strength")
        )
        == 82
    )


def test_assignment_retains_endurance_classification_and_dose():
    option = {
        "name": "Long swim",
        "prescription": "40 min continuous",
        "selection_metadata": {
            "modality": "swim",
            "system": "aerobic",
            "total_minutes": 40,
            "duration": "40 min continuous",
        },
    }
    assignment = conditioning_assignment_from_slot("GPP", {"slot_id": "swim"}, option)
    assert assignment["total_minutes"] == 40
    assert assignment["modality"] == "swim"
    assert substantial_endurance(assignment)


def test_saved_planner_membership_defers_5k_and_preserves_six_exercise_anchor(
    saved_case,
):
    from fightcamp.stage2_payload import _project_open_development_block

    calendar = _calendar()
    week = calendar["weeks"][0]
    roles = []
    for session in saved_case["source_sessions"]:
        if session.get("category") not in {"strength", "conditioning", "technical"}:
            continue
        role = {
            "role_key": session["role_key"],
            "category": session["category"],
            "scheduled_day_hint": session["weekday"],
            "scheduled_d_day": 82,
            "scheduled_countdown_label": "D-82",
            "preferred_system": "aerobic",
            "selected_exercise_assignments": [
                {
                    "name": exercise["name"],
                    "effective_prescription": exercise["prescription"],
                    "slot_group": "strength_slots"
                    if session["category"] == "strength"
                    else "conditioning_slots",
                }
                for exercise in session.get("exercises") or []
            ],
        }
        roles.append(role)
    week["session_roles"] = roles
    apply_realised_load_calendar_revalidation(calendar)
    assert {r["category"] for r in week["session_roles"]} == {"strength", "technical"}
    strength = next(r for r in week["session_roles"] if r["category"] == "strength")
    assert len(strength["selected_exercise_assignments"]) == 6
    assert week["suppressed_roles"][0]["role_key"] == "aerobic_base_day"
    assert week["suppressed_roles"][0]["reason_code"] == UNSAFE_STACKING_CODE
    projected = _project_open_development_block({"weekly_role_map": calendar})["weeks"][
        0
    ]
    assert {s["weekday"] for s in projected["sessions"]} == {"Wednesday"}
    assert projected["removed_sessions"][0]["reason_code"] == UNSAFE_STACKING_CODE


def test_saved_open_case_without_role_map_flags_actual_day_stacking(saved_case):
    brief = saved_case["planning_brief"]
    assert "weekly_role_map" not in brief
    findings = raw_stacking_findings(saved_case["raw_text"])
    assert len(findings) == 1
    assert findings[0]["day"].endswith(":wednesday")
    report = validate_stage2_output(
        planning_brief=brief, final_plan_text=saved_case["raw_text"]
    )
    assert any(item["code"] == UNSAFE_STACKING_CODE for item in report["errors"])
    # User policy: report for admin review; validators never pause release.
    release = apply_stage2_release_policy(report)
    assert release["release_decision"] == "publish_with_flags"
    assert release["is_athlete_releasable"]


def _structured(name="5K Steady Run", distance=None, duration=None):
    return {
        "weeks": [
            {
                "days": [
                    {
                        "weekday": "Wednesday",
                        "sessions": [
                            {
                                "title": "Strength",
                                "session_type": "strength_power",
                                "blocks": [
                                    {"display_name": "Tire Flip", "block_type": "power"}
                                ],
                            },
                            {
                                "title": "Aerobic support",
                                "session_type": "conditioning",
                                "blocks": [
                                    {
                                        "display_name": name,
                                        "distance": distance,
                                        "duration": duration,
                                    }
                                ],
                            },
                        ],
                    }
                ]
            }
        ]
    }


@pytest.mark.parametrize(
    "name,distance,duration",
    [
        ("5K Steady Run", None, None),
        ("Steady swim", {"value": 1500, "unit": "m"}, None),
        ("Steady cycling", None, {"value": 45, "unit": "minutes"}),
        ("Long row", {"value": 6, "unit": "km"}, None),
        ("Easy continuous swim", None, {"value": 2400, "unit": "seconds"}),
    ],
)
def test_structured_final_audit_rejects_unsafe_card(name, distance, duration):
    plan = _structured(name, distance, duration)
    assert structured_stacking_findings(plan)
    blocking, _ = split_findings(audit_structured_plan(plan))
    assert any(UNSAFE_STACKING_CODE in finding for finding in blocking)


def test_unsafe_structured_conversion_is_discarded_even_after_session_regrouping():
    from api.structured_plan_generation import build_structured_plan_outcome
    from test_structured_plan_models import _valid_plan
    from test_structured_plan_generation import _faithful_source

    plan = _valid_plan()
    day = plan["weeks"][0]["days"][0]
    endurance = copy.deepcopy(day["sessions"][0])
    endurance.update(session_id="aerobic", title="Aerobic", session_type="conditioning")
    endurance["blocks"] = [
        {
            "block_id": "run",
            "block_type": "conditioning",
            "display_name": "5K Steady Run",
            "order_index": 1,
            "distance": {"value": 5, "unit": "km"},
        }
    ]
    day["sessions"].append(endurance)
    outcome = build_structured_plan_outcome(plan, raw_markdown=_faithful_source(plan))
    assert outcome.status == "blocked_by_safety_audit"
    assert outcome.structured_plan is None
    assert any(UNSAFE_STACKING_CODE in error for error in outcome.errors)


def test_raw_and_structured_safe_pairings_remain_clean(saved_case):
    text = saved_case["raw_text"]
    start = text.index("Wednesday — Aerobic support")
    end = text.index("Thursday — Hard sparring", start)
    assert not raw_stacking_findings(text[:start] + text[end:])
    strength_start = text.index("Wednesday — Strength")
    assert not raw_stacking_findings(text[:strength_start] + text[start:])
    plan = _structured("Easy bike flush", duration={"value": 10, "unit": "minutes"})
    assert not structured_stacking_findings(plan)
    plan = _structured()
    plan["weeks"][0]["days"][0]["sessions"][0] = {
        "title": "Light technical",
        "blocks": [],
    }
    assert not structured_stacking_findings(plan)


def test_raw_checks_same_day_sessions_and_combined_session():
    for text in [
        "### D-30 (Wednesday) — Strength\n- Tire Flip: 4x2\n### D-30 (Wednesday) — Aerobic\n- 5K Steady Run: 5 km continuous",
        "Wednesday — Strength + endurance\n- Tire Flip: 4x2\n- Easy run: 5 km continuous",
    ]:
        assert raw_stacking_findings(text)
