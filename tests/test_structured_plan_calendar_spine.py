"""The structured calendar must be continuous and Mon-Sun, whatever the converter did.

These lock down :func:`api.structured_plan_calendar_spine.reconcile_calendar_spine`,
which rebuilds a dated camp's ``structured_plan.weeks`` from the deterministic
role-map spine so that, for a camp beginning on D-N, every countdown day
D-N..D-0 exists exactly once — as a session day or a no-session rest day — grouped
into the Mon-Sun calendar weeks the web view renders, with each week's phase and
boundaries owned by the authoritative calendar rather than the surviving sessions.

Root cause reproduced here
--------------------------
A sparse (often non-boxing) camp converts into a plan whose ``weeks[*].days`` hold
only session-bearing days. The web view then derives week boundaries, date /
countdown ranges, app/coach counts and phase from the surviving days, so a week
collapses to a single day, a converter mega-week is cut by ``splitWeekByCalendarWeek``
into single-day tabs that all read one phase, and D-days disappear instead of
existing as no-session days.
"""
from __future__ import annotations

from datetime import date, timedelta

from api.structured_plan_calendar_spine import reconcile_calendar_spine
from api.structured_plan_models import validate_structured_plan
from fightcamp.stage2_role_map import _build_weekly_role_map


FIGHT_DATE = "2026-09-17"  # Thursday
FIGHT = date(2026, 9, 17)
_WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ── builders ──────────────────────────────────────────────────────────────────

def _iso(d_day: int) -> str:
    return (FIGHT - timedelta(days=d_day)).isoformat()


def _weekday(d_day: int) -> str:
    return _WEEKDAY_SHORT[(FIGHT - timedelta(days=d_day)).weekday()]


def _session(d_day: int, *, session_id: str | None = None, title: str | None = None) -> dict:
    return {
        "session_id": session_id or f"sess-{d_day}",
        "session_type": "strength_power",
        "title": title or f"Work {d_day}",
        "objective": "x",
        "completion_status": "not_started",
        "mindset_anchor": {"intent": "i", "focus_cue": "f", "reset_cue": "r"},
        "blocks": [],
    }


def _session_day(
    d_day: int,
    *,
    phase: str = "TAPER",
    title: str | None = None,
    iso: str | None = None,
    weekday: str | None = None,
    sessions: list | None = None,
    headline: str | None = None,
) -> dict:
    return {
        "date": iso if iso is not None else _iso(d_day),
        "weekday": weekday if weekday is not None else _weekday(d_day),
        "day_type": "high",
        "countdown_label": f"D-{d_day}",
        "phase_label": phase,
        "today_card": {
            "headline": headline if headline is not None else f"Session {d_day}",
            "readiness_status": "train_as_planned",
            "mindset_anchor": {"intent": "i", "focus_cue": "f", "reset_cue": "r"},
        },
        "sessions": sessions if sessions is not None else [_session(d_day, title=title)],
    }


def _coach_only_day(d_day: int, *, phase: str = "SPP", headline: str = "Hard sparring") -> dict:
    """A declared contact day with no app session (coach-owned work)."""
    return {
        "date": _iso(d_day),
        "weekday": _weekday(d_day),
        "day_type": "high",
        "countdown_label": f"D-{d_day}",
        "phase_label": phase,
        "today_card": {
            "headline": headline,
            "readiness_status": "train_as_planned",
            "mindset_anchor": {"intent": "", "focus_cue": "", "reset_cue": ""},
        },
        "sessions": [],
    }


def _week(days: list[dict], *, index: int = 1, phase: str = "TAPER", goal: str = "Goal") -> dict:
    ddays = [int(d["countdown_label"][2:]) for d in days if str(d["countdown_label"]).startswith("D-")]
    if not ddays:
        ddays = [0]
    return {
        "week_id": f"wk-{index}",
        "week_index": index,
        "phase_label": phase,
        "week_goal": goal,
        "start_date": days[0]["date"],
        "end_date": days[-1]["date"],
        "countdown_start": f"D-{max(ddays)}",
        "countdown_end": f"D-{min(ddays)}",
        "load_focus": {
            "volume": "moderate",
            "intensity": "moderate",
            "specificity": "moderate",
            "fatigue_target": "moderate",
        },
        "progression": {"week_type": "build", "planned_change_from_previous": ""},
        "days": days,
    }


