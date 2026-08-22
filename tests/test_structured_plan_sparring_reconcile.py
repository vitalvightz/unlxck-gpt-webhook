"""Tests for the deterministic coach-led / sparring card reconciliation.

The structured card derives a day's coach-led status from the LLM headline alone,
so a dropped or mislabelled sparring day silently renders as "Rest day.". These
tests prove the role-map schedule is used to stamp/insert those cards so a
declared sparring day always ships as a coach-led card.
"""
from __future__ import annotations

import re

from api.structured_plan_sparring_reconcile import reconcile_coach_led_sparring_days

# Mirror the web classifier (web/lib/structured-plan.ts) so the assertions prove a
# stamped/inserted headline would actually classify as coach-led there.
_TECHNICAL_RE = re.compile(
    r"\b(technical|skill|drill|pad\s?work|pads|mitts?|footwork|shadow)", re.I
)
_SPARRING_RE = re.compile(r"\bspar(?:r(?:ing|ed)|s)?\b", re.I)
_COACH_LED_RE = re.compile(r"\bcoach", re.I)


def _classifies_coach_led(headline: str) -> bool:
    return bool(
        _TECHNICAL_RE.search(headline)
        or _SPARRING_RE.search(headline)
        or _COACH_LED_RE.search(headline)
    )


def _planning_brief(hard_plan: list[dict], *, span_days: int = 7, end_d: int = 28) -> dict:
    """A single-week role map with a countdown spine (d_day, no calendar_date).

    Mirrors production: ``build_calendar_days`` ships weekday + d_day per day, so
    the deterministic schedule matches structured days by D-day.
    """
    calendar_days = []
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for offset in range(span_days):
        d_day = end_d + (span_days - 1 - offset)
        calendar_days.append({"weekday": weekdays[offset % 7], "d_day": d_day})
    return {
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": "SPP",
                    "calendar_days": calendar_days,
                    "hard_sparring_plan": hard_plan,
                }
            ]
        }
    }


def _week_calendar(span_days: int, end_d: int) -> list[dict]:
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return [
        {"weekday": weekdays[offset % 7], "d_day": end_d + (span_days - 1 - offset)}
        for offset in range(span_days)
    ]


def _multi_week_brief() -> dict:
    # Week 1 Thursday -> D-31, week 2 Thursday -> D-24.
    return {
        "weekly_role_map": {
            "weeks": [
                {"phase": "SPP", "calendar_days": _week_calendar(7, 28), "hard_sparring_plan": _hard_thursday()},
                {"phase": "SPP", "calendar_days": _week_calendar(7, 21), "hard_sparring_plan": _hard_thursday()},
            ]
        }
    }


def _dated_brief() -> dict:
    """Single week whose schedule days carry BOTH a calendar_date and a d_day.

    Thursday is D-31 with a concrete date, so the role-map contact day has both
    identities — the case where the structured plan may already contain the day by
    D-day only.
    """
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    dates = ["2026-07-20", "2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24", "2026-07-25", "2026-07-26"]
    calendar_days = [
        {"weekday": weekdays[offset], "d_day": 28 + (7 - 1 - offset), "calendar_date": dates[offset]}
        for offset in range(7)
    ]
    return {
        "weekly_role_map": {
            "weeks": [{"phase": "SPP", "calendar_days": calendar_days, "hard_sparring_plan": _hard_thursday()}]
        }
    }


def _light_support_friday_brief(*, hard_plan: list[dict] | None = None) -> dict:
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    dates = ["2026-07-20", "2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24", "2026-07-25", "2026-07-26"]
    calendar_days = [
        {"weekday": weekdays[offset], "d_day": 28 + (7 - 1 - offset), "calendar_date": dates[offset]}
        for offset in range(7)
    ]
    return {
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": "SPP",
                    "calendar_days": calendar_days,
                    "declared_support_work_days": ["Friday"],
                    "declared_technical_skill_days": [],
                    "hard_sparring_plan": hard_plan or [],
                }
            ]
        }
    }


def _day(countdown: str, *, headline: str = "", sessions: list | None = None) -> dict:
    return {
        "date": "",
        "countdown_label": countdown,
        "day_type": "moderate",
        "today_card": {"headline": headline, "readiness_status": "train_as_planned"},
        "sessions": sessions if sessions is not None else [],
    }


