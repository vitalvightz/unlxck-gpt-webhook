"""Countdown-aware calendar spine for normal camps.

Covers:
- per-day D-day mapping inside a week,
- the calendar_days metadata block,
- hard-sparring planner converting D-15+ days to technical (D-16 stays the
  last allowed declared day) and capping D-21..D-16 to a single effective
  hard exposure,
- no pre-fight session rendering after a Friday fight day.
"""

from fightcamp.fight_date_utils import build_calendar_days, d_day_for_weekday
from fightcamp.sparring_dose_planner import compute_hard_sparring_plan


def _week_with_calendar(*, end_d, span, fight_weekday="friday", **overrides):
    week = {
        "phase": overrides.pop("phase", "SPP"),
        "stage_key": overrides.pop("stage_key", "specific_density_build"),
        "week_index": 1,
        "phase_week_index": overrides.pop("phase_week_index", None),
        "phase_week_total": overrides.pop("phase_week_total", None),
        "projected_days_until_fight_start": end_d + span - 1,
        "projected_days_until_fight_end": end_d,
        "span_days": span,
        "fight_weekday": fight_weekday,
        "declared_hard_sparring_days": overrides.pop("hard_days", []),
        "session_roles": overrides.pop("session_roles", []),
    }
    week.update(overrides)
    return week


def _athlete(days_until_fight, *, hard_days, fight_weekday="friday"):
    return {
        "sport": "boxing",
        "fatigue": "low",
        "days_until_fight": days_until_fight,
        "weight_cut_pct": 0.0,
        "weight_cut_risk": False,
        "readiness_flags": [],
        "injuries": [],
        "hard_sparring_days": hard_days,
        "fight_date": None,
        "fight_weekday": fight_weekday,
    }


# ── Calendar spine primitives ─────────────────────────────────────────────────

def test_d_day_for_weekday_friday_fight_resolves_each_weekday():
    # Final week: ends at D-1 (Thursday before Friday fight), span 7.
    assert d_day_for_weekday("thursday", fight_weekday="friday",
                             projected_days_until_fight_end=1, span_days=7) == 1
    assert d_day_for_weekday("friday", fight_weekday="friday",
                             projected_days_until_fight_end=1, span_days=7) == 7
    assert d_day_for_weekday("monday", fight_weekday="friday",
                             projected_days_until_fight_end=1, span_days=7) == 4


def test_d_day_for_weekday_returns_none_when_outside_week_span():
    # Final week with span 3: only the last 3 days before fight are in scope.
    assert d_day_for_weekday("monday", fight_weekday="friday",
                             projected_days_until_fight_end=1, span_days=3) is None
    assert d_day_for_weekday("wednesday", fight_weekday="friday",
                             projected_days_until_fight_end=1, span_days=3) == 2


def test_build_calendar_days_friday_fight_skips_post_fight_weekend():
    # 6-day final week ending at D-1. Because the role map clamps end_d to >= 1
    # for normal-camp weeks, no Saturday/Sunday AFTER fight day can appear here.
    days = build_calendar_days(fight_weekday="friday",
                               projected_days_until_fight_end=1, span_days=6)
    assert all(entry["d_day"] >= 1 for entry in days)
    assert all(entry["is_after_fight_day"] is False for entry in days)
    assert all(entry["is_fight_day"] is False for entry in days)
    # The day immediately before a Friday fight is always Thursday (D-1).
    assert days[-1] == {
        "weekday": "thursday",
        "d_day": 1,
        "is_fight_day": False,
        "is_after_fight_day": False,
    }


def test_build_calendar_days_marks_fight_day_when_d0_in_range():
    days = build_calendar_days(fight_weekday="friday",
                               projected_days_until_fight_end=0, span_days=1)
    assert days == [
        {"weekday": "friday", "d_day": 0, "is_fight_day": True, "is_after_fight_day": False}
    ]


# ── Hard sparring per-day countdown rules ─────────────────────────────────────

