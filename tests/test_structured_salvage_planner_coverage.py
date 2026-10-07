"""Structured conversion never costs the athlete Stage 1 strength/conditioning.

Production regression (plan f20160b1, 2026-10-06): the converter mirrored the
source's spelled-out day headers ("D-23 (Friday) — Strength") into every
``day.weekday``. The schema stores ``"Fri"``, nothing normalized it, and each
failing ``weeks.N.days.M.weekday`` path was promoted to a whole-day salvage
target. 24 of 24 converted days were deleted, including every strength and
conditioning session; the calendar spine then refilled the countdown with
empty days, and the card shipped as ``valid``.

These tests replay that shape and pin the invariant: invalid athlete-facing
metadata is repaired or cleared at the smallest node, and a containment that
would remove planner-owned S&C is refused so the existing repair / deterministic
Stage 1 fallback builds the card instead.
"""

from __future__ import annotations

import copy
from datetime import date, timedelta

import pytest

from api.services.effective_structured_plan import resolve_effective_structured_plan
from api.stage2_automation import report_structured_card_outcome
from api.structured_plan_calendar_spine import reconcile_calendar_spine
from api.structured_plan_generation import (
    _salvage_invalid_training_nodes,
    build_structured_plan_outcome,
    normalize_structured_plan_candidate,
)
from api.structured_plan_models import safe_parse_structured_plan
from fightcamp.stage2_payload import build_computed_support

FIGHT_DATE = date(2026, 11, 1)  # Sunday, as in production


def _iso(d_day: int) -> str:
    return (FIGHT_DATE - timedelta(days=d_day)).isoformat()


def _long_weekday(d_day: int) -> str:
    return (FIGHT_DATE - timedelta(days=d_day)).strftime("%A")


# (d_day, role_key, category, label, session_type, [(exercise, dose)])
_SC_ROLES = [
    (26, "alactic_support_day", "conditioning", "Alactic sharpness", "conditioning",
     [("Depth Drop (No Rebound)", "6 sets x 3 reps; rest 90 sec; RPE 7")]),
    (24, "aerobic_base_day", "conditioning", "Aerobic support", "conditioning",
     [("Jump Rope Conditioning", "15 min continuous; RPE 5")]),
    (23, "primary_strength_day", "strength", "Strength", "strength_power",
     [("Push-Up (Weighted)", "2 sets x 8 reps; rest 120 sec; RPE 6"),
      ("Cossack Squat (Dynamic)", "2 sets x 8 reps per side; rest 120 sec; RPE 6")]),
    (20, "secondary_strength_day", "strength", "Strength", "strength_power",
     [("Tire Flip", "4 sets x 3 reps; rest 90 sec; RPE 7"),
      ("Clap Push-Up", "4 sets x 3 reps; rest 90 sec; RPE 7")]),
    (16, "neural_plus_strength_day", "strength", "Strength", "strength_power",
     [("Jump Lunge (Alternating)", "3 sets x 2 reps; rest 120 sec"),
      ("Med-Ball Rotational Slam", "3 sets x 2 reps; rest 120 sec")]),
    (16, "fight_pace_repeatability_day", "conditioning", "Fight-pace conditioning", "conditioning",
     [("Double-End Bag Circuit", "5 rounds x 3 min; rest 60 sec; RPE 9")]),
]
_SC_COUNT = {"strength_power": 3, "conditioning": 3}


def _brief() -> dict:
    roles = []
    for index, (d_day, key, category, label, _stype, exercises) in enumerate(_SC_ROLES):
        roles.append(
            {
                "role_key": key,
                "category": category,
                "athlete_facing_label": label,
                "session_index": index,
                "scheduled_countdown_label": f"D-{d_day}",
                "selected_exercise_assignments": [
                    {"name": name, "prescription": dose} for name, dose in exercises
                ],
            }
        )
    return {
        "fight_date": FIGHT_DATE.isoformat(),
        "days_until_fight": 26,
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "phase": "SPP",
                    "calendar_days": [{"d_day": d} for d in range(26, -1, -1)],
                    "session_roles": roles,
                }
            ]
        },
    }