def _structured_plan(days: list[dict], *, week_index: int = 1, **week_extra) -> dict:
    week = {
        "week_id": f"wk-{week_index}",
        "week_index": week_index,
        "phase_label": "SPP",
        "start_date": "",
        "end_date": "",
        "days": days,
    }
    week.update(week_extra)
    return {"weeks": [week]}


def _hard_thursday() -> list[dict]:
    # Thursday in the synthetic week is the 4th day -> d_day 31 (end_d 28, span 7).
    return [
        {
            "day": "Thursday",
            "hard_day_class": "primary_hard",
            "effective_load": "hard",
            "status": "hard_as_planned",
        }
    ]


def _hard_friday() -> list[dict]:
    return [
        {
            "day": "Friday",
            "hard_day_class": "primary_hard",
            "effective_load": "hard",
            "status": "hard_as_planned",
        }
    ]


def _late_context_brief(*, d_day: int = 9, downgraded: bool = True) -> dict:
    return {
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": "TAPER",
                    "session_roles": [
                        {
                            "role_key": "hard_sparring_day",
                            "scheduled_day_hint": "tuesday",
                            "scheduled_countdown_label": f"D-{d_day}",
                            "countdown_label": f"D-{d_day}",
                            "countdown_offset": d_day,
                            "downgraded": downgraded,
                            "downgraded_to_role_key": "technical_touch_day" if downgraded else "",
                            "placement_source": (
                                "declared_hard_day_downgrade_context"
                                if downgraded
                                else "declared_hard_day_lock"
                            ),
                        }
                    ],
                    "hard_sparring_plan": [],
                }
            ]
        }
    }


def test_stamps_coach_led_headline_on_mislabelled_rest_day():
    plan = _structured_plan([_day("D-31", headline="Recovery")])
    notes = reconcile_coach_led_sparring_days(plan, _planning_brief(_hard_thursday()))

    headline = plan["weeks"][0]["days"][0]["today_card"]["headline"]
    assert headline == "Hard sparring"
    assert _classifies_coach_led(headline)
    assert notes and "stamped" in notes[0]


def test_stamps_when_headline_is_blank():
    plan = _structured_plan([_day("D-31", headline="")])
    reconcile_coach_led_sparring_days(plan, _planning_brief(_hard_thursday()))
    assert plan["weeks"][0]["days"][0]["today_card"]["headline"] == "Hard sparring"


def test_inserts_dropped_sparring_day_into_covering_week():
    plan = _structured_plan([_day("D-33", headline="Strength"), _day("D-30", headline="Aerobic")])
    notes = reconcile_coach_led_sparring_days(plan, _planning_brief(_hard_thursday()))

    days = plan["weeks"][0]["days"]
    assert [d["countdown_label"] for d in days] == ["D-33", "D-31", "D-30"]
    inserted = days[1]
    assert inserted["today_card"]["headline"] == "Hard sparring"
    assert inserted["sessions"] == []
    assert inserted["phase_label"] == "SPP"
    assert any("inserted" in note for note in notes)


def test_surfaces_coach_led_contact_alongside_real_app_sessions():
    real_session = [{"title": "Fight Tactical Watch", "blocks": []}]
    plan = _structured_plan([_day("D-31", headline="Fight Tactical Watch", sessions=real_session)])
    notes = reconcile_coach_led_sparring_days(plan, _planning_brief(_hard_thursday()))

    day = plan["weeks"][0]["days"][0]
    assert day["today_card"]["headline"] == "Fight Tactical Watch"
    assert day["sessions"] == real_session
    assert day["today_card"]["coach_led_contact"] == "Hard sparring"
    assert any("surfaced coach-led contact" in note for note in notes)


def test_does_not_double_surface_coach_led_contact():
    real_session = [{"title": "Fight Tactical Watch", "blocks": []}]
    day = _day("D-31", headline="Fight Tactical Watch", sessions=real_session)
    day["today_card"]["coach_led_contact"] = "Hard sparring"
    plan = _structured_plan([day])
    notes = reconcile_coach_led_sparring_days(plan, _planning_brief(_hard_thursday()))

    assert plan["weeks"][0]["days"][0]["today_card"]["coach_led_contact"] == "Hard sparring"
    assert notes == []


