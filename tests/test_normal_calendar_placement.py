from __future__ import annotations

import copy
import inspect
from types import SimpleNamespace

from fightcamp import normal_calendar_placement, stage2_payload, weekly_plan_render
from fightcamp.normal_calendar_placement import fill_missing_session_days


def _role(role_key: str, day: str = "") -> dict:
    return {
        "role_key": role_key,
        "category": "strength",
        "scheduled_day_hint": day,
    }


def test_fill_missing_session_days_preserves_legacy_assignment_contract() -> None:
    existing = _role("primary_strength_day", "Wednesday")
    first_blank = _role("aerobic_support_day")
    second_blank = _role("secondary_strength_day")
    no_slot = _role("recovery_reset_day")
    weekly_role_map = {
        "weeks": [
            {
                "declared_training_days": ["Friday", "Monday", "Wednesday", "not-a-day"],
                "session_roles": [existing, first_blank, second_blank, no_slot],
            }
        ]
    }

    returned = fill_missing_session_days(weekly_role_map)

    assert returned is weekly_role_map
    assert existing["scheduled_day_hint"] == "Wednesday"
    assert first_blank["scheduled_day_hint"] == "Monday"
    assert second_blank["scheduled_day_hint"] == "Friday"
    assert no_slot["scheduled_day_hint"] == ""


def test_fill_missing_session_days_ignores_invalid_week_entries() -> None:
    weekly_role_map = {
        "weeks": [
            None,
            {
                "declared_training_days": ["Tuesday"],
                "session_roles": [None, _role("primary_strength_day")],
            },
        ]
    }

    fill_missing_session_days(weekly_role_map)

    assert weekly_role_map["weeks"][1]["session_roles"][1]["scheduled_day_hint"] == "Tuesday"


def test_renderer_does_not_expose_missing_day_completion() -> None:
    # Step 8: the read-only renderer must not re-export or define the placement
    # mutator. Day completion is owned solely by normal_calendar_placement; the
    # renderer neither imports nor defines it (the temporary Step-4 back-compat
    # alias is removed now that no production caller depends on it).
    assert not hasattr(weekly_plan_render, "fill_missing_session_days")
    source = inspect.getsource(weekly_plan_render)
    assert "def fill_missing_session_days(" not in source
    assert "import fill_missing_session_days" not in source


def test_stage2_payload_imports_missing_day_completion_from_placement_owner() -> None:
    source = inspect.getsource(stage2_payload)

    assert stage2_payload.fill_missing_session_days is normal_calendar_placement.fill_missing_session_days
    assert "from .normal_calendar_placement import fill_missing_session_days" in source
    assert "from .weekly_plan_render import fill_missing_session_days" not in source


def test_placement_helper_does_not_add_policy_or_new_roles() -> None:
    role = _role("primary_strength_day")
    weekly_role_map = {
        "weeks": [
            {
                "declared_training_days": ["Thursday"],
                "session_roles": [role],
                "suppressed_roles": [{"role_key": "secondary_strength_day"}],
            }
        ]
    }

    before_roles = list(weekly_role_map["weeks"][0]["session_roles"])
    before_suppressed = list(weekly_role_map["weeks"][0]["suppressed_roles"])

    fill_missing_session_days(weekly_role_map)

    assert weekly_role_map["weeks"][0]["session_roles"] == before_roles
    assert weekly_role_map["weeks"][0]["suppressed_roles"] == before_suppressed
    assert role["scheduled_day_hint"] == "Thursday"


def _render_brief_with_one_dayless_role() -> dict:
    """A normal-camp brief (>1 week, so the renderer emits sections): week 1 has one
    placed role and one deliberately dayless role; week 2 is fully placed."""
    return {
        "payload_variant": "",
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "phase": "GPP",
                    "declared_training_days": ["Monday", "Thursday"],
                    "calendar_days": [
                        {"weekday": "monday", "d_day": 56},
                        {"weekday": "thursday", "d_day": 53},
                    ],
                    "session_roles": [
                        {
                            "category": "strength",
                            "role_key": "primary_strength_day",
                            "athlete_facing_label": "Strength",
                            "scheduled_day_hint": "Thursday",
                        },
                        {
                            # No scheduled_day_hint: placement was (deliberately) not run.
                            "category": "conditioning",
                            "role_key": "aerobic_base_day",
                            "athlete_facing_label": "Aerobic support",
                            "preferred_system": "aerobic",
                        },
                    ],
                },
                {
                    "week_index": 2,
                    "phase": "GPP",
                    "declared_training_days": ["Monday", "Thursday"],
                    "calendar_days": [
                        {"weekday": "monday", "d_day": 49},
                        {"weekday": "thursday", "d_day": 46},
                    ],
                    "session_roles": [
                        {
                            "category": "strength",
                            "role_key": "primary_strength_day",
                            "athlete_facing_label": "Strength",
                            "scheduled_day_hint": "Thursday",
                        }
                    ],
                },
            ]
        },
    }


def _render_blocks() -> SimpleNamespace:
    return SimpleNamespace(
        strength_blocks={"GPP": {"exercises": [{"name": "Back Squat", "anchor_capable": True}]}},
        conditioning_blocks={"GPP": {"grouped_drills": {"aerobic": [{"name": "Easy Bike", "duration": "25 min"}]}}},
    )


def test_rendering_does_not_mutate_planner_scheduling_state() -> None:
    # Step 8 ownership regression: rendering is a read-only consumer. Rendering a role
    # the placement layer left dayless must not originate/relocate a weekday or otherwise
    # mutate scheduling fields on the source role objects — the renderer describes
    # planner state, it does not complete it.
    brief = _render_brief_with_one_dayless_role()
    before = copy.deepcopy(brief["weekly_role_map"])

    section = weekly_plan_render.render_weekly_schedule_section(
        planning_brief=brief, blocks=_render_blocks()
    )
    # Guard: the render path actually executed (so "no mutation" is not vacuous).
    assert section.startswith("# Weekly Schedule")

    # Whole calendar/role state is byte-for-byte unchanged by rendering.
    assert brief["weekly_role_map"] == before
    roles = brief["weekly_role_map"]["weeks"][0]["session_roles"]
    # The renderer did not originate a scheduled_day_hint for the dayless role...
    assert roles[1].get("scheduled_day_hint") in (None, "")
    for field in ("scheduled_countdown_label", "countdown_offset", "real_weekday"):
        assert field not in roles[1]
    # ...and did not relocate the already-placed role.
    assert roles[0]["scheduled_day_hint"] == "Thursday"


def test_rendering_places_dayless_role_only_after_upstream_completion() -> None:
    # The dayless role reaches a real day only when the placement owner runs before
    # rendering (as the pipeline does) — never from the renderer itself.
    brief = _render_brief_with_one_dayless_role()
    rendered_without_placement = weekly_plan_render.render_weekly_schedule_section(
        planning_brief=brief, blocks=_render_blocks()
    )
    # Renderer alone: the dayless role stays dayless (label only, no weekday heading).
    assert "### Aerobic support" in rendered_without_placement
    assert "### Monday" not in rendered_without_placement

    placed = _render_brief_with_one_dayless_role()
    fill_missing_session_days(placed["weekly_role_map"])
    rendered_after_placement = weekly_plan_render.render_weekly_schedule_section(
        planning_brief=placed, blocks=_render_blocks()
    )
    # After the placement owner assigns the free training day, the renderer reads it.
    assert "### Monday (D-56) — Aerobic support" in rendered_after_placement
