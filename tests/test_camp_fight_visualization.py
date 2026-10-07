"""Optional camp Fight Visualisation: D-42 -> D-8, up to three a week."""
from __future__ import annotations

from api.structured_plan_locked_merge import merge_locked_structured_content
from fightcamp.camp_week_fillers_impl import _ensure_camp_visualizations
from fightcamp.fight_visualization_library import (
    CAMP_VISUALIZATION_DURATION_MIN,
    camp_visualization_role,
    choose_camp_visualization_days,
)
from fightcamp.gap_fill_inserts import (
    apply_gap_fill_inserts,
    budgeted_insert_count,
    camp_visualization_day_tier,
)


def _athlete(**overrides):
    model = {
        "sport": "boxing",
        "style_tactical": ["pressure_fighter"],
        "days_until_fight": 13,
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"],
    }
    model.update(overrides)
    return model


def _role(offset, role_key, **extra):
    role = {
        "role_key": role_key,
        "category": extra.pop("category", "sparring"),
        "countdown_offset": offset,
        "countdown_label": f"D-{offset}",
        "scheduled_countdown_label": f"D-{offset}",
    }
    role.update(extra)
    return role


def _support(offset, role_key="mobility_rehab"):
    return _role(offset, role_key, category="support_insert", stress_class="support", cost_class="low")


def _camp(sequence):
    return {
        role["countdown_offset"]: role
        for role in sequence
        if role.get("role_key") == "fight_visualization" and role.get("optional_fight_visualization")
    }


def test_day_tiers_prefer_tactical_focus_then_low_load_and_skip_contact_and_rest():
    assert camp_visualization_day_tier([_role(10, "tactical_watch")]) == 0
    assert camp_visualization_day_tier([_support(10)]) == 1
    assert camp_visualization_day_tier([_role(10, "primary_strength_day", category="strength")]) == 2
    assert camp_visualization_day_tier([_role(10, "hard_sparring_day")]) is None
    assert camp_visualization_day_tier([]) is None
    assert camp_visualization_day_tier([_role(10, "fight_visualization")]) is None


def test_three_days_are_spread_out_and_ranked():
    # Tactical Focus on 12, low load on 11 and 9, strength on 10 and 8.
    # 12 and 9 are spaced; 11 comes in last only because nothing spaced is left.
    assert choose_camp_visualization_days({12: 0, 11: 1, 9: 1, 10: 2, 8: 2}) == [12, 11, 9]
    assert choose_camp_visualization_days({14: 1, 13: 1, 11: 2, 9: 2}) == [14, 11, 9]
    assert choose_camp_visualization_days({13: 2, 12: 2}) == [13, 12]
    assert choose_camp_visualization_days({}) == []


def test_late_path_offers_camp_sessions_before_the_countdown():
    sequence = apply_gap_fill_inserts(
        [
            _role(12, "hard_sparring_day"),
            _role(11, "primary_strength_day", category="strength"),
            _support(10),
            _role(9, "hard_sparring_day"),
            _role(8, "primary_strength_day", category="strength"),
        ],
        _athlete(),
    )
    camp = _camp(sequence)
    assert camp, "expected optional camp sessions on D-13..D-8"
    assert len(camp) <= 3
    assert all(8 <= offset <= 13 for offset in camp)
    # Never on a hard-contact day.
    assert not {12, 9} & set(camp)
    for role in camp.values():
        assert role["prescribed_duration_min"] == CAMP_VISUALIZATION_DURATION_MIN
        assert "optional mental rehearsal" in role["display_text"]
        governance = role["governance"]
        assert governance["selected_drill_locked"] is True
        assert governance["mandatory"] is False
        assert not role.get("mandatory_fight_visualization")
    # The countdown protocol is untouched and still mandatory.
    countdown = {
        role["countdown_offset"]
        for role in sequence
        if role.get("role_key") == "fight_visualization" and role.get("mandatory_fight_visualization")
    }
    assert countdown == {7, 5, 3, 1, 0}


def test_camp_sessions_spend_no_insert_budget():
    roles = [_support(offset) for offset in (13, 11, 9)]
    sequence = apply_gap_fill_inserts(roles, _athlete())
    camp = list(_camp(sequence).values())
    assert camp
    assert budgeted_insert_count(camp) == 0


def test_short_notice_plan_has_no_camp_block():
    sequence = apply_gap_fill_inserts([_support(5)], _athlete(days_until_fight=6))
    assert _camp(sequence) == {}


def _week(days):
    """A camp week: ``days`` maps weekday -> (d_day, [role_key, ...])."""
    return {
        "phase": "SPP",
        "calendar_days": [{"weekday": day, "d_day": d_day} for day, (d_day, _keys) in days.items()],
        "session_roles": [
            {
                "role_key": key,
                "scheduled_day_hint": day.title(),
                "category": "support_insert" if key in {"tactical_watch", "mobility_rehab"} else "strength",
                "stress_class": "support" if key in {"tactical_watch", "mobility_rehab"} else "",
                "cost_class": "low" if key in {"tactical_watch", "mobility_rehab"} else "",
            }
            for day, (_d_day, keys) in days.items()
            for key in keys
        ],
    }


def test_camp_week_pairs_with_tactical_focus_and_low_load_days():
    week = _week(
        {
            "monday": (27, ["primary_strength_day"]),
            "tuesday": (26, ["hard_sparring_day"]),
            "wednesday": (25, ["tactical_watch"]),
            "thursday": (24, ["primary_strength_day"]),
            "friday": (23, ["mobility_rehab"]),
            "saturday": (22, ["hard_sparring_day"]),
            "sunday": (21, []),
        }
    )
    assert _ensure_camp_visualizations(week, _athlete(days_until_fight=30)) == 3
    placed = {
        role["scheduled_day_hint"]: role
        for role in week["session_roles"]
        if role.get("optional_fight_visualization")
    }
    assert "Wednesday" in placed and "Friday" in placed
    assert not {"Tuesday", "Saturday", "Sunday"} & set(placed)
    # Each week runs picture -> read -> reset.
    names = [role["fight_visualization"]["name"] for role in sorted(placed.values(), key=lambda r: -r["countdown_offset"])]
    assert len(set(names)) == 3


def test_camp_week_stays_inside_the_window():
    far = _week({"monday": (50, ["tactical_watch"]), "tuesday": (49, ["mobility_rehab"])})
    assert _ensure_camp_visualizations(far, _athlete(days_until_fight=55)) == 0
    tail = _week({"monday": (13, ["tactical_watch"])})
    # D-13 and later belongs to the late-fight tail.
    assert _ensure_camp_visualizations(tail, _athlete(days_until_fight=30)) == 0


def test_card_marks_the_camp_session_optional():
    role = camp_visualization_role(_athlete(), d_day=10, weekday="wednesday", ordinal=0)
    assert role is not None
    brief = {"weeks": [{"session_roles": [role]}]}
    plan = {"weeks": [{"days": [{"countdown_label": "D-10", "sessions": []}]}]}
    result = merge_locked_structured_content(plan, brief)
    assert not result.unresolved
    session = result.plan["weeks"][0]["days"][0]["sessions"][0]
    assert session["title"] == "Fight Visualisation"
    assert session["objective"].startswith("Optional. ")
    assert session["blocks"][0]["duration"] == {"value": 12, "unit": "minutes"}