def test_surfaces_coach_led_contact_even_when_app_headline_already_coach_led():
    real_session = [{"title": "Tactical Cue Card", "blocks": []}]
    plan = _structured_plan(
        [_day("D-31", headline="Coach-led boxing session", sessions=real_session)]
    )
    notes = reconcile_coach_led_sparring_days(plan, _planning_brief(_hard_thursday()))

    day = plan["weeks"][0]["days"][0]
    assert day["today_card"]["headline"] == "Coach-led boxing session"
    assert day["sessions"] == real_session
    assert day["today_card"]["coach_led_contact"] == "Hard sparring"
    assert any("surfaced coach-led contact" in note for note in notes)


def test_d9_declared_technical_day_keeps_tactical_watch_as_attached_filler():
    tactical_watch = [{"title": "Fight Tactical Watch", "duration": "8-12 min", "blocks": []}]
    plan = _structured_plan([_day("D-9", headline="Fight Tactical Watch", sessions=tactical_watch)])
    notes = reconcile_coach_led_sparring_days(plan, _late_context_brief(d_day=9, downgraded=True))

    day = plan["weeks"][0]["days"][0]
    assert day["today_card"]["headline"] == "Fight Tactical Watch"
    assert day["today_card"]["coach_led_contact"] == "Controlled fight-speed technical rounds"
    assert day["sessions"] == tactical_watch
    assert any("surfaced coach-led contact" in note for note in notes)


def test_declared_technical_day_preserves_app_work_alongside_contact():
    freshness = [{
        "title": "Fight-week freshness",
        "blocks": [{
            "display_name": "Band face pull, light",
            "sets": 2,
            "reps": "12-15",
            "effort": {"method": "RPE", "value": 3},
        }],
    }]
    plan = _structured_plan([_day("D-9", headline="Fight-week freshness", sessions=freshness)])
    notes = reconcile_coach_led_sparring_days(plan, _late_context_brief(d_day=9, downgraded=True))

    day = plan["weeks"][0]["days"][0]
    assert day["today_card"]["headline"] == "Fight-week freshness"
    assert day["today_card"]["coach_led_contact"] == "Controlled fight-speed technical rounds"
    assert day["sessions"] == freshness
    assert not any("removed incompatible same-day app work" in note for note in notes)


def test_allowed_filler_ignores_blocked_words_in_free_text_notes():
    tactical_watch = [
        {
            "title": "Fight Tactical Watch",
            "description": "Visualize maintaining fight pace without chasing strength recovery.",
            "notes": "Keep it calm.",
        }
    ]
    plan = _structured_plan([_day("D-9", headline="Fight Tactical Watch", sessions=tactical_watch)])
    reconcile_coach_led_sparring_days(plan, _late_context_brief(d_day=9, downgraded=True))

    day = plan["weeks"][0]["days"][0]
    assert day["sessions"] == tactical_watch
    assert day["today_card"]["coach_led_contact"] == "Controlled fight-speed technical rounds"


def test_declared_technical_day_preserves_high_rpe_app_work():
    mobility = [{"title": "Mobility Reset", "rpe": 7}]
    plan = _structured_plan([_day("D-9", headline="Mobility Reset", sessions=mobility)])
    reconcile_coach_led_sparring_days(plan, _late_context_brief(d_day=9, downgraded=True))

    day = plan["weeks"][0]["days"][0]
    assert day["today_card"]["headline"] == "Mobility Reset"
    assert day["today_card"]["coach_led_contact"] == "Controlled fight-speed technical rounds"
    assert day["sessions"] == mobility


def test_malformed_session_roles_is_ignored_without_error():
    brief = _late_context_brief(d_day=9, downgraded=True)
    brief["weekly_role_map"]["weeks"][0]["session_roles"] = {"role_key": "hard_sparring_day"}
    plan = _structured_plan([_day("D-9", headline="Recovery")])
    notes = reconcile_coach_led_sparring_days(plan, brief)

    assert notes == []
    assert plan["weeks"][0]["days"][0]["today_card"]["headline"] == "Recovery"