def test_d15_hard_sparring_converts_to_technical():
    # 4-week camp, week 2 covers D-20..D-14. Friday fight → Wednesday is D-16
    # (last allowed declared day) and Friday is D-14 (banned).
    week = _week_with_calendar(
        end_d=14, span=7, fight_weekday="friday",
        hard_days=["Monday", "Wednesday", "Friday"],
    )
    plan = compute_hard_sparring_plan(
        week=week,
        athlete_snapshot=_athlete(20, hard_days=["Monday", "Wednesday", "Friday"]),
    )
    by_day = {entry["day"]: entry for entry in plan}

    # Friday is D-14: inside the ban → convert to technical.
    assert by_day["Friday"]["status"] == "convert_to_technical_suggested"
    assert by_day["Friday"]["effective_load"] == "technical"
    assert "d15_hard_sparring_ban" in by_day["Friday"]["reason_codes"]

    # Monday (D-18) and Wednesday (D-16) are both in the D-21..D-16 cap band,
    # so exactly one stays hard. Wednesday is D-16 specifically — it must NOT
    # be converted, because the dict still calls it the last allowed day.
    assert by_day["Wednesday"]["d_day"] == 16
    assert by_day["Wednesday"]["effective_load"] != "technical"
    assert by_day["Monday"]["d_day"] == 18
    band_hard = sum(
        1 for day in ("Monday", "Wednesday")
        if by_day[day]["effective_load"] == "hard"
    )
    assert band_hard == 1


def test_d16_remains_last_allowed_hard_spar_day():
    # Friday fight, week of D-22..D-16 — Wednesday is D-16. Only one declared
    # hard day inside the cap band → it stays hard, matching the long-standing
    # _COUNTDOWN_COACH_NOTES[16] semantics.
    week = _week_with_calendar(
        end_d=16, span=7, fight_weekday="friday",
        hard_days=["Wednesday"],
    )
    plan = compute_hard_sparring_plan(
        week=week,
        athlete_snapshot=_athlete(22, hard_days=["Wednesday"]),
    )
    assert plan[0]["day"] == "Wednesday"
    assert plan[0]["d_day"] == 16
    assert plan[0]["effective_load"] == "hard"


def test_d21_d16_window_caps_to_one_effective_hard_day():
    # Week ends at D-16, span 6, days D-16..D-21 — fully inside the cap window.
    # Friday fight → D-16 = Wednesday, D-21 = Friday.
    week = _week_with_calendar(
        end_d=16, span=6, fight_weekday="friday",
        hard_days=["Friday", "Wednesday"],
    )
    plan = compute_hard_sparring_plan(
        week=week,
        athlete_snapshot=_athlete(22, hard_days=["Friday", "Wednesday"]),
    )
    statuses = {entry["day"]: entry["status"] for entry in plan}

    hard_count = sum(1 for status in statuses.values() if status == "hard_as_planned")
    assert hard_count == 1, statuses
    assert any("d21_d16_cap_one" in entry.get("reason_codes", []) for entry in plan)


def test_normal_week_outside_d21_keeps_hard_sparring_as_declared():
    # 4-week camp, week 1 covers D-27..D-21. With Friday fight, every weekday is >=22.
    week = _week_with_calendar(
        end_d=21, span=7, fight_weekday="friday",
        hard_days=["Tuesday", "Thursday"],
    )
    plan = compute_hard_sparring_plan(
        week=week,
        athlete_snapshot=_athlete(27, hard_days=["Tuesday", "Thursday"]),
    )
    assert all(entry["status"] == "hard_as_planned" for entry in plan)
    assert all(entry["d_day"] >= 22 for entry in plan)


# ── Normal-camp role-map integration: 4-week and 12-week ──────────────────────