def _source_text() -> str:
    lines = ["SPP — Week 1 (D-26 to D-0) — Build repeatability and power", ""]
    for d_day, _key, _cat, label, _stype, exercises in _SC_ROLES:
        lines.append(f"D-{d_day} ({_long_weekday(d_day)}) — {label}")
        lines.append("Why: planner-owned work for this day.")
        lines.extend(f"- {name}: {dose}." for name, dose in exercises)
        lines.append("")
    return "\n".join(lines)


def _mindset() -> dict:
    return {"intent": "Stay sharp", "focus_cue": "Fast hands", "reset_cue": "Breathe"}


def _converter_card(*, weekday=_long_weekday) -> dict:
    """What the converter emitted: the sessions Stage 2 DID render, sparse days."""
    days: dict[int, dict] = {}
    for d_day, key, _cat, label, stype, exercises in _SC_ROLES:
        day = days.setdefault(
            d_day,
            {
                "date": _iso(d_day),
                "weekday": weekday(d_day),
                "day_type": "high",
                "countdown_label": f"D-{d_day}",
                "phase_label": "SPP",
                "today_card": {
                    "headline": label,
                    "readiness_status": "train_as_planned",
                    "mindset_anchor": _mindset(),
                },
                "sessions": [],
            },
        )
        day["sessions"].append(
            {
                "session_id": f"ses-{d_day}-{key}",
                "session_type": stype,
                "title": label,
                "objective": "Planner-owned work.",
                "mindset_anchor": _mindset(),
                "blocks": [
                    {
                        "block_type": "strength" if stype == "strength_power" else "conditioning",
                        "display_name": name,
                    }
                    for name, _dose in exercises
                ],
            }
        )
    return {
        "schema_version": "1.0",
        "plan_metadata": {
            "title": "Fight camp", "sport": "boxing", "plan_type": "fight_camp",
            "timezone": "Europe/London", "status": "active", "units": "metric",
        },
        "athlete_context": {"sport_profile": "boxing"},
        "event_context": {"event_type": "fight", "fight_date": FIGHT_DATE.isoformat()},
        "countdown_labels": [],
        "red_flag_rules": [],
        "plan_notes": [],
        "weeks": [
            {
                "week_index": 1,
                "phase_label": "SPP",
                "week_goal": "Repeatability",
                "start_date": _iso(26),
                "end_date": _iso(0),
                "load_focus": {
                    "volume": "moderate", "intensity": "high",
                    "specificity": "high", "fatigue_target": "moderate",
                },
                "progression": {"week_type": "build", "planned_change_from_previous": "Build."},
                "days": [days[d] for d in sorted(days, reverse=True)],
            }
        ],
        "daily_check_ins": [],
        "nutrition": {"summary": "Fuel around sessions.", "daily_focus": "Carbs around training."},
        "progression_notes": "",
        "raw_markdown_fallback": "",
    }


def _sessions_by_dday(plan: dict) -> dict[int, list[dict]]:
    found: dict[int, list[dict]] = {}
    for week in plan.get("weeks") or []:
        for day in week.get("days") or []:
            label = str(day.get("countdown_label") or "")
            if label.startswith("D-"):
                found.setdefault(int(label[2:]), []).extend(day.get("sessions") or [])
    return found


def _sc_counts(plan: dict) -> dict[str, int]:
    counts = {"strength_power": 0, "conditioning": 0}
    for sessions in _sessions_by_dday(plan).values():
        for session in sessions:
            if session.get("session_type") in counts:
                counts[session["session_type"]] += 1
    return counts


def _outcome(card: dict, **kwargs):
    return build_structured_plan_outcome(
        card, raw_markdown=_source_text(), planning_brief=_brief(), **kwargs
    )


# --- production replay ------------------------------------------------------


def test_production_replay_spelled_out_weekdays_keep_every_planner_sc_session():
    outcome = _outcome(_converter_card())

    assert outcome.status == "valid", outcome.errors
    assert not [w for w in outcome.warnings if w.startswith("schema_salvage")]
    assert _sc_counts(outcome.structured_plan) == _SC_COUNT
    days = _sessions_by_dday(outcome.structured_plan)
    for d_day in (23, 20, 16):
        assert any(s["session_type"] == "strength_power" for s in days[d_day]), d_day
    weekdays = {
        day["countdown_label"]: day["weekday"]
        for week in outcome.structured_plan["weeks"]
        for day in week["days"]
    }
    assert weekdays["D-23"] == "Fri"
    assert weekdays["D-20"] == "Mon"