def test_d20_declared_hard_day_can_be_recovered_from_context_role():
    plan = _structured_plan([_day("D-20", headline="Recovery")])
    reconcile_coach_led_sparring_days(plan, _late_context_brief(d_day=20, downgraded=False))

    assert plan["weeks"][0]["days"][0]["today_card"]["headline"] == "Hard sparring"


def test_declared_late_technical_context_cards_follow_countdown_taper():
    expected = {
        17: "Controlled fight-speed technical rounds",
        8: "Controlled fight-speed technical rounds",
        7: "Technical rhythm only",
        5: "Technical rhythm only",
        4: "Technical touch — pads / shadow",
        2: "Technical touch — pads / shadow",
        1: "Technical activation — no contact",
    }
    for d_day, expected_headline in expected.items():
        plan = _structured_plan([_day(f"D-{d_day}", headline="Recovery")])
        reconcile_coach_led_sparring_days(plan, _late_context_brief(d_day=d_day, downgraded=True))

        headline = plan["weeks"][0]["days"][0]["today_card"]["headline"]
        assert headline == expected_headline
        assert _classifies_coach_led(headline)


def _normal_camp_role_brief(
    *,
    d_day: int,
    status: str = "hard_as_planned",
    hard_day_class: str = "primary_hard",
    reason_codes: list[str] | None = None,
) -> dict:
    return {
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": "SPP",
                    "session_roles": [
                        {
                            "role_key": "hard_sparring_day",
                            "scheduled_day_hint": "Tuesday",
                            "scheduled_countdown_label": f"D-{d_day}",
                            "countdown_label": f"D-{d_day}",
                            "hard_sparring_status": status,
                            "hard_sparring_class": hard_day_class,
                            "hard_sparring_reason_codes": list(reason_codes or []),
                        }
                    ],
                    "hard_sparring_plan": [],
                }
            ]
        }
    }


def test_normal_camp_converted_day_inside_d17_ban_uses_countdown_specific_card():
    expected = {
        17: "Controlled fight-speed technical rounds",
        15: "Controlled fight-speed technical rounds",
        11: "Controlled fight-speed technical rounds",
        8: "Controlled fight-speed technical rounds",
        7: "Technical rhythm only",
        5: "Technical rhythm only",
        4: "Technical touch — pads / shadow",
        2: "Technical touch — pads / shadow",
        1: "Technical activation — no contact",
    }
    for d_day, expected_headline in expected.items():
        plan = _structured_plan([_day(f"D-{d_day}", headline="Recovery")])
        reconcile_coach_led_sparring_days(
            plan,
            _normal_camp_role_brief(
                d_day=d_day,
                status="convert_to_technical_suggested",
                hard_day_class="managed_hard",
                reason_codes=["d17_hard_sparring_ban"],
            ),
        )
        assert plan["weeks"][0]["days"][0]["today_card"]["headline"] == expected_headline


def test_normal_camp_hard_sparring_ban_boundary_is_d18():
    hard_plan = _structured_plan([_day("D-18", headline="Recovery")])
    reconcile_coach_led_sparring_days(hard_plan, _normal_camp_role_brief(d_day=18))
    assert hard_plan["weeks"][0]["days"][0]["today_card"]["headline"] == "Hard sparring"

    banned_plan = _structured_plan([_day("D-17", headline="Recovery")])
    reconcile_coach_led_sparring_days(banned_plan, _normal_camp_role_brief(d_day=17))
    assert banned_plan["weeks"][0]["days"][0]["today_card"]["headline"] == "Controlled fight-speed technical rounds"


def test_normal_camp_deloaded_hard_day_renders_reduced_dose():
    plan = _structured_plan([_day("D-25", headline="Recovery")])
    reconcile_coach_led_sparring_days(
        plan,
        _normal_camp_role_brief(
            d_day=25,
            status="deload_suggested",
            hard_day_class="managed_hard",
            reason_codes=["consecutive_hard_days"],
        ),
    )
    assert plan["weeks"][0]["days"][0]["today_card"]["headline"] == "Hard sparring — reduced dose"


