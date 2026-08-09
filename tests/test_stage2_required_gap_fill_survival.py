from fightcamp.stage2_pipeline import _required_countdown_session_warnings


_ROLE_LABELS = {
    "strength_touch_day": "Strength Touch",
    "tactical_watch": "Fight Tactical Watch",
    "recovery_reset": "Recovery Reset",
    "neural_power_day": "Neural Power",
}


def _role(offset: int, role_key: str, category: str) -> dict:
    return {
        "countdown_offset": offset,
        "countdown_label": f"D-{offset}",
        "scheduled_countdown_label": f"D-{offset}",
        "scheduled_day_hint": {
            14: "friday",
            11: "monday",
            9: "wednesday",
            8: "thursday",
        }[offset],
        "role_key": role_key,
        "category": category,
        "athlete_facing_label": _ROLE_LABELS[role_key],
        "render_mandatory": True,
    }


def _planning_brief() -> dict:
    return {
        "late_fight_session_sequence": [
            _role(14, "strength_touch_day", "strength"),
            _role(11, "tactical_watch", "support_insert"),
            _role(9, "recovery_reset", "support_insert"),
            _role(8, "neural_power_day", "power"),
        ]
    }


def test_final_plan_blocks_if_required_gap_fill_sessions_disappear():
    warnings = _required_countdown_session_warnings(
        planning_brief=_planning_brief(),
        final_plan_text="""
D-14 (Friday) — Strength touch
D-8 (Thursday) — Neural power
""",
    )

    missing = {
        warning["expected_countdown_label"]
        for warning in warnings
        if warning["code"] == "late_fight_missing_required_countdown_session"
    }
    assert missing == {"D-11", "D-9"}


def test_final_plan_accepts_gap_fill_sessions_when_they_survive_rendering():
    warnings = _required_countdown_session_warnings(
        planning_brief=_planning_brief(),
        final_plan_text="""
D-14 (Friday) — Strength touch
D-11 (Monday) — Fight Tactical Watch
D-9 (Wednesday) — Recovery Reset
D-8 (Thursday) — Neural power
""",
    )

    assert warnings == []


def test_same_day_header_does_not_hide_a_missing_required_role():
    # The D-9 header and Tactical Watch both survive; Recovery Reset does not.
    # A header-only guard would miss this exact same-day collision.
    planning_brief = {
        "late_fight_session_sequence": [
            _role(9, "tactical_watch", "support_insert"),
            _role(9, "recovery_reset", "support_insert"),
        ]
    }

    warnings = _required_countdown_session_warnings(
        planning_brief=planning_brief,
        final_plan_text="""
D-9 (Wednesday) — Fight Tactical Watch
- Review the selected tactical cue.
""",
    )

    assert {warning["role_key"] for warning in warnings} == {"recovery_reset"}


def test_same_day_roles_both_pass_when_both_survive():
    planning_brief = {
        "late_fight_session_sequence": [
            _role(9, "tactical_watch", "support_insert"),
            _role(9, "recovery_reset", "support_insert"),
        ]
    }

    warnings = _required_countdown_session_warnings(
        planning_brief=planning_brief,
        final_plan_text="""
D-9 (Wednesday) — Fight Tactical Watch
- Review the selected tactical cue.

Recovery Reset
- Easy breathing and mobility.
""",
    )

    assert warnings == []