def test_normal_camp_4_week_emits_calendar_metadata_and_bans_d15():
    from fightcamp.stage2_role_map import _build_weekly_role_map

    athlete_model = {
        "sport": "boxing",
        "status": "amateur",
        "rounds_format": "3x3",
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        "hard_sparring_days": ["monday", "wednesday", "friday"],
        "fatigue": "low",
        "weight_cut_pct": 0.0,
        "weight_cut_risk": False,
        "readiness_flags": [],
        "injuries": [],
        "fight_date": "2026-05-29",  # Friday
        "days_until_fight": 28,
    }
    progression = {
        "weeks": [
            {"week_index": 1, "phase": "GPP", "stage_key": "general_capacity",
             "phase_week_index": 1, "phase_week_total": 1, "span_days": 7,
             "session_counts": {"strength": 2, "conditioning": 2, "recovery": 1}},
            {"week_index": 2, "phase": "SPP", "stage_key": "specific_density_build",
             "phase_week_index": 1, "phase_week_total": 2, "span_days": 7,
             "session_counts": {"strength": 2, "conditioning": 2, "recovery": 1}},
            {"week_index": 3, "phase": "SPP", "stage_key": "specific_density_build",
             "phase_week_index": 2, "phase_week_total": 2, "span_days": 7,
             "session_counts": {"strength": 2, "conditioning": 2, "recovery": 1}},
            {"week_index": 4, "phase": "TAPER", "stage_key": "taper_sharpen",
             "phase_week_index": 1, "phase_week_total": 1, "span_days": 7,
             "session_counts": {"strength": 1, "conditioning": 1, "recovery": 1}},
        ]
    }
    role_map = _build_weekly_role_map(
        athlete_model, progression, {"key": "general_fight_readiness"}
    )

    weeks = role_map["weeks"]
    assert len(weeks) == 4
    for week in weeks:
        assert week["calendar_days"], "every week needs a calendar spine"
        assert week["countdown_range"], "every week needs a countdown range"
        assert week["projected_days_until_fight_end"] >= 0
        # No pre-fight day appears AFTER the fight day (Friday).
        assert all(day["is_after_fight_day"] is False for day in week["calendar_days"])

    # Week 3 ends at D-7 → all days fall inside the D-15 ban → all converted.
    week_3_plan = weeks[2]["hard_sparring_plan"]
    assert all(entry["effective_load"] != "hard" for entry in week_3_plan)


def test_normal_camp_12_week_attaches_calendar_to_every_week():
    from fightcamp.stage2_role_map import _build_weekly_role_map

    athlete_model = {
        "sport": "boxing",
        "status": "amateur",
        "rounds_format": "3x3",
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        "hard_sparring_days": ["tuesday", "thursday"],
        "fatigue": "low",
        "weight_cut_pct": 0.0,
        "weight_cut_risk": False,
        "readiness_flags": [],
        "injuries": [],
        "fight_date": "2026-07-24",  # Friday
        "days_until_fight": 84,
    }
    weeks_input = []
    for idx in range(1, 13):
        if idx <= 4:
            phase, stage = "GPP", "general_capacity"
            pwi, pwt = idx, 4
        elif idx <= 10:
            phase, stage = "SPP", "specific_density_build"
            pwi, pwt = idx - 4, 6
        else:
            phase, stage = "TAPER", "taper_sharpen"
            pwi, pwt = idx - 10, 2
        weeks_input.append({
            "week_index": idx, "phase": phase, "stage_key": stage,
            "phase_week_index": pwi, "phase_week_total": pwt, "span_days": 7,
            "session_counts": {"strength": 2, "conditioning": 2, "recovery": 1},
        })
    role_map = _build_weekly_role_map(
        athlete_model, {"weeks": weeks_input}, {"key": "general_fight_readiness"}
    )

    weeks = role_map["weeks"]
    assert len(weeks) == 12
    all_d_days = [day["d_day"] for week in weeks for day in week["calendar_days"]]
    # Spine starts the day after generation (D-83) and ends on fight day (D-0).
    assert min(all_d_days) == 0
    assert max(all_d_days) == 83

    # Week 12 ends at D-0 → its declared Tue/Thu both fall inside D-15.
    final_plan = weeks[-1]["hard_sparring_plan"]
    assert all(entry["effective_load"] != "hard" for entry in final_plan)