def test_countdown_ban_outranks_a_role_still_claiming_hard_inside_d17():
    plan = _structured_plan([_day("D-12", headline="Recovery")])
    brief = _normal_camp_role_brief(d_day=12)
    del brief["weekly_role_map"]["weeks"][0]["session_roles"][0]["hard_sparring_status"]
    del brief["weekly_role_map"]["weeks"][0]["session_roles"][0]["hard_sparring_reason_codes"]
    del brief["weekly_role_map"]["weeks"][0]["session_roles"][0]["hard_sparring_class"]

    reconcile_coach_led_sparring_days(plan, brief)
    assert plan["weeks"][0]["days"][0]["today_card"]["headline"] == "Controlled fight-speed technical rounds"


def test_schedule_derived_hard_day_inside_ban_is_clamped_to_countdown_specific_technical_card():
    hard_plan = [
        {
            "day": "Thursday",
            "effective_load": "hard",
            "status": "hard_as_planned",
            "hard_day_class": "primary_hard",
        }
    ]
    plan = _structured_plan([_day("D-10", headline="Recovery")])
    reconcile_coach_led_sparring_days(plan, _planning_brief(hard_plan, end_d=7))
    assert plan["weeks"][0]["days"][0]["today_card"]["headline"] == "Controlled fight-speed technical rounds"


def test_leaves_already_coach_led_headline_alone():
    plan = _structured_plan([_day("D-31", headline="Coach-led boxing session")])
    notes = reconcile_coach_led_sparring_days(plan, _planning_brief(_hard_thursday()))
    assert plan["weeks"][0]["days"][0]["today_card"]["headline"] == "Coach-led boxing session"
    assert notes == []


def test_technical_and_reduced_loads_get_classifiable_headlines():
    hard_plan = [
        {"day": "Thursday", "effective_load": "technical", "status": "convert_to_technical_suggested",
         "hard_day_class": "technical"},
        {"day": "Friday", "effective_load": "reduced", "status": "deload_suggested",
         "hard_day_class": "managed_hard"},
    ]
    plan = _structured_plan([_day("D-31", headline="Rest"), _day("D-30", headline="Rest")])
    reconcile_coach_led_sparring_days(plan, _planning_brief(hard_plan))

    technical = plan["weeks"][0]["days"][0]["today_card"]["headline"]
    reduced = plan["weeks"][0]["days"][1]["today_card"]["headline"]
    assert technical == "Technical-only combat"
    assert reduced == "Hard sparring — reduced dose"
    assert _classifies_coach_led(technical)
    assert _classifies_coach_led(reduced)


def test_noop_when_no_contact_days_declared():
    plan = _structured_plan([_day("D-31", headline="Recovery")])
    brief = _planning_brief([])
    before = plan["weeks"][0]["days"][0]["today_card"]["headline"]
    notes = reconcile_coach_led_sparring_days(plan, brief)
    assert notes == []
    assert plan["weeks"][0]["days"][0]["today_card"]["headline"] == before


def test_noop_on_malformed_inputs():
    assert reconcile_coach_led_sparring_days(None, {}) == []
    assert reconcile_coach_led_sparring_days({}, None) == []
    assert reconcile_coach_led_sparring_days({"weeks": []}, _planning_brief(_hard_thursday())) == []


def test_does_not_double_insert_when_day_present_with_sessions():
    real_session = [{"title": "Fight Tactical Watch", "blocks": []}]
    plan = _structured_plan([_day("D-31", headline="Fight Tactical Watch", sessions=real_session)])
    reconcile_coach_led_sparring_days(plan, _planning_brief(_hard_thursday()))
    assert len(plan["weeks"][0]["days"]) == 1
    assert plan["weeks"][0]["days"][0]["today_card"]["coach_led_contact"] == "Hard sparring"


def test_inserts_dropped_boundary_sparring_day():
    plan = _structured_plan([_day("D-30", headline="Strength"), _day("D-29", headline="Aerobic")])
    notes = reconcile_coach_led_sparring_days(plan, _planning_brief(_hard_thursday()))

    days = plan["weeks"][0]["days"]
    assert [d["countdown_label"] for d in days] == ["D-31", "D-30", "D-29"]
    assert days[0]["today_card"]["headline"] == "Hard sparring"
    assert any("inserted" in note for note in notes)