def test_production_replay_survives_the_final_calendar_spine_pass():
    # stage2_automation re-runs the spine on the outcome before persistence.
    outcome = _outcome(_converter_card())
    rebuilt = reconcile_calendar_spine(outcome.structured_plan, _brief())

    assert safe_parse_structured_plan(rebuilt).ok
    days = _sessions_by_dday(rebuilt)
    assert set(days) == set(range(26, -1, -1))  # continuous countdown kept
    for d_day, _key, _cat, _label, stype, _ex in _SC_ROLES:
        assert any(s["session_type"] == stype for s in days[d_day]), d_day
    assert _sc_counts(rebuilt) == _SC_COUNT


# --- smallest-node repair ---------------------------------------------------


def test_strength_day_with_one_invalid_metadata_field_keeps_its_strength_session():
    card = _converter_card(weekday=lambda d: "Fri" if d == 23 else _long_weekday(d)[:3])
    d23 = card["weeks"][0]["days"][2]
    assert d23["countdown_label"] == "D-23"
    # The plan-level nutrition warning is an object; mirrored onto the day card
    # it is invalid there, but it is presentation copy, not training.
    d23["today_card"]["weight_cut_warning"] = {
        "risk_level": "none",
        "display_text": "Low-level cut noted. Protect recovery and fuelling.",
    }

    outcome = _outcome(card)

    assert outcome.status == "valid", outcome.errors
    day = next(
        d for w in outcome.structured_plan["weeks"] for d in w["days"]
        if d["countdown_label"] == "D-23"
    )
    assert [s["session_type"] for s in day["sessions"]] == ["strength_power"]
    assert day["today_card"]["weight_cut_warning"] == (
        "Low-level cut noted. Protect recovery and fuelling."
    )


def test_conditioning_day_with_one_invalid_metadata_field_keeps_its_session():
    card = _converter_card(weekday=lambda d: _long_weekday(d)[:3])
    d24 = card["weeks"][0]["days"][1]
    assert d24["countdown_label"] == "D-24"
    d24["priority_microdose"] = "Reactive Start Burst"  # not the schema's object

    outcome = _outcome(card)

    assert outcome.status == "valid", outcome.errors
    sessions = _sessions_by_dday(outcome.structured_plan)[24]
    assert [s["session_type"] for s in sessions] == ["conditioning"]


def test_unnormalized_optional_day_field_is_cleared_not_the_day():
    """Defence in depth: salvage itself clears optional day metadata."""
    card = _converter_card(weekday=lambda d: _long_weekday(d)[:3])
    error = "weeks.0.days.2.weekday: Input should be 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat' or 'Sun'"
    card["weeks"][0]["days"][2]["weekday"] = "Friyay"

    salvaged, warnings, refusals = _salvage_invalid_training_nodes(
        card, [error], raw_markdown=_source_text(), planning_brief=_brief()
    )

    assert refusals == []
    day = salvaged["weeks"][0]["days"][2]
    assert day["weekday"] is None
    assert len(day["sessions"]) == 1
    assert warnings == [f"schema_salvage: cleared invalid day field 'weekday' on 'D-23' ({error})"]


# --- Stage 1 authority when containment would lose S&C ----------------------


def _corrupt_strength_session(card: dict) -> dict:
    card["weeks"][0]["days"][2]["sessions"][0]["completion"] = "not an object"
    return card


def test_salvage_refuses_to_drop_a_planner_owned_strength_session():
    outcome = _outcome(_corrupt_strength_session(_converter_card()))

    assert outcome.status == "invalid_fallback_used"
    assert outcome.structured_plan is None
    refusal = next(e for e in outcome.errors if e.startswith("schema_salvage_refused:"))
    assert "'D-23'" in refusal and "sessions.0.completion" in refusal


def test_refused_salvage_falls_back_to_stage1_coverage_at_read_time():
    outcome = _outcome(_corrupt_strength_session(_converter_card()))
    assert outcome.structured_plan is None

    card = resolve_effective_structured_plan(
        {"id": "plan-1", "structured_plan": None, "planning_brief": _brief()},
        raw_markdown=_source_text(),
    )

    assert card is not None
    days = _sessions_by_dday(card)
    for d_day, key, _cat, _label, stype, exercises in _SC_ROLES:
        session = next(s for s in days[d_day] if key in str(s.get("session_id")))
        assert session["session_type"] == stype
        assert [b["display_name"] for b in session["blocks"]] == [n for n, _ in exercises]