def _plan(weeks: list[dict], *, fight_date: str = FIGHT_DATE) -> dict:
    return {
        "schema_version": "1.0",
        "plan_metadata": {
            "title": "t",
            "sport": "mma",
            "plan_type": "fight_camp",
            "timezone": "UTC",
            "status": "active",
            "units": "metric",
        },
        "athlete_context": {"sport_profile": "mma"},
        "event_context": {"event_type": "fight", "fight_date": fight_date},
        "countdown_labels": [],
        "red_flag_rules": [],
        "plan_notes": [],
        "weeks": weeks,
        "daily_check_ins": [],
        "nutrition": {
            "summary": "s",
            "daily_focus": "d",
            "training_day_guidance": "t",
            "fight_week_guidance": "f",
        },
        "progression_notes": "",
        "raw_markdown_fallback": "",
    }


def _role_map(*, days_until_fight: int, sport: str = "mma", fight_date: str = FIGHT_DATE) -> dict:
    athlete_model = {
        "sport": sport,
        "status": "amateur",
        "rounds_format": "3x5",
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday", "sunday"],
        "hard_sparring_days": ["tuesday", "thursday"],
        "support_work_days": ["monday"],
        "fatigue": "low",
        "weight_cut_pct": 0.0,
        "weight_cut_risk": False,
        "readiness_flags": [],
        "injuries": [],
        "fight_date": fight_date,
        "days_until_fight": days_until_fight,
    }
    week_count = max(1, days_until_fight // 7)
    weeks_input = []
    for idx in range(1, week_count + 1):
        phase = "SPP" if idx <= (week_count - 1) else "TAPER"
        weeks_input.append(
            {
                "week_index": idx,
                "phase": phase,
                "stage_key": "x",
                "phase_week_index": 1,
                "phase_week_total": 2,
                "span_days": 7,
                "session_counts": {"strength": 2, "conditioning": 1, "recovery": 1},
            }
        )
    return _build_weekly_role_map(
        athlete_model, {"weeks": weeks_input}, {"key": "general_fight_readiness"}
    )


def _brief(*, days_until_fight: int = 21, sport: str = "mma", fight_date: str = FIGHT_DATE) -> dict:
    return {
        "weekly_role_map": _role_map(days_until_fight=days_until_fight, sport=sport, fight_date=fight_date),
        "fight_date": fight_date,
        "days_until_fight": days_until_fight,
    }


def _late_fight_brief() -> dict:
    return {
        "weekly_role_map": {
            "weeks": [
                {"week_index": 1, "phase": "TAPER", "countdown_span": {"start_day": 20, "end_day": 14}},
                {"week_index": 2, "phase": "TAPER", "countdown_span": {"start_day": 13, "end_day": 7}},
                {"week_index": 3, "phase": "TAPER", "countdown_span": {"start_day": 6, "end_day": 0}},
            ]
        },
        "fight_date": FIGHT_DATE,
        "days_until_fight": 20,
    }


def _all_ddays(plan: dict) -> list[int]:
    return sorted(
        (int(day["countdown_label"][2:]) for week in plan["weeks"] for day in week["days"]),
        reverse=True,
    )


def _monday(iso: str) -> date:
    d = date.fromisoformat(iso[:10])
    return d - timedelta(days=d.weekday())


def _assert_mon_sun(plan: dict) -> None:
    """Every rebuilt week is a single Mon-Sun block spanning at most seven days.

    This is exactly what the frontend's splitWeekByCalendarWeek expects; a week
    wider than seven days would be re-cut (or, at exactly seven, wrongly not).
    """
    for week in plan["weeks"]:
        days = week["days"]
        mondays = {_monday(d["date"]) for d in days}
        assert len(mondays) == 1, f"week {week['week_index']} straddles calendar weeks: {mondays}"
        span = (date.fromisoformat(days[-1]["date"]) - date.fromisoformat(days[0]["date"])).days
        assert 0 <= span <= 6, f"week {week['week_index']} spans {span} days (must be <=6 for one calendar week)"
    # Weeks run earliest -> latest and never overlap.
    week_mondays = [_monday(w["days"][0]["date"]) for w in plan["weeks"]]
    assert week_mondays == sorted(week_mondays)
    assert len(week_mondays) == len(set(week_mondays))


def _assert_continuous_to_fight(plan: dict, camp_start: int) -> None:
    assert _all_ddays(plan) == list(range(camp_start, -1, -1))
    ddays = [int(d["countdown_label"][2:]) for w in plan["weeks"] for d in w["days"]]
    assert len(ddays) == len(set(ddays)), "one calendar-day identity per countdown"


# ── the observed production failure: one sparse mega-week -> Mon-Sun weeks ─────

def test_sparse_mega_week_rebuilds_mon_sun_weeks_with_authoritative_phases():
    # The MMA production case: every session day collapsed into ONE week stamped
    # TAPER. The reconcile restores the Mon-Sun calendar the UI renders.
    mega = [_session_day(d) for d in [20, 17, 16, 14, 10, 9, 7, 6, 3, 2, 0]]
    plan = _plan([_week(mega, index=1, phase="TAPER", goal="Taper")])

    out = reconcile_calendar_spine(plan, _brief())
    validate_structured_plan(out)
    _assert_mon_sun(out)
    _assert_continuous_to_fight(out, 21)

    ranges = [(w["countdown_start"], w["countdown_end"]) for w in out["weeks"]]
    assert ranges == [("D-21", "D-18"), ("D-17", "D-11"), ("D-10", "D-4"), ("D-3", "D-0")]
    # Not one blanket "Taper" label: the sharp fight week is TAPER, the build
    # weeks are not.
    phases = [w["phase_label"] for w in out["weeks"]]
    assert phases[-1] == "TAPER"
    assert set(phases) != {"TAPER"}, "phases must not all collapse to one label"


def test_week_dates_come_from_the_full_calendar_not_surviving_sessions():
    mega = [_session_day(d) for d in [20, 17, 16, 14, 10, 9, 7, 6, 3, 2, 0]]
    out = reconcile_calendar_spine(_plan([_week(mega, index=1, phase="TAPER")]), _brief())
    w1 = out["weeks"][0]
    # NOT a one-day window: Thu D-21 through Sun D-18.
    assert w1["countdown_start"] == "D-21" and w1["countdown_end"] == "D-18"
    assert w1["start_date"] == _iso(21) and w1["end_date"] == _iso(18)
    assert w1["days"][0]["weekday"] == "Thu" and w1["days"][-1]["weekday"] == "Sun"


def test_every_no_session_day_exists_once_as_a_rest_day():
    mega = [_session_day(d) for d in [20, 17, 16, 14, 10, 9, 7, 6, 3, 2, 0]]
    out = reconcile_calendar_spine(_plan([_week(mega, index=1, phase="TAPER")]), _brief())
    by_dday = {int(d["countdown_label"][2:]): d for w in out["weeks"] for d in w["days"]}
    rest = by_dday[19]  # carried no session in the source
    assert rest["sessions"] == []
    assert rest["day_type"] == "rest"
    assert rest["today_card"]["headline"] == ""  # renders as a compact rest row
    assert rest["date"] == _iso(19) and rest["weekday"] == _weekday(19)


def test_session_content_is_preserved_verbatim():
    day = _session_day(16, title="Back Squat")
    day["today_card"]["coach_led_contact"] = "Technical-only combat"
    plan = _plan([_week([_session_day(20), day, _session_day(0)], index=1, phase="TAPER")])
    out = reconcile_calendar_spine(plan, _brief())
    kept = next(d for w in out["weeks"] for d in w["days"] if d["countdown_label"] == "D-16")
    assert kept["sessions"][0]["title"] == "Back Squat"
    assert kept["sessions"][0]["session_id"] == "sess-16"
    assert kept["today_card"]["coach_led_contact"] == "Technical-only combat"


# ── Issue 2: continuity alone is not enough ───────────────────────────────────

def test_dense_continuous_mega_week_is_still_regrouped_and_rephased():
    # Every D-day D-20..D-0 is present, but in ONE week labelled TAPER. Continuity
    # must NOT short-circuit the reconcile: the week structure and phases are still
    # wrong and must be rebuilt.
    dense = [_session_day(d, phase="TAPER", title=f"w{d}") for d in range(20, -1, -1)]
    plan = _plan([_week(dense, index=1, phase="TAPER")])
    out = reconcile_calendar_spine(plan, _brief())
    assert out is not plan, "a continuous-but-mega week is rebuilt, not skipped"
    _assert_mon_sun(out)
    assert len(out["weeks"]) == 4
    assert set(w["phase_label"] for w in out["weeks"]) != {"TAPER"}


def test_already_correct_plan_is_a_true_no_op():
    # Reconcile once to reach the authoritative form, then reconciling again must
    # change nothing (identical Mon-Sun grouping + phases + calendar identity).
    mega = [_session_day(d) for d in [20, 17, 14, 10, 7, 3, 0]]
    brief = _brief()
    once = reconcile_calendar_spine(_plan([_week(mega, index=1, phase="TAPER")]), brief)
    twice = reconcile_calendar_spine(once, brief)
    assert twice is once


# ── Issue 3: the planner calendar is authoritative, not the converter's ────────

def test_wrong_converter_date_and_weekday_are_corrected():
    bad = _session_day(14, title="Bench", iso="2025-01-01", weekday="Sun")
    plan = _plan([_week([_session_day(20), bad, _session_day(0)], index=1, phase="TAPER")])
    out = reconcile_calendar_spine(plan, _brief())
    fixed = next(d for w in out["weeks"] for d in w["days"] if d["countdown_label"] == "D-14")
    assert fixed["date"] == _iso(14), "date is fight_date minus the countdown, not the converter's"
    assert fixed["weekday"] == _weekday(14)
    assert fixed["sessions"][0]["title"] == "Bench", "content preserved while calendar is corrected"


# ── Issue 4: D-N exists even with no session, from days_until_fight ────────────

def test_empty_camp_start_day_is_kept_from_days_until_fight():
    # No D-21 session, and the role-map spine only computes D-20..D-0 — but the
    # athlete is 21 days out, so D-21 must still exist as a rest day.
    mega = [_session_day(d) for d in [20, 17, 14, 10, 7, 3, 0]]
    out = reconcile_calendar_spine(_plan([_week(mega, index=1, phase="TAPER")]), _brief(days_until_fight=21))
    _assert_continuous_to_fight(out, 21)
    d21 = next(d for w in out["weeks"] for d in w["days"] if d["countdown_label"] == "D-21")
    assert d21["sessions"] == [] and d21["day_type"] == "rest"
    assert out["weeks"][0]["countdown_start"] == "D-21"


def test_extent_ignores_absurd_days_until_fight():
    # A garbled days_until_fight far beyond the (short, 21-day) spine must not
    # balloon the calendar — the role-map spine bounds the extent.
    mega = [_session_day(d) for d in [20, 14, 7, 0]]
    brief = {
        "weekly_role_map": _role_map(days_until_fight=21),  # spine reaches D-20
        "fight_date": FIGHT_DATE,
        "days_until_fight": 900,  # garbled
    }
    out = reconcile_calendar_spine(_plan([_week(mega, index=1, phase="TAPER")]), brief)
    assert _all_ddays(out)[0] <= 20 + 14, "extent is bounded to a sane lead-in"


# ── content preservation edge cases the reviewer called out ───────────────────

def test_duplicate_calendar_day_rows_merge_into_one_identity():
    # The converter split one calendar day into two rows (same D-day). They must
    # collapse to a single day carrying BOTH sessions, never a duplicate identity.
    row_a = _session_day(16, sessions=[_session(16, session_id="a", title="Squat")])
    row_b = _session_day(16, sessions=[_session(16, session_id="b", title="Row")])
    plan = _plan([_week([_session_day(20), row_a, row_b, _session_day(0)], index=1, phase="TAPER")])
    out = reconcile_calendar_spine(plan, _brief())
    d16 = [d for w in out["weeks"] for d in w["days"] if d["countdown_label"] == "D-16"]
    assert len(d16) == 1, "one calendar-day identity for D-16"
    titles = {s["title"] for s in d16[0]["sessions"]}
    assert titles == {"Squat", "Row"}, "both rows' sessions preserved"


def test_multi_session_day_is_kept_as_one_day():
    multi = _session_day(
        14, sessions=[_session(14, session_id="am", title="AM"), _session(14, session_id="pm", title="PM")]
    )
    plan = _plan([_week([_session_day(20), multi, _session_day(0)], index=1, phase="TAPER")])
    out = reconcile_calendar_spine(plan, _brief())
    d14 = [d for w in out["weeks"] for d in w["days"] if d["countdown_label"] == "D-14"]
    assert len(d14) == 1 and len(d14[0]["sessions"]) == 2


def test_coach_only_sessionless_day_is_preserved_not_reset():
    # A declared contact day carries no app session; the spine must keep its
    # headline and empty sessions, not overwrite it with a blank rest day.
    coach = _coach_only_day(16, headline="Hard sparring")
    plan = _plan([_week([_session_day(20), coach, _session_day(0)], index=1, phase="TAPER")])
    out = reconcile_calendar_spine(plan, _brief())
    d16 = next(d for w in out["weeks"] for d in w["days"] if d["countdown_label"] == "D-16")
    assert d16["sessions"] == []
    assert d16["today_card"]["headline"] == "Hard sparring", "coach-owned contact kept"


def test_app_session_count_is_unchanged_by_filled_rest_days():
    mega = [_session_day(d) for d in [20, 17, 16, 14, 10, 9, 7, 6, 3, 2, 0]]
    out = reconcile_calendar_spine(_plan([_week(mega, index=1, phase="TAPER")]), _brief())
    total = sum(len(d["sessions"]) for w in out["weeks"] for d in w["days"])
    assert total == len(mega), "session days preserved; rest days add zero sessions"


# ── contracts and cross-sport ─────────────────────────────────────────────────

def test_late_fight_countdown_span_contract_is_understood():
    mega = [_session_day(d) for d in [20, 17, 16, 14, 10, 7, 6, 2, 0]]
    out = reconcile_calendar_spine(_plan([_week(mega, index=1, phase="TAPER")]), _late_fight_brief())
    validate_structured_plan(out)
    _assert_mon_sun(out)
    _assert_continuous_to_fight(out, 20)


def test_invariant_holds_for_boxing_too():
    # Sport-independent: a sparse boxing camp gets the same continuous Mon-Sun
    # calendar as MMA.
    mega = [_session_day(d) for d in [27, 20, 14, 7, 3, 0]]
    brief = _brief(days_until_fight=28, sport="boxing")
    out = reconcile_calendar_spine(_plan([_week(mega, index=1, phase="TAPER")]), brief)
    validate_structured_plan(out)
    _assert_mon_sun(out)
    _assert_continuous_to_fight(out, 28)


def test_multiple_sparse_aligned_weeks_are_each_completed():
    w1 = _week([_session_day(20), _session_day(16)], index=1, phase="SPP")
    w2 = _week([_session_day(13), _session_day(9)], index=2, phase="SPP")
    w3 = _week([_session_day(6), _session_day(0)], index=3, phase="TAPER")
    out = reconcile_calendar_spine(_plan([w1, w2, w3]), _brief())
    validate_structured_plan(out)
    _assert_mon_sun(out)
    _assert_continuous_to_fight(out, 21)


def test_missing_fight_day_is_inserted_as_competition_day():
    mega = [_session_day(d) for d in [20, 14, 7, 2]]  # no D-0
    out = reconcile_calendar_spine(_plan([_week(mega, index=1, phase="TAPER")]), _brief())
    fight = next(d for w in out["weeks"] for d in w["days"] if d["countdown_label"] == "D-0")
    assert fight["day_type"] == "competition"
    assert fight["today_card"]["headline"] == "Fight day"


def test_output_is_schema_valid_and_week_indices_are_sequential():
    mega = [_session_day(d) for d in [20, 17, 16, 14, 10, 9, 7, 6, 3, 2, 0]]
    out = reconcile_calendar_spine(_plan([_week(mega, index=1, phase="TAPER")]), _brief())
    validate_structured_plan(out)
    assert [w["week_index"] for w in out["weeks"]] == list(range(1, len(out["weeks"]) + 1))


# ── no-op safety: never touch what it should not ──────────────────────────────

def test_open_plan_is_never_touched():
    plan = _plan([_week([_session_day(d) for d in [20, 14, 7, 0]], index=1, phase="TAPER")])
    brief = dict(_brief())
    brief["open_plan_spec"] = {"plan_type": "open_ongoing_system"}
    assert reconcile_calendar_spine(plan, brief) is plan


def test_missing_fight_date_is_a_no_op():
    plan = _plan([_week([_session_day(d) for d in [20, 14, 7, 0]], index=1, phase="TAPER")])
    assert reconcile_calendar_spine(plan, {"weekly_role_map": _role_map(days_until_fight=21)}) is plan


def test_missing_role_map_is_a_no_op():
    plan = _plan([_week([_session_day(d) for d in [20, 14, 7, 0]], index=1, phase="TAPER")])
    assert reconcile_calendar_spine(plan, {"fight_date": FIGHT_DATE}) is plan


def test_malformed_inputs_are_no_ops():
    assert reconcile_calendar_spine(None, {}) is None
    assert reconcile_calendar_spine({"weeks": []}, {}) == {"weeks": []}
    plan = _plan([_week([_session_day(20)], index=1)])
    assert reconcile_calendar_spine(plan, "not a brief") is plan


def test_plan_with_no_resolvable_calendar_identity_is_a_no_op():
    day = _session_day(20)
    day["countdown_label"] = ""
    day["date"] = ""
    plan = _plan([_week([day], index=1, phase="TAPER")])
    assert reconcile_calendar_spine(plan, _brief()) is plan


def test_never_raises_on_garbage_role_map():
    plan = _plan([_week([_session_day(d) for d in [20, 14, 7, 0]], index=1, phase="TAPER")])
    brief = {"weekly_role_map": {"weeks": "nonsense"}, "fight_date": FIGHT_DATE, "days_until_fight": 21}
    assert reconcile_calendar_spine(plan, brief) is plan


def test_blank_countdown_label_day_is_recovered_from_its_date():
    labelled = _session_day(20, title="Deadlift")
    blank = _session_day(14, title="Bench")
    blank["countdown_label"] = ""  # label lost, date intact
    plan = _plan([_week([labelled, blank, _session_day(0)], index=1, phase="TAPER")])
    out = reconcile_calendar_spine(plan, _brief())
    validate_structured_plan(out)
    kept = next(d for w in out["weeks"] for d in w["days"] if d["date"] == _iso(14))
    assert kept["sessions"][0]["title"] == "Bench"
    assert kept["countdown_label"] == "D-14"
