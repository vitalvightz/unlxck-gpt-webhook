"""End-to-end invariant: a coach-owned contact day never hides behind its sessions.

Production plan (anonymised here): the readable programme had hard sparring on
D-42/D-35/D-28/D-21 (Saturdays) but the saved card only showed it on D-42 and
D-28. On D-35 and D-21 the day carried the planner's Self-Review Cues session
with ``coach_led_contact`` null, so the renderer showed the mental session alone
and labelled the day "Zero load".

Cause: the contact reconcile treated Self-Review as incompatible app work and
removed it (its allowlist was a label regex that drifted from the planner's
zero-load roles), stamping the contact on the headline only. The calendar spine
then restored the scheduled Self-Review after the reconcile had run, leaving a
session day with no ``coach_led_contact``.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path

import pytest

from api.models import PlanRequest
from api.plan_mappers import _map_plan_detail
from api.services.effective_structured_plan import resolve_effective_structured_plan
from api.stage2_automation import OpenAIStage2Automator
from api.structured_plan_deterministic_fallback import build_deterministic_structured_plan
from api.structured_plan_generation import StructuredPlanOutcome, _merge_locked_content
from api.structured_plan_sparring_reconcile import (
    reconcile_coach_led_sparring_days,
    surface_coach_led_contact,
)
from fightcamp import input_parsing, stage2_planning_brief
from fightcamp.main import generate_plan_sync

FIXTURES = Path(__file__).parent / "fixtures"
SATURDAYS = ("D-42", "D-35", "D-28", "D-21")
SELF_REVIEW_DAYS = ("D-35", "D-21")


@pytest.fixture(scope="module")
def brief() -> dict:
    intake = json.loads(
        (FIXTURES / "programme_fidelity" / "affected_intake.json").read_text(encoding="utf8")
    )
    intake["random_seed"] = 1
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(input_parsing, "_utc_now", lambda: datetime(2026, 10, 14, 3, 40))
        patch.setattr(stage2_planning_brief, "_utc_now", lambda: datetime(2026, 10, 14, 3, 40))
        stage1 = generate_plan_sync(PlanRequest(**intake).to_payload())
    return stage1["planning_brief"]


@pytest.fixture(scope="module")
def production_days() -> dict[str, dict]:
    days = json.loads(
        (FIXTURES / "sparring_contact" / "production_contact_days.json").read_text(encoding="utf8")
    )
    return {day["countdown_label"]: day for day in days}


@pytest.fixture(scope="module")
def fallback(brief) -> dict:
    plan = build_deterministic_structured_plan(brief)
    assert plan is not None
    return plan


def _days(plan: dict) -> dict[str, dict]:
    return {
        day["countdown_label"]: day
        for week in plan.get("weeks") or []
        for day in week.get("days") or []
        if isinstance(day, dict) and day.get("countdown_label")
    }


def _titles(day: dict) -> list[str]:
    return [str(session.get("title")) for session in day.get("sessions") or []]


def _with_days(plan: dict, replacements: dict[str, dict]) -> dict:
    plan = copy.deepcopy(plan)
    for week in plan["weeks"]:
        for index, day in enumerate(week["days"]):
            label = day.get("countdown_label")
            if label in replacements:
                week["days"][index] = copy.deepcopy(replacements[label])
    return plan


def _assert_contact_preserved(plan: dict) -> None:
    days = _days(plan)
    for label in SATURDAYS:
        day = days[label]
        assert day["today_card"]["coach_led_contact"] == "Hard sparring", label
        assert day["day_type"] == "high", label
        assert "hard_sparring_day" in day["planning_day_role_keys"], label
    for label in SELF_REVIEW_DAYS:
        # The planner's zero-load companion survives next to the contact.
        assert _titles(days[label]) == ["Self-Review Cues"], label


def test_deterministic_source_schedules_hard_sparring_with_companions(brief):
    by_day: dict[str, set[str]] = {}
    for week in brief["weekly_role_map"]["weeks"]:
        for role in week["session_roles"]:
            label = role.get("scheduled_countdown_label") or role.get("countdown_label")
            by_day.setdefault(label, set()).add(role["role_key"])
            if label in SATURDAYS and role["role_key"] == "hard_sparring_day":
                assert role["hard_sparring_status"] == "hard_as_planned"
    assert by_day["D-42"] == by_day["D-28"] == {"hard_sparring_day", "breathing_reset"}
    assert by_day["D-35"] == by_day["D-21"] == {"hard_sparring_day", "self_review"}


def test_deterministic_fallback_keeps_contact_and_scheduled_self_review(fallback):
    _assert_contact_preserved(fallback)


@pytest.mark.parametrize("converter_kept_self_review", [True, False])
def test_converted_card_preserves_contact_after_spine_restores_sessions(
    brief, fallback, production_days, converter_kept_self_review
):
    # Production converter output for the four Saturdays, with the contact field
    # removed and (in one variant) the Self-Review dropped, as a converter does.
    converted = {}
    for label, day in production_days.items():
        day = copy.deepcopy(day)
        day["today_card"].pop("coach_led_contact", None)
        if label in SELF_REVIEW_DAYS and not converter_kept_self_review:
            day["sessions"] = []
        converted[label] = day
    plan = _merge_locked_content(_with_days(fallback, converted), brief)
    outcome = OpenAIStage2Automator._reconcile_structured_calendar(
        StructuredPlanOutcome(status="valid", structured_plan=plan), brief
    )
    _assert_contact_preserved(outcome.structured_plan)


def test_saved_production_card_resolves_with_contact(brief, fallback, production_days):
    stored = _with_days(fallback, production_days)
    # The saved row is exactly as production persisted it: headline and role
    # keys correct, contact field null on D-35/D-21.
    saved = _days(stored)
    for label in SELF_REVIEW_DAYS:
        assert saved[label]["today_card"]["headline"] == "Hard sparring"
        assert saved[label]["today_card"]["coach_led_contact"] is None
    row = {"id": "replay00", "structured_plan": stored, "planning_brief": brief, "plan_text": "x"}
    resolved = resolve_effective_structured_plan(row)
    _assert_contact_preserved(resolved)
    # Read-time repair is a copy: the stored row is untouched.
    assert _days(stored)["D-35"]["today_card"]["coach_led_contact"] is None


def test_plan_detail_api_serves_contact_for_saved_production_card(brief, fallback, production_days):
    row = {
        "id": "replay00",
        "athlete_id": "athlete-replay",
        "status": "publishable_with_flags",
        "plan_text": "# Plan",
        "final_plan_text": "# Plan",
        "fight_date": "2026-12-05",
        "created_at": "2026-10-14T14:43:52+00:00",
        "structured_plan": _with_days(fallback, production_days),
        "planning_brief": brief,
    }
    detail = _map_plan_detail(row, include_admin=False, current_training_day="2026-10-20")
    payload = detail.outputs.structured_plan.model_dump(mode="json")
    _assert_contact_preserved(payload)


def test_missing_contact_field_is_restored_independent_of_headline(brief, fallback):
    # Negative regression: drop the contact key entirely, keep the correct
    # headline and role keys. The headline alone must never be the carrier.
    plan = copy.deepcopy(fallback)
    for label in SATURDAYS:
        card = _days(plan)[label]["today_card"]
        card.pop("coach_led_contact", None)
        card["headline"] = "Hard sparring"
    assert all(_days(plan)[label]["today_card"]["headline"] == "Hard sparring" for label in SATURDAYS)
    notes = surface_coach_led_contact(plan, brief)
    assert len(notes) == 4
    _assert_contact_preserved(plan)


def test_surface_never_upgrades_a_downgraded_technical_day(brief, fallback):
    # D-14 is a declared hard Saturday the dose planner converted to technical.
    plan = copy.deepcopy(fallback)
    day = _days(plan)["D-14"]
    contact = day["today_card"].get("coach_led_contact") or day["today_card"].get("headline")
    assert "hard sparring" not in str(contact).lower()
    day["today_card"].pop("coach_led_contact", None)
    day["sessions"] = day.get("sessions") or [copy.deepcopy(_days(fallback)["D-35"]["sessions"][0])]
    surface_coach_led_contact(plan, brief)
    surfaced = _days(plan)["D-14"]["today_card"]["coach_led_contact"]
    assert surfaced and "hard" not in surfaced.lower()


def test_surface_is_idempotent_and_adds_or_removes_no_sessions(brief, fallback):
    plan = copy.deepcopy(fallback)
    before = {label: _titles(day) for label, day in _days(plan).items()}
    assert surface_coach_led_contact(plan, brief) == []
    assert {label: _titles(day) for label, day in _days(plan).items()} == before


def test_reconcile_still_removes_unscheduled_physical_work_from_hard_contact(brief, fallback):
    # The zero-load exemption is only for roles the planner scheduled on that
    # day; converter-invented physical work on a hard day is still removed.
    plan = copy.deepcopy(fallback)
    day = _days(plan)["D-35"]
    day["today_card"].pop("coach_led_contact", None)
    day["sessions"].append({
        "title": "Strength Primer",
        "session_type": "strength_power",
        "blocks": [{"display_name": "Trap Bar Deadlift", "block_type": "strength"}],
        "mindset_anchor": {"intent": "", "focus_cue": "", "reset_cue": ""},
    })
    reconcile_coach_led_sparring_days(plan, brief)
    day = _days(plan)["D-35"]
    assert _titles(day) == ["Self-Review Cues"]
    assert day["today_card"]["coach_led_contact"] == "Hard sparring"