def test_salvage_refuses_a_whole_day_removal_that_would_lose_conditioning():
    card = _converter_card(weekday=lambda d: _long_weekday(d)[:3])
    error = "weeks.0.days.1.today_card.mindset_anchor: Field required"

    salvaged, warnings, refusals = _salvage_invalid_training_nodes(
        card, [error], raw_markdown=_source_text(), planning_brief=_brief()
    )

    assert salvaged is card and warnings == []
    assert refusals and "'D-24'" in refusals[0] and "mindset_anchor" in refusals[0]


def test_unbacked_model_session_is_still_removed():
    card = _converter_card(weekday=lambda d: _long_weekday(d)[:3])
    invented = copy.deepcopy(card["weeks"][0]["days"][0]["sessions"][0])
    invented.update(
        session_id="bonus", session_type="mixed", title="Bonus Finisher",
        completion="not an object",
    )
    card["weeks"][0]["days"][0]["sessions"].append(invented)  # D-26

    outcome = _outcome(card)

    assert outcome.status == "valid", outcome.errors
    titles = [s["title"] for s in _sessions_by_dday(outcome.structured_plan)[26]]
    assert "Bonus Finisher" not in titles
    assert _sc_counts(outcome.structured_plan) == _SC_COUNT
    assert any(
        w.startswith("schema_salvage: omitted invalid session 'Bonus Finisher' (")
        for w in outcome.warnings
    )


def test_normalized_day_copy_is_still_safety_audited():
    support = build_computed_support(
        flags={"weight": 70, "mental_block": ["confidence"], "weight_cut_risk": True,
               "weight_cut_pct": 7.0, "fatigue": "high"},
        phases=["GPP", "SPP", "TAPER"],
    )
    gated = support["nutrition"]["by_phase"]["TAPER"]["coach_gated"]["acute_cut_protocol"]
    card = _converter_card()
    card["weeks"][0]["days"][2]["today_card"]["weight_cut_warning"] = {
        "display_text": f"Pre-fight buffer: {gated['bicarbonate_g_per_kg']}"
    }

    outcome = _outcome(card, computed_support=support)

    assert outcome.status == "blocked_by_safety_audit"
    assert outcome.structured_plan is None


# --- observability ----------------------------------------------------------


def test_schema_salvage_is_reported_as_a_salvaged_card(monkeypatch):
    card = _converter_card(weekday=lambda d: _long_weekday(d)[:3])
    card["weeks"][0]["days"][0]["sessions"].append(
        {
            "session_id": "bonus", "session_type": "mixed", "title": "Bonus Finisher",
            "objective": "x", "mindset_anchor": _mindset(), "completion": "bad",
        }
    )
    outcome = _outcome(card)
    assert outcome.status == "valid"

    assert report_structured_card_outcome(outcome, source="test") == "salvaged"


@pytest.mark.parametrize("weekday", ["Friday", "friday", "FRI", "Fri.", ""])
def test_weekday_spellings_normalize(weekday):
    from api.structured_plan_generation import _normalize_day

    expected = None if not weekday else "Fri"
    assert _normalize_day({"weekday": weekday})["weekday"] == expected


# --- end-to-end coverage invariant (repair / first pass) --------------------


def _short_weekday(d_day: int) -> str:
    return _long_weekday(d_day)[:3]


def _without_d23_strength(card: dict) -> dict:
    card = copy.deepcopy(card)
    card["weeks"][0]["days"] = [
        day for day in card["weeks"][0]["days"] if day["countdown_label"] != "D-23"
    ]
    return card


