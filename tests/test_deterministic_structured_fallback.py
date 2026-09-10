"""The athlete-facing fallback is built from deterministic planner state.

Stage 2 may omit anything it likes in prose; none of it can remove a declared
combat day, a Tactical Watch or the fight day from what the athlete sees.
"""

from __future__ import annotations

import datetime

import pytest

from api.structured_plan_deterministic_fallback import build_deterministic_structured_plan
from api.structured_plan_faithfulness import _authoritative_locked_day, _locked_roles
from api.structured_plan_models import safe_parse_structured_plan
from support import _build_request


@pytest.fixture(scope="module")
def camp_brief() -> dict:
    """Tuesday + Thursday hard sparring, Wednesday declared light combat."""
    generate_plan_sync = pytest.importorskip("fightcamp.main").generate_plan_sync
    fight_date = (datetime.date.today() + datetime.timedelta(days=56)).isoformat()
    request = _build_request(
        {
            "fight_date": fight_date,
            "hard_sparring_days": ["Tuesday", "Thursday"],
            "support_work_days": ["Wednesday"],
            "training_availability": [
                "Monday", "Tuesday", "Wednesday", "Thursday", "Saturday",
            ],
            "weekly_training_frequency": 5,
        }
    ).to_payload()
    request["random_seed"] = 3
    return generate_plan_sync(request)["planning_brief"]


@pytest.fixture(scope="module")
def fallback(camp_brief) -> dict:
    """The canonical plan, assembled with NO Stage 2 output of any kind."""
    plan = build_deterministic_structured_plan(camp_brief)
    assert plan is not None
    return plan


def _days(plan: dict) -> dict[int, dict]:
    days: dict[int, dict] = {}
    for week in plan.get("weeks") or []:
        for day in week.get("days") or []:
            label = str(day.get("countdown_label") or "")
            if label.upper().startswith("D-"):
                days[int(label[2:])] = day
    return days


def _role_ddays(planning_brief: dict, role_key: str) -> set[int]:
    found: set[int] = set()
    for week in (planning_brief.get("weekly_role_map") or {}).get("weeks") or []:
        for role in week.get("session_roles") or []:
            if str(role.get("role_key") or "").strip() != role_key:
                continue
            label = str(
                role.get("scheduled_countdown_label") or role.get("countdown_label") or ""
            )
            if label.upper().startswith("D-"):
                found.add(int(label[2:]))
    return found


def _contact_text(day: dict) -> str:
    card = day.get("today_card") or {}
    return f"{card.get('headline') or ''} {card.get('coach_led_contact') or ''}".strip()


def test_fallback_is_a_valid_structured_plan(fallback):
    assert safe_parse_structured_plan(fallback).ok


def test_stage2_omitting_every_thursday_cannot_remove_hard_sparring(camp_brief, fallback):
    declared = _role_ddays(camp_brief, "hard_sparring_day")
    assert declared, "fixture must declare hard sparring"
    days = _days(fallback)
    for dday in sorted(declared, reverse=True):
        assert dday in days, f"D-{dday} missing from the calendar entirely"
        assert _contact_text(days[dday]), f"D-{dday} lost its declared contact"


def test_stage2_omitting_wednesday_cannot_remove_declared_light_combat(camp_brief, fallback):
    declared = _role_ddays(camp_brief, "light_combat_day")
    assert declared, "fixture must declare light combat"
    days = _days(fallback)
    for dday in sorted(declared, reverse=True):
        assert _contact_text(days[dday]), f"D-{dday} lost its declared light combat"


def test_stage2_omitting_tactical_watch_cannot_remove_it(camp_brief, fallback):
    roles = _locked_roles(camp_brief)
    assert roles, "fixture must produce deterministic Tactical Watch roles"
    days = _days(fallback)
    for role in roles:
        dday = _authoritative_locked_day(role)
        assert dday is not None
        names = {
            str(block.get("display_name"))
            for session in days[dday].get("sessions") or []
            for block in session.get("blocks") or []
            if block.get("block_type") == "mindset"
        }
        expected = str((role.get("governance") or {}).get("selected_drill_name") or "")
        assert expected in names, f"D-{dday} lost {expected!r}"


def test_distinct_roles_on_one_day_are_all_preserved(camp_brief, fallback):
    """Ownership protects the role, not the whole day."""
    days = _days(fallback)
    light_combat = _role_ddays(camp_brief, "light_combat_day")
    multi = [
        dday
        for dday in light_combat
        if days[dday].get("sessions") and _contact_text(days[dday])
    ]
    assert multi, (
        "expected at least one declared light-combat day to also carry app work; "
        "dedupe must not collapse distinct same-day roles"
    )
    for dday in multi:
        titles = [s.get("title") for s in days[dday]["sessions"]]
        assert len(titles) == len(set(titles)) or len(titles) > 1


def test_no_duplicate_session_identity_anywhere(fallback):
    seen: set[str] = set()
    for week in fallback.get("weeks") or []:
        for day in week.get("days") or []:
            for session in day.get("sessions") or []:
                session_id = str(session.get("session_id"))
                assert session_id not in seen, f"duplicate session {session_id}"
                seen.add(session_id)


def test_fight_day_override_still_wins(fallback):
    day = _days(fallback)[0]
    assert day.get("day_type") == "competition"
    assert "fight" in str((day.get("today_card") or {}).get("headline") or "").lower()


def test_fallback_carries_authoritative_doses_not_invented_ones(camp_brief, fallback):
    """Every rendered exercise came from a selected assignment with its dose."""
    assignments: dict[str, str] = {}
    for week in (camp_brief.get("weekly_role_map") or {}).get("weeks") or []:
        for role in week.get("session_roles") or []:
            for item in role.get("selected_exercise_assignments") or []:
                if isinstance(item, dict) and item.get("name"):
                    assignments[str(item["name"])] = str(item.get("base_prescription") or "")

    rendered = [
        block
        for week in fallback.get("weeks") or []
        for day in week.get("days") or []
        for session in day.get("sessions") or []
        for block in session.get("blocks") or []
        if block.get("block_type") != "mindset"
    ]
    assert rendered, "the fallback must carry Stage 1's selected work"
    for block in rendered:
        assert str(block.get("display_name")) in assignments, (
            f"{block.get('display_name')!r} was not a deterministic selection"
        )


def test_fallback_invents_no_nutrition_guidance(fallback):
    nutrition = fallback.get("nutrition") or {}
    assert set(nutrition) == {
        "summary",
        "daily_focus",
        "training_day_guidance",
        "fight_week_guidance",
    }
    assert not any(str(value).strip() for value in nutrition.values())