def test_targets_correct_week_by_index_in_multi_week_plan():
    brief = _multi_week_brief()
    plan = {
        "weeks": [
            {"week_id": "wk-1", "week_index": 1, "phase_label": "SPP", "start_date": "", "end_date": "",
             "days": [_day("D-33", headline="Strength")]},
            {"week_id": "wk-2", "week_index": 2, "phase_label": "SPP", "start_date": "", "end_date": "",
             "days": [_day("D-26", headline="Strength")]},
        ]
    }
    reconcile_coach_led_sparring_days(plan, brief)

    wk1 = [d["countdown_label"] for d in plan["weeks"][0]["days"]]
    wk2 = [d["countdown_label"] for d in plan["weeks"][1]["days"]]
    assert "D-31" in wk1 and "D-31" not in wk2
    assert "D-24" in wk2 and "D-24" not in wk1


def test_no_duplicate_when_present_by_dday_only_but_contact_has_date():
    plan = _structured_plan([_day("D-31", headline="Recovery")])
    notes = reconcile_coach_led_sparring_days(plan, _dated_brief())

    days = plan["weeks"][0]["days"]
    assert len(days) == 1
    assert days[0]["today_card"]["headline"] == "Hard sparring"
    assert not any("inserted" in note for note in notes)


def test_span_fallback_inserts_when_week_index_does_not_match():
    plan = _structured_plan(
        [_day("D-33", headline="Strength"), _day("D-30", headline="Aerobic")],
        week_index=99,
    )
    reconcile_coach_led_sparring_days(plan, _planning_brief(_hard_thursday()))
    assert [d["countdown_label"] for d in plan["weeks"][0]["days"]] == ["D-33", "D-31", "D-30"]


def test_declared_support_work_day_does_not_insert_light_combat_card():
    plan = _structured_plan([_day("D-31", headline="Strength"), _day("D-29", headline="Aerobic")])
    notes = reconcile_coach_led_sparring_days(plan, _light_support_friday_brief())

    days = plan["weeks"][0]["days"]
    assert [d["countdown_label"] for d in days] == ["D-31", "D-29"]
    assert notes == []


def test_declared_support_work_day_does_not_stamp_light_combat_card():
    friday = _day("D-30", headline="Mobility support")
    plan = _structured_plan([friday])
    notes = reconcile_coach_led_sparring_days(plan, _light_support_friday_brief())

    assert friday["today_card"]["headline"] == "Mobility support"
    assert notes == []


def test_hard_sparring_wins_when_support_work_overlaps_same_day():
    plan = _structured_plan([_day("D-31", headline="Strength"), _day("D-29", headline="Aerobic")])
    reconcile_coach_led_sparring_days(
        plan,
        _light_support_friday_brief(hard_plan=_hard_friday()),
    )

    days = plan["weeks"][0]["days"]
    inserted = [day for day in days if day["countdown_label"] == "D-30"]
    assert len(inserted) == 1
    assert inserted[0]["today_card"]["headline"] == "Hard sparring"


def test_malformed_support_work_brief_is_noop():
    plan = _structured_plan([_day("D-30", headline="Recovery")])
    malformed_brief = {"weekly_role_map": {"weeks": [{"declared_support_work_days": "Friday"}]}}
    before = plan["weeks"][0]["days"][0]["today_card"]["headline"]

    assert reconcile_coach_led_sparring_days(plan, malformed_brief) == []
    assert plan["weeks"][0]["days"][0]["today_card"]["headline"] == before


def test_support_work_day_keeps_existing_app_session_without_contact_note():
    real_session = [{"title": "Mobility support", "blocks": []}]
    plan = _structured_plan([_day("D-30", headline="Mobility support", sessions=real_session)])
    notes = reconcile_coach_led_sparring_days(plan, _light_support_friday_brief())

    day = plan["weeks"][0]["days"][0]
    assert day["today_card"]["headline"] == "Mobility support"
    assert day["sessions"] == real_session
    assert len(plan["weeks"][0]["days"]) == 1
    assert notes == []