def test_repair_that_deletes_planner_strength_cannot_ship():
    # 1. planner owns D-23 Strength; 2. the converter's session is schema-invalid.
    broken = _corrupt_strength_session(_converter_card())
    # 3. salvage correctly refuses to delete it.
    _, _, refusals = _salvage_invalid_training_nodes(
        copy.deepcopy(broken), ["weeks.0.days.2.sessions.0.completion: bad"],
        raw_markdown=_source_text(), planning_brief=_brief(),
    )
    assert refusals
    # 4. the repair model "fixes" the card by deleting D-23 Strength.
    repaired = _without_d23_strength(_converter_card(weekday=_short_weekday))
    # Schema-valid once the pipeline's own normalization runs on it.
    assert safe_parse_structured_plan(normalize_structured_plan_candidate(repaired)).ok

    outcome = _outcome(broken, repair_fn=lambda _data, _errors: copy.deepcopy(repaired))

    # 5. the repaired card must not become athlete-visible.
    assert outcome.status != "repair_attempted_valid"
    assert outcome.status == "invalid_fallback_used"
    assert outcome.structured_plan is None
    assert any(
        e.startswith("planner_coverage: D-23 'primary_strength_day' (strength_power)")
        for e in outcome.errors
    ), outcome.errors


def test_repair_that_keeps_planner_strength_still_ships():
    broken = _corrupt_strength_session(_converter_card())
    fixed = _converter_card(weekday=_short_weekday)

    outcome = _outcome(broken, repair_fn=lambda _data, _errors: copy.deepcopy(fixed))

    assert outcome.status == "repair_attempted_valid", outcome.errors
    assert _sc_counts(outcome.structured_plan) == _SC_COUNT


def test_first_pass_card_that_silently_omits_planner_strength_is_rejected():
    outcome = _outcome(_without_d23_strength(_converter_card()))

    assert outcome.status == "invalid_fallback_used"
    assert outcome.structured_plan is None
    assert any("D-23 'primary_strength_day'" in e for e in outcome.errors)


def test_retitled_planner_session_still_counts_as_represented():
    card = _converter_card()
    card["weeks"][0]["days"][2]["sessions"][0]["title"] = "Lower-body power"

    outcome = _outcome(card)

    assert outcome.status == "valid", outcome.errors


def test_role_the_source_never_rendered_is_not_a_conversion_loss():
    # Stage 2 underfill (the text omits a scheduled role) is a separate issue:
    # the converter cannot be blamed for content it was never given.
    brief = _brief()
    brief["weekly_role_map"]["weeks"][0]["session_roles"].append(
        {
            "role_key": "strength_touch_day",
            "category": "strength",
            "athlete_facing_label": "Strength touch",
            "scheduled_countdown_label": "D-13",
            "selected_exercise_assignments": [{"name": "Explosive Straight Burst"}],
        }
    )

    outcome = build_structured_plan_outcome(
        _converter_card(), raw_markdown=_source_text(), planning_brief=brief
    )

    assert outcome.status == "valid", outcome.errors


# --- coverage is exercise-level, not session-shaped -------------------------
#
# Production (plans 6c418f41, d12963b2, 1e80d605): every card after the check
# went live fell back, though the converter had kept the work. It folded D-16's
# fight-pace conditioning into the "Strength" session, and typed/titled single-
# exercise primers after their exercise, so no session LOOKED like the role.


def _day(card: dict, d_day: int) -> dict:
    return next(
        day for week in card["weeks"] for day in week["days"]
        if day["countdown_label"] == f"D-{d_day}"
    )


def test_two_roles_folded_into_one_session_are_both_represented():
    card = _converter_card(weekday=_short_weekday)
    d16 = _day(card, 16)
    strength, conditioning = d16["sessions"]
    strength["blocks"] += conditioning["blocks"]
    d16["sessions"] = [strength]

    outcome = _outcome(card)

    assert outcome.status == "valid", outcome.errors


def test_primer_titled_and_typed_after_its_exercise_is_represented():
    card = _converter_card(weekday=_short_weekday)
    session = _day(card, 26)["sessions"][0]
    session.update(session_type="skill", title="Depth Drop (No Rebound)")

    outcome = _outcome(card)

    assert outcome.status == "valid", outcome.errors


def test_role_whose_exercises_left_the_day_is_still_a_loss():
    # The session survives in name only: its exercises moved off D-23.
    card = _converter_card(weekday=_short_weekday)
    session = _day(card, 23)["sessions"][0]
    session.update(session_id="ses-mobility", session_type="skill", title="Mobility")
    session["blocks"] = [{"block_type": "mobility_activation", "display_name": "Hip circles"}]

    outcome = _outcome(card)

    assert outcome.status == "invalid_fallback_used"
    assert any("D-23 'primary_strength_day'" in e for e in outcome.errors)
