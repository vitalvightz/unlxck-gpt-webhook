"""Regression tests: fillers may only land on declared training-availability days.

An athlete who declares Monday–Friday must never receive a filler (Fight Tactical
Watch, Tactical Cue Card, visualization/mindset, mobility/recovery, conditioning,
or any other gap-fill/support insert) on Saturday or Sunday, in either the
normal-camp engine (:func:`apply_camp_week_fillers`) or the late-fight engine
(:func:`apply_gap_fill_inserts`). The calendar spine can list weekdays the athlete
never trains; declared training availability is the authority.
"""

from __future__ import annotations

from fightcamp.camp_week_fillers import apply_camp_week_fillers
from fightcamp.gap_fill_inserts import apply_gap_fill_inserts

WEEK_ORDER = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
WEEKDAYS = {"monday", "tuesday", "wednesday", "thursday", "friday"}
WEEKEND = {"saturday", "sunday"}


def _athlete(**overrides):
    athlete = {
        "sport": "boxing",
        "days_until_fight": 28,
        "plan_creation_weekday": "monday",
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        "hard_sparring_days": [],
        "fatigue": "low",
        "fatigue_level": "low",
        "readiness_flags": [],
        "weight_cut_risk": False,
        "weight_cut_pct": 0.0,
        "weaknesses": [],
        "key_goals": [],
        "injuries": [],
        "parsed_injuries": [],
        "guided_injury": None,
        "injury_restrictions": [],
    }
    athlete.update(overrides)
    return athlete


# ── Normal-camp helpers ──────────────────────────────────────────────────────


def _full_spine(d_monday: int):
    """Full seven-day calendar spine (weekends included), Monday counts down first."""
    return [
        {"weekday": day, "d_day": d_monday - index}
        for index, day in enumerate(WEEK_ORDER)
    ]


def _loaded_week(phase: str, d_monday: int, *, training_days=None):
    """A week whose every declared weekday already carries two sessions.

    No day is free and none is a single-session shareable day, so the mandatory
    Tactical Watch can only be placed by sharing one of the loaded declared days.
    """
    roles = []
    for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"):
        roles.append(
            {"role_key": "primary_strength_day", "category": "strength", "scheduled_day_hint": day}
        )
        roles.append(
            {"role_key": "hard_sparring_day", "category": "sparring", "scheduled_day_hint": day}
        )
    return {
        "phase": phase,
        "session_roles": roles,
        "calendar_days": _full_spine(d_monday),
        "intentionally_unused_days": [],
        "declared_training_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        if training_days is None
        else training_days,
    }


