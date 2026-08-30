"""Characterization gate for the final-calendar integrity refactor.

These tests intentionally exercise the real deterministic planning pipeline. They
freeze semantic planner behaviour that Stage 3 must preserve while allowing the
new integrity governor to change only calendars that violate the shared
``combat_load_policy`` seam.

The projection is deliberately semantic: role identity, day/D-day ownership,
load-relevant contact state, suppression, and D-14/D-13 ownership. It avoids
exercise names and presentation copy so later rendering work does not make this
architecture gate noisy.
"""

from __future__ import annotations

import datetime as dt
import logging

import pytest

from fightcamp import input_parsing
from fightcamp.input_parsing import PlanInput
from fightcamp.plan_pipeline_blocks import generate_plan_blocks
from fightcamp.plan_pipeline_rendering import build_stage2_outputs
from fightcamp.plan_pipeline_runtime import (
    RenderedPlanBundle,
    build_runtime_context,
    prime_plan_banks,
)

logging.disable(logging.CRITICAL)

FIGHT_DATE = dt.date(2026, 1, 30)  # Friday
_EQUIPMENT = (
    "bands, partner, kettlebells, dumbbells, cable, barbell, pullup_bar, "
    "heavy_bag, neck_harness, plate, towel, weight_belt, box, trap_bar, "
    "landmine, foam_roller, assault_bike, weight_vest, rower, pool, hurdles"
)


@pytest.fixture(scope="module", autouse=True)
def _warm_banks():
    prime_plan_banks(logger=logging.getLogger("calendar-integrity-characterization"))


def _fields(**overrides) -> list[dict]:
    return [
        {"label": "Full name", "value": "Calendar Characterization"},
        {"label": "Age", "value": "30"},
        {"label": "Weight (kg)", "value": overrides.get("weight", "88")},
        {"label": "Target Weight (kg)", "value": overrides.get("target_weight", "85")},
        {"label": "Height (cm)", "value": "185"},
        {"label": "Fighting Style (Technical)", "value": "boxing"},
        {"label": "Fighting Style (Tactical)", "value": "counter_striker"},
        {"label": "Stance", "value": "Orthodox"},
        {"label": "Professional Status", "value": "professional"},
        {"label": "Current Record", "value": "9-2"},
        {"label": "Athlete Time Zone", "value": "Europe/London"},
        {"label": "Rounds x Minutes", "value": "12x3"},
        {"label": "Weekly Training Frequency", "value": overrides.get("frequency", "4")},
        {"label": "Fatigue Level", "value": overrides.get("fatigue", "low")},
        {"label": "Equipment Access", "value": _EQUIPMENT},
        {
            "label": "Training Availability",
            "value": overrides.get(
                "availability",
                "Monday, Tuesday, Wednesday, Thursday, Friday, Sunday",
            ),
        },
        {"label": "Hard Sparring Days", "value": overrides.get("hard_sparring", "")},
        {"label": "Support Work Days", "value": overrides.get("support", "Monday")},
        {"label": "What are your key performance goals?", "value": overrides.get("key_goals", "power, speed")},
        {"label": "Primary goal", "value": overrides.get("primary_goal", "power")},
        {"label": "Where do you feel weakest right now?", "value": overrides.get("weak", "coordination, speed")},
        {"label": "Primary weak area", "value": overrides.get("primary_weak", "coordination")},
        {"label": "When is your next fight?", "value": FIGHT_DATE.strftime("%Y-%m-%d")},
        {"label": "Any injuries or areas you need to work around?", "value": overrides.get("injuries", "")},
    ]


def _run(days: int, monkeypatch, **overrides) -> dict:
    fixed_now = dt.datetime.combine(
        FIGHT_DATE - dt.timedelta(days=days),
        dt.time(12, 0),
    )
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: fixed_now)
    plan_input = PlanInput.from_payload({"data": {"fields": _fields(**overrides)}})
    assert plan_input.days_until_fight == days
    context = build_runtime_context(
        plan_input=plan_input,
        random_seed=1,
        logger=logging.getLogger("calendar-integrity-characterization"),
    )
    blocks = generate_plan_blocks(
        context=context,
        logger=logging.getLogger("calendar-integrity-characterization"),
        record_timing=lambda *args, **kwargs: None,
    )
    rendered = RenderedPlanBundle(
        fight_plan_text="",
        coach_notes="",
        reason_log={},
        html="",
    )
    _payload, brief, _handoff = build_stage2_outputs(
        context=context,
        blocks=blocks,
        rendered=rendered,
    )
    return brief


def _role_d_day(week: dict, role: dict) -> int | None:
    weekday = str(role.get("scheduled_day_hint") or role.get("real_weekday") or "").strip().lower()
    for day in week.get("calendar_days", []) or []:
        if not isinstance(day, dict):
            continue
        if str(day.get("weekday") or "").strip().lower() == weekday and isinstance(day.get("d_day"), int):
            return day["d_day"]
    for key in ("scheduled_countdown_label", "countdown_label"):
        label = str(role.get(key) or "").strip().upper()
        if label.startswith("D-") and label[2:].isdigit():
            return int(label[2:])
    return None


