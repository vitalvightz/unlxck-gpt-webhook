from __future__ import annotations

import inspect

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