def _free_week(phase: str, d_monday: int):
    """A week with free declared weekdays available for adaptive fillers.

    Mirrors the PR #2221 cap fixture (one Monday session, Wednesday/Friday unused)
    but ships a full seven-day spine so weekend calendar days are present too.
    """
    return {
        "phase": phase,
        "session_roles": [
            {"role_key": "primary_strength_day", "category": "strength", "scheduled_day_hint": "Monday"}
        ],
        "calendar_days": _full_spine(d_monday),
        "intentionally_unused_days": [
            {"day": "Wednesday", "role": "recovery_only_day"},
            {"day": "Friday", "role": "off_day"},
        ],
        "declared_training_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    }


def _camp_fillers(week):
    return [
        role
        for role in week["session_roles"]
        if isinstance(role, dict)
        and (role.get("camp_week_filler") or role.get("category") == "support_insert")
    ]


def _watches(roles):
    return [r for r in roles if r.get("role_key") == "tactical_watch"]


def _day_of(role) -> str:
    return str(role.get("scheduled_day_hint") or role.get("real_weekday") or "").strip().lower()


# ── Late-fight helpers ───────────────────────────────────────────────────────


def _session(offset: int, role_key: str = "strength_touch_day") -> dict:
    return {
        "session_index": 1,
        "category": "strength",
        "role_key": role_key,
        "countdown_offset": offset,
        "countdown_label": f"D-{offset}",
        "scheduled_countdown_label": f"D-{offset}",
    }


def _late_fight_fillers(sequence):
    """Every gap-fill insert (base strength touch days are the only non-inserts)."""
    return [r for r in sequence if str(r.get("role_key") or "") != "strength_touch_day"]


# ── 1. Mon–Fri availability → no filler on Sat/Sun ───────────────────────────


def test_normal_camp_filler_never_lands_on_unavailable_day():
    week = _loaded_week("SPP", 28)
    apply_camp_week_fillers({"weeks": [week]}, _athlete())

    fillers = _camp_fillers(week)
    assert fillers, "expected at least the mandatory Tactical Watch to be placed"
    for role in fillers:
        assert _day_of(role) in WEEKDAYS
        assert _day_of(role) not in WEEKEND


def test_normal_camp_would_reach_weekend_without_declared_availability():
    """Guards that the scenario genuinely exposes weekend calendar days.

    Without declared availability the least-loaded fallback picks an empty weekend
    day, so the availability gate above is load-bearing, not incidental.
    """
    week = _loaded_week("SPP", 28, training_days=[])
    apply_camp_week_fillers({"weeks": [week]}, _athlete(training_days=[]))
    assert any(_day_of(role) in WEEKEND for role in _watches(week["session_roles"]))


def test_late_fight_filler_never_lands_on_unavailable_day():
    sequence = apply_gap_fill_inserts(
        [_session(21), _session(14), _session(7)],
        _athlete(days_until_fight=21),
    )
    fillers = _late_fight_fillers(sequence)
    assert fillers, "expected gap-fill inserts to be produced"
    for role in fillers:
        assert _day_of(role) in WEEKDAYS
        assert _day_of(role) not in WEEKEND


# ── 2. Mandatory Tactical Watch: once per segment, only on an available day ───


def test_late_fight_mandatory_watch_once_per_segment_on_available_day():
    sequence = apply_gap_fill_inserts(
        [_session(21), _session(14), _session(7)],
        _athlete(days_until_fight=21),
    )
    watches = [r for r in _watches(sequence) if r.get("mandatory_tactical_watch")]
    # one per seven-day segment (0, 1, 2), exactly as PR #2221 requires
    assert {w["tactical_watch_segment"] for w in watches} == {0, 1, 2}
    for watch in watches:
        assert watch["countdown_offset"] > 0
        assert _day_of(watch) in WEEKDAYS


def test_normal_camp_mandatory_watch_once_per_phase_on_available_day():
    role_map = {"weeks": [_loaded_week("GPP", 42), _loaded_week("SPP", 28), _loaded_week("TAPER", 7)]}
    apply_camp_week_fillers(role_map, _athlete(days_until_fight=42))
    for week in role_map["weeks"]:
        watches = _watches(week["session_roles"])
        assert len(watches) == 1
        assert watches[0]["mandatory_tactical_watch"] is True
        assert _day_of(watches[0]) in WEEKDAYS


# ── 3. All available days full → share an available day, never an unavailable one


def test_watch_shares_available_day_when_no_free_declared_day_exists():
    week = _loaded_week("SPP", 28)
    pre_counts: dict[str, int] = {}
    for role in week["session_roles"]:
        pre_counts[_day_of(role)] = pre_counts.get(_day_of(role), 0) + 1

    apply_camp_week_fillers({"weeks": [week]}, _athlete())

    watch = _watches(week["session_roles"])[0]
    day = _day_of(watch)
    # shared onto a declared day that already carried sessions — not a weekend
    assert day in WEEKDAYS
    assert pre_counts.get(day, 0) >= 1


# ── 4. PR #2221 filler caps and watch requirements remain unchanged ──────────


def test_pr2221_caps_and_watch_requirements_unchanged_with_weekend_calendar():
    role_map = {"weeks": [_free_week("GPP", 42), _free_week("SPP", 28), _free_week("TAPER", 7)]}
    apply_camp_week_fillers(role_map, _athlete(days_until_fight=42))

    support_counts = []
    for week in role_map["weeks"]:
        watches = _watches(week["session_roles"])
        assert len(watches) == 1
        assert watches[0]["weekly_requirement"] == "fight_tactical_watch"
        assert watches[0]["governance"]["authority"] == "gap_fill_support_insert"
        # every support insert still respects declared availability
        assert all(_day_of(role) in WEEKDAYS for role in _camp_fillers(week))
        support_counts.append(len(_camp_fillers(week)))

    # GPP cap 1, SPP cap 2, TAPER cap 1 — identical to PR #2221
    assert support_counts == [1, 2, 1]


# ── 5. Non-fight (non-watch) fillers also cannot use unavailable days ─────────


def test_non_watch_fillers_cannot_use_unavailable_days():
    sequence = apply_gap_fill_inserts(
        [_session(21), _session(14), _session(7)],
        _athlete(days_until_fight=21),
    )
    non_watch = [
        role
        for role in _late_fight_fillers(sequence)
        if str(role.get("role_key") or "") != "tactical_watch"
    ]
    for role in non_watch:
        assert _day_of(role) in WEEKDAYS
        assert _day_of(role) not in WEEKEND


def test_non_watch_fillers_would_reach_weekend_without_declared_availability():
    """Confirms the same sequence otherwise places non-watch fillers on weekends."""
    sequence = apply_gap_fill_inserts(
        [_session(21), _session(14), _session(7)],
        _athlete(days_until_fight=21, training_days=[]),
    )
    non_watch = [
        role
        for role in _late_fight_fillers(sequence)
        if str(role.get("role_key") or "") != "tactical_watch"
    ]
    assert any(_day_of(role) in WEEKEND for role in non_watch)