def _semantic_projection(brief: dict) -> dict:
    role_rows: list[tuple] = []
    contact_rows: list[tuple] = []
    suppression_rows: list[tuple] = []
    weekly_role_map = brief.get("weekly_role_map") or {}
    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
        week_index = int(week.get("week_index") or 0)
        for role in week.get("session_roles", []) or []:
            if not isinstance(role, dict):
                continue
            role_rows.append(
                (
                    week_index,
                    str(role.get("phase") or week.get("phase") or ""),
                    str(role.get("role_key") or ""),
                    str(role.get("category") or ""),
                    str(role.get("scheduled_day_hint") or role.get("real_weekday") or "").lower(),
                    _role_d_day(week, role),
                    bool(role.get("late_fight_tail_owned")),
                    bool(role.get("late_camp_role_morph")),
                    bool(role.get("late_camp_strength_morph")),
                    str(role.get("stress_class") or ""),
                    str(role.get("cost_class") or ""),
                )
            )
        for entry in week.get("hard_sparring_plan", []) or []:
            if not isinstance(entry, dict):
                continue
            contact_rows.append(
                (
                    week_index,
                    str(entry.get("day") or "").lower(),
                    str(entry.get("status") or ""),
                    str(entry.get("effective_load") or ""),
                )
            )
        for entry in week.get("suppressed_roles", []) or []:
            if isinstance(entry, dict):
                suppression_rows.append(
                    (
                        week_index,
                        str(entry.get("role_key") or entry.get("role") or ""),
                        str(entry.get("reason_code") or ""),
                    )
                )
    return {
        "generator_mode": brief.get("generator_mode"),
        "payload_variant": brief.get("payload_variant"),
        "roles": sorted(role_rows),
        "contacts": sorted(contact_rows),
        "suppressed": sorted(suppression_rows),
        "tail_handoff": weekly_role_map.get("late_fight_tail_handoff"),
    }


def _all_roles(brief: dict):
    for week in (brief.get("weekly_role_map") or {}).get("weeks", []) or []:
        for role in week.get("session_roles", []) or []:
            if isinstance(role, dict):
                yield week, role


def _all_contact_entries(brief: dict):
    for week in (brief.get("weekly_role_map") or {}).get("weeks", []) or []:
        for entry in week.get("hard_sparring_plan", []) or []:
            if isinstance(entry, dict):
                yield week, entry


def test_semantic_projection_is_deterministic_for_clean_normal_camp(monkeypatch):
    first = _semantic_projection(_run(24, monkeypatch, hard_sparring=""))
    second = _semantic_projection(_run(24, monkeypatch, hard_sparring=""))
    assert first == second
    assert first["generator_mode"] == "deterministic_planner_plus_ai_finalizer"
    assert first["payload_variant"] is None
    assert first["roles"]


def test_no_contact_fixture_does_not_invent_resolved_contact(monkeypatch):
    brief = _run(24, monkeypatch, hard_sparring="")
    assert list(_all_contact_entries(brief)) == []


def test_one_declared_hard_contact_has_resolved_contact_state(monkeypatch):
    brief = _run(24, monkeypatch, hard_sparring="Thursday")
    entries = [entry for _week, entry in _all_contact_entries(brief)]
    assert entries
    assert any(
        str(entry.get("status") or "") == "hard_as_planned"
        or str(entry.get("effective_load") or "") == "hard"
        for entry in entries
    )


def test_two_declared_hard_contacts_preserve_two_contact_calendar_ownership(monkeypatch):
    brief = _run(24, monkeypatch, hard_sparring="Tuesday, Friday")
    weekdays = {
        str(entry.get("day") or "").strip().lower()
        for _week, entry in _all_contact_entries(brief)
    }
    assert {"tuesday", "friday"} <= weekdays


def test_d16_declared_hard_contact_is_resolved_away_from_effective_hard(monkeypatch):
    brief = _run(16, monkeypatch, hard_sparring="Tuesday, Friday")
    entries = [entry for _week, entry in _all_contact_entries(brief)]
    assert entries
    assert not any(
        str(entry.get("status") or "") == "hard_as_planned"
        or str(entry.get("effective_load") or "") == "hard"
        for entry in entries
    )


def test_no_saturday_availability_never_places_normal_app_role_on_saturday(monkeypatch):
    brief = _run(24, monkeypatch, hard_sparring="Thursday")
    for _week, role in _all_roles(brief):
        assert str(role.get("scheduled_day_hint") or "").strip().lower() != "saturday"


def test_d14_d13_planner_boundary_is_characterized(monkeypatch):
    d14 = _run(14, monkeypatch, hard_sparring="Thursday")
    d13 = _run(13, monkeypatch, hard_sparring="Thursday")
    assert d14.get("generator_mode") == "deterministic_planner_plus_ai_finalizer"
    assert d14.get("payload_variant") is None
    assert d13.get("payload_variant") == "late_fight_stage2_payload"


def test_long_camp_contains_finished_tail_owned_roles(monkeypatch):
    brief = _run(24, monkeypatch, hard_sparring="Thursday")
    owned = [
        (week, role)
        for week, role in _all_roles(brief)
        if role.get("late_fight_tail_owned")
    ]
    assert owned
    assert all(
        (d_day := _role_d_day(week, role)) is not None and 1 <= d_day <= 13
        for week, role in owned
    )


def test_characterization_projection_carries_suppression_and_tail_state(monkeypatch):
    projection = _semantic_projection(
        _run(
            24,
            monkeypatch,
            hard_sparring="Tuesday, Friday",
            fatigue="high",
        )
    )
    assert "suppressed" in projection
    assert projection["tail_handoff"] == {
        "active": True,
        "normal_planner_through_d": 14,
        "late_fight_planner_from_d": 13,
        "source": "finished_existing_late_fight_path",
    }
