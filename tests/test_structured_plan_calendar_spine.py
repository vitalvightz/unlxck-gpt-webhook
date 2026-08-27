"""The structured calendar must be continuous, whatever the converter produced.

These lock down :func:`api.structured_plan_calendar_spine.reconcile_calendar_spine`,
which rebuilds a dated camp's ``structured_plan.weeks`` from the deterministic
role-map spine so every countdown day D-N..D-0 exists exactly once — as a session
day or a no-session rest day — regardless of how sparse the converter's output was.

Root cause reproduced here
--------------------------
A sparse (often non-boxing) camp converts into a plan whose ``weeks[*].days`` hold
only session-bearing days. The web view then derives week boundaries, date /
countdown ranges, app/coach counts and phase from the surviving days, so a week
collapses to a single day ("D-21 -> D-21"), a converter mega-week is cut by the
frontend into single-day tabs that all read one phase, and D-days disappear
instead of existing as no-session days. The reconcile restores the spine.
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


def _session_day(d_day: int, *, phase: str = "TAPER", title: str | None = None) -> dict:
    return {
        "date": _iso(d_day),
        "weekday": _weekday(d_day),
        "day_type": "high",
        "countdown_label": f"D-{d_day}",
        "phase_label": phase,
        "today_card": {
            "headline": f"Session {d_day}",
            "readiness_status": "train_as_planned",
            "mindset_anchor": {"intent": "i", "focus_cue": "f", "reset_cue": "r"},
        },
        "sessions": [
            {
                "session_id": f"sess-{d_day}",
                "session_type": "strength_power",
                "title": title or f"Work {d_day}",
                "objective": "x",
                "completion_status": "not_started",
                "mindset_anchor": {"intent": "i", "focus_cue": "f", "reset_cue": "r"},
                "blocks": [],
            }
        ],
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


def _plan(weeks: list[dict]) -> dict:
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
        "event_context": {"event_type": "fight", "fight_date": FIGHT_DATE},
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


def _normal_camp_role_map(days_until_fight: int = 21) -> dict:
    athlete_model = {
        "sport": "mma",
        "status": "amateur",
        "rounds_format": "3x5",
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday", "sunday"],
        "hard_sparring_days": ["tuesday", "thursday"],
        "support_work_days": ["monday"],
        "fatigue": "low",
        "weight_cut_pct": 3.4,
        "weight_cut_risk": False,
        "readiness_flags": [],
        "injuries": [],
        "fight_date": FIGHT_DATE,
        "days_until_fight": days_until_fight,
    }
    weeks_input = []
    for idx in range(1, days_until_fight // 7 + 1):
        phase = "SPP" if idx <= (days_until_fight // 7 - 1) else "TAPER"
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


def _brief(role_map: dict) -> dict:
    return {"weekly_role_map": role_map, "fight_date": FIGHT_DATE}


def _late_fight_span_role_map() -> dict:
    return {
        "weeks": [
            {"week_index": 1, "phase": "TAPER", "countdown_span": {"start_day": 20, "end_day": 14}},
            {"week_index": 2, "phase": "TAPER", "countdown_span": {"start_day": 13, "end_day": 7}},
            {"week_index": 3, "phase": "TAPER", "countdown_span": {"start_day": 6, "end_day": 0}},
        ]
    }


def _all_ddays(plan: dict) -> list[int]:
    return sorted(
        (int(day["countdown_label"][2:]) for week in plan["weeks"] for day in week["days"]),
        reverse=True,
    )


# ── the observed production failure: one sparse mega-week ──────────────────────

def test_sparse_mega_week_rebuilds_continuous_spine_with_correct_phases():
    # The MMA production case: every session day collapsed into ONE week stamped
    # TAPER, spanning D-20..D-0. The reconcile must restore three correctly-phased
    # weeks with a gap-free calendar.
    session_ddays = [20, 17, 16, 14, 10, 9, 7, 6, 3, 2, 0]
    mega = [_session_day(d) for d in session_ddays]
    plan = _plan([_week(mega, index=1, phase="TAPER", goal="Taper")])

    out = reconcile_calendar_spine(plan, _brief(_normal_camp_role_map()))
    validate_structured_plan(out)  # schema-valid

    assert _all_ddays(out) == list(range(20, -1, -1)), "every D-day D-20..D-0 exists once"
    phases = [week["phase_label"] for week in out["weeks"]]
    assert phases == ["SPP", "SPP", "TAPER"], "phases follow the authoritative spine, not one blanket label"
    assert len(out["weeks"]) == 3


def test_week_boundaries_come_from_the_full_calendar_not_surviving_sessions():
    mega = [_session_day(d) for d in [20, 17, 16, 14, 10, 9, 7, 6, 3, 2, 0]]
    plan = _plan([_week(mega, index=1, phase="TAPER")])

    out = reconcile_calendar_spine(plan, _brief(_normal_camp_role_map()))
    week1 = out["weeks"][0]

    # NOT "D-20 -> D-20" / a one-day window: the week spans its whole countdown.
    assert week1["countdown_start"] == "D-20"
    assert week1["countdown_end"] == "D-14"
    assert week1["start_date"] == _iso(20)
    assert week1["end_date"] == _iso(14)


def test_every_no_session_day_exists_exactly_once_as_a_rest_day():
    mega = [_session_day(d) for d in [20, 17, 16, 14, 10, 9, 7, 6, 3, 2, 0]]
    plan = _plan([_week(mega, index=1, phase="TAPER")])

    out = reconcile_calendar_spine(plan, _brief(_normal_camp_role_map()))
    by_dday = {
        int(day["countdown_label"][2:]): day
        for week in out["weeks"]
        for day in week["days"]
    }
    # D-19 carried no session in the source -> it exists as a no-session rest day,
    # never a phantom or a dropped day.
    rest = by_dday[19]
    assert rest["sessions"] == []
    assert rest["day_type"] == "rest"
    assert rest["today_card"]["headline"] == ""  # renders as a compact rest row
    assert rest["date"] == _iso(19)
    assert rest["weekday"] == _weekday(19)


def test_session_content_is_preserved_verbatim():
    day = _session_day(16, title="Back Squat")
    day["today_card"]["coach_led_contact"] = "Technical-only combat"
    mega = [_session_day(20), day, _session_day(0)]
    plan = _plan([_week(mega, index=1, phase="TAPER")])

    out = reconcile_calendar_spine(plan, _brief(_normal_camp_role_map()))
    kept = next(
        d for week in out["weeks"] for d in week["days"] if d["countdown_label"] == "D-16"
    )
    assert kept["sessions"][0]["title"] == "Back Squat"
    assert kept["sessions"][0]["session_id"] == "sess-16"
    assert kept["today_card"]["coach_led_contact"] == "Technical-only combat"


# ── the invariant across contracts and shapes ─────────────────────────────────

def test_late_fight_countdown_span_contract_is_understood():
    mega = [_session_day(d) for d in [20, 17, 16, 14, 10, 7, 6, 2, 0]]
    plan = _plan([_week(mega, index=1, phase="TAPER")])

    out = reconcile_calendar_spine(plan, _brief(_late_fight_span_role_map()))
    validate_structured_plan(out)
    assert _all_ddays(out) == list(range(20, -1, -1))
    assert len(out["weeks"]) == 3


def test_multiple_sparse_aligned_weeks_are_each_filled():
    # The converter kept three weeks but each is sparse; every one is completed.
    w1 = _week([_session_day(20), _session_day(16)], index=1, phase="SPP")
    w2 = _week([_session_day(13), _session_day(9)], index=2, phase="SPP")
    w3 = _week([_session_day(6), _session_day(0)], index=3, phase="TAPER")
    plan = _plan([w1, w2, w3])

    out = reconcile_calendar_spine(plan, _brief(_normal_camp_role_map()))
    validate_structured_plan(out)
    assert _all_ddays(out) == list(range(20, -1, -1))
    assert [w["phase_label"] for w in out["weeks"]] == ["SPP", "SPP", "TAPER"]
    assert [len(w["days"]) for w in out["weeks"]] == [7, 7, 7]


def test_camp_start_edge_day_beyond_the_spine_is_kept_not_dropped():
    # The plan's first day (D-21) sits one further out than the role map's computed
    # spine (D-20..D-0). It must be preserved and extend week 1, not vanish.
    mega = [_session_day(21)] + [_session_day(d) for d in [20, 16, 14, 9, 6, 2, 0]]
    plan = _plan([_week(mega, index=1, phase="TAPER")])

    out = reconcile_calendar_spine(plan, _brief(_normal_camp_role_map()))
    validate_structured_plan(out)
    all_ddays = _all_ddays(out)
    assert all_ddays[0] == 21 and all_ddays[-1] == 0
    assert all_ddays == list(range(21, -1, -1))
    assert out["weeks"][0]["countdown_start"] == "D-21"
    kept = next(d for d in out["weeks"][0]["days"] if d["countdown_label"] == "D-21")
    assert kept["sessions"], "the edge session day keeps its content"


def test_missing_fight_day_is_inserted_as_competition_day():
    # Converter dropped D-0 entirely. It must exist, named as the fight, never as
    # ordinary rest.
    mega = [_session_day(d) for d in [20, 14, 7, 2]]
    plan = _plan([_week(mega, index=1, phase="TAPER")])

    out = reconcile_calendar_spine(plan, _brief(_normal_camp_role_map()))
    fight_day = next(
        d for week in out["weeks"] for d in week["days"] if d["countdown_label"] == "D-0"
    )
    assert fight_day["day_type"] == "competition"
    assert fight_day["today_card"]["headline"] == "Fight day"


def test_no_calendar_day_is_duplicated():
    mega = [_session_day(d) for d in [20, 17, 16, 14, 10, 9, 7, 6, 3, 2, 0]]
    plan = _plan([_week(mega, index=1, phase="TAPER")])

    out = reconcile_calendar_spine(plan, _brief(_normal_camp_role_map()))
    ddays = [int(d["countdown_label"][2:]) for w in out["weeks"] for d in w["days"]]
    assert len(ddays) == len(set(ddays)), "one calendar-day identity per countdown"


def test_reconcile_is_idempotent():
    mega = [_session_day(d) for d in [20, 17, 16, 14, 10, 9, 7, 6, 3, 2, 0]]
    plan = _plan([_week(mega, index=1, phase="TAPER")])
    brief = _brief(_normal_camp_role_map())

    once = reconcile_calendar_spine(plan, brief)
    twice = reconcile_calendar_spine(once, brief)
    # A now-continuous calendar is left untouched on the second pass.
    assert twice is once


# ── no-op safety: never touch what it should not ──────────────────────────────

def test_dense_continuous_camp_is_returned_untouched():
    dense = [_session_day(d, phase="SPP") for d in range(20, -1, -1)]
    plan = _plan([_week(dense, index=1, phase="SPP")])
    out = reconcile_calendar_spine(plan, _brief(_normal_camp_role_map()))
    assert out is plan, "a calendar already continuous is a no-op (zero regression)"


def test_open_plan_is_never_touched():
    mega = [_session_day(d) for d in [20, 14, 7, 0]]
    plan = _plan([_week(mega, index=1, phase="TAPER")])
    brief = {
        "weekly_role_map": _normal_camp_role_map(),
        "fight_date": FIGHT_DATE,
        "open_plan_spec": {"plan_type": "open_ongoing_system"},
    }
    assert reconcile_calendar_spine(plan, brief) is plan


def test_missing_fight_date_is_a_no_op():
    mega = [_session_day(d) for d in [20, 14, 7, 0]]
    plan = _plan([_week(mega, index=1, phase="TAPER")])
    assert reconcile_calendar_spine(plan, {"weekly_role_map": _normal_camp_role_map()}) is plan


def test_missing_role_map_is_a_no_op():
    mega = [_session_day(d) for d in [20, 14, 7, 0]]
    plan = _plan([_week(mega, index=1, phase="TAPER")])
    assert reconcile_calendar_spine(plan, {"fight_date": FIGHT_DATE}) is plan


def test_malformed_inputs_are_no_ops():
    assert reconcile_calendar_spine(None, {}) is None
    assert reconcile_calendar_spine({"weeks": []}, {}) == {"weeks": []}
    plan = _plan([_week([_session_day(20)], index=1)])
    assert reconcile_calendar_spine(plan, "not a brief") is plan


def test_blank_countdown_label_day_is_recovered_from_its_date():
    # A session day whose countdown_label went blank is still placed (and kept)
    # via its ISO date, never dropped or turned into a rest day.
    labelled = _session_day(20, title="Deadlift")
    blank = _session_day(14, title="Bench")
    blank["countdown_label"] = ""  # label lost, date intact
    plan = _plan([_week([labelled, blank, _session_day(0)], index=1, phase="TAPER")])

    out = reconcile_calendar_spine(plan, _brief(_normal_camp_role_map()))
    validate_structured_plan(out)
    kept = next(
        d for week in out["weeks"] for d in week["days"] if d["date"] == _iso(14)
    )
    assert kept["sessions"][0]["title"] == "Bench", "the label-less day keeps its session"
    assert kept["countdown_label"] == "D-14", "and gets its authoritative label back"
    assert _all_ddays(out) == list(range(20, -1, -1))


def test_plan_with_no_resolvable_calendar_identity_is_a_no_op():
    # Neither a countdown label nor a date on any day -> nothing to map onto the
    # spine, so the converter output is left untouched (never nuked to rest days).
    day = _session_day(20)
    day["countdown_label"] = ""
    day["date"] = ""
    plan = _plan([_week([day], index=1, phase="TAPER")])
    assert reconcile_calendar_spine(plan, _brief(_normal_camp_role_map())) is plan


def test_never_raises_on_garbage_role_map():
    mega = [_session_day(d) for d in [20, 14, 7, 0]]
    plan = _plan([_week(mega, index=1, phase="TAPER")])
    brief = {"weekly_role_map": {"weeks": "nonsense"}, "fight_date": FIGHT_DATE}
    # Degrades to a silent no-op rather than blowing up the card pipeline.
    assert reconcile_calendar_spine(plan, brief) is plan


# ── counts derive from the full calendar, not surviving sessions ──────────────

def test_app_session_count_is_unchanged_by_filled_rest_days():
    # Rest days carry no sessions, so the athlete-facing app-session count for a
    # week counts only the real sessions — the fill never inflates it.
    mega = [_session_day(d) for d in [20, 17, 16, 14, 10, 9, 7, 6, 3, 2, 0]]
    plan = _plan([_week(mega, index=1, phase="TAPER")])
    out = reconcile_calendar_spine(plan, _brief(_normal_camp_role_map()))

    total_sessions = sum(
        len(day["sessions"]) for week in out["weeks"] for day in week["days"]
    )
    assert total_sessions == len(mega), "session days preserved; rest days add zero sessions"
