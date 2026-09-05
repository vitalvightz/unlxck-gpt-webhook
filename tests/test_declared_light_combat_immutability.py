"""Declared light combat is a coach-owned, immutable, but S&C-compatible day.

Declared light-combat / technical days (``support_work_days``) are mandatory,
coach-owned calendar context on that exact weekday. They are *S&C-compatible, not
day-exclusive*:

    declared light combat
        -> coach-owned role that can never disappear, be replaced, or move
        -> planner considers any app-owned S&C for the same day
        -> combat_load_policy decides:
             LEGAL (low-load / true-microdose)  -> STACK on the light day
             ILLEGAL (meaningful S&C / 2nd contact) -> the S&C yields (dropped)
        -> light combat always remains

That invariant must hold in BOTH planners — normal camp (D-14+) and the D-13
inward countdown spine — through the one shared ``declared_combat_ownership``
helper, and it must never expand the athlete's planned weekly training exposure:
a legal same-day S&C stacks on the light day rather than taking a fresh day.

Regression: the normal ``D>13`` planner used to carry ``support_work_days`` into
the weekly map only as ``declared_support_work_days`` metadata and never created
the mandatory ``light_combat_day`` spine, so an app-owned aerobic support session
could take the declared Wednesday and the light-combat session simply vanished.
"""

from copy import deepcopy

from fightcamp.calendar_integrity import apply_final_calendar_integrity
from fightcamp.combat_load_policy import LoadClass, role_load_class
from fightcamp.declared_combat_ownership import (
    LIGHT_COMBAT_ROLE_KEY,
    build_declared_light_combat_role,
    declared_light_combat_weekdays,
)
from fightcamp.stage2_payload_late_fight import (
    _countdown_weekday_map,
    _visible_calendar_session_sequence,
    ensure_declared_coach_combat_spine,
)
from fightcamp.stage2_role_map import (
    _build_weekly_role_map,
    _lock_declared_light_combat_roles,
)


TRAINING_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]


def _athlete(**overrides):
    athlete = {
        "sport_style": "boxing",
        "sport": "boxing",
        "training_days": list(TRAINING_DAYS),
        "hard_sparring_days": ["monday", "friday"],
        "support_work_days": ["wednesday"],
        "key_goals": ["conditioning"],
        "weaknesses": ["gas_tank"],
        # A Wednesday fight so declared Wednesday sessions land on exact multiples
        # of seven (D-21, D-14, D-7) in the countdown.
        "fight_date": "2027-07-21",
        "days_until_fight": 28,
    }
    athlete.update(overrides)
    return athlete


def _gpp_progression(weeks: int, session_counts=None):
    counts = session_counts or {"strength": 1, "conditioning": 2, "recovery": 1}
    return {
        "weeks": [
            {
                "week_index": i + 1,
                "phase": "GPP",
                "stage_key": "general_capacity",
                "span_days": 7,
                "session_counts": dict(counts),
                "conditioning_sequence": ["aerobic", "aerobic"],
            }
            for i in range(weeks)
        ]
    }


def _wednesday_roles(week: dict) -> list[dict]:
    return [
        role
        for role in week.get("session_roles", [])
        if str(role.get("scheduled_day_hint") or "").strip().lower() == "wednesday"
    ]


def _light_combat_on(week: dict, weekday: str) -> dict | None:
    return next(
        (
            role
            for role in week.get("session_roles", [])
            if role.get("role_key") == LIGHT_COMBAT_ROLE_KEY
            and str(role.get("scheduled_day_hint") or "").strip().lower() == weekday
        ),
        None,
    )


def _distinct_training_days(week: dict) -> set[str]:
    return {
        day
        for role in week.get("session_roles", [])
        if role.get("role_key") != "fight_day_protocol"
        and (day := str(role.get("scheduled_day_hint") or "").strip().lower())
    }


# ---------------------------------------------------------------------------
# The reported regression: D-21 / D-14 normal-camp Wednesdays must survive.
# ---------------------------------------------------------------------------
def test_declared_light_combat_survives_every_normal_camp_wednesday():
    # A 4-week camp anchored on a Wednesday fight puts declared Wednesdays on
    # D-21, D-14, D-7, and D-0 (the fight itself). D-21 and D-14 are exactly the
    # normal-camp days that used to lose their light-combat session.
    role_map = _build_weekly_role_map(
        _athlete(), _gpp_progression(4), {"key": "conditioning_endurance"}
    )
    by_label = {}
    for week in role_map["weeks"]:
        light = _light_combat_on(week, "wednesday")
        if light is not None:
            by_label[light.get("scheduled_countdown_label")] = light

    for label in ("D-21", "D-14", "D-7"):
        role = by_label.get(label)
        assert role is not None, f"expected a coach-owned light-combat Wednesday at {label}"
        assert role["role_key"] == LIGHT_COMBAT_ROLE_KEY
        assert role["coach_owned"] is True
        assert role["declared_day_locked"] is True


def test_light_combat_is_never_replaced_on_its_declared_wednesday():
    role_map = _build_weekly_role_map(
        _athlete(), _gpp_progression(4), {"key": "conditioning_endurance"}
    )
    for week in role_map["weeks"]:
        wednesday = _wednesday_roles(week)
        role_keys = {role["role_key"] for role in wednesday}
        # The D-0 fight week is owned by the fight-day protocol, not a session.
        if role_keys == {"fight_day_protocol"}:
            continue
        # Never: the Wednesday exists but the light-combat slot was replaced by an
        # app role. The coach-owned lock is always present on the declared day.
        assert LIGHT_COMBAT_ROLE_KEY in role_keys
        assert _light_combat_on(week, "wednesday")["coach_owned"] is True


def test_declared_light_combat_multi_week_plan_passes_final_governor():
    role_map = _build_weekly_role_map(
        _athlete(), _gpp_progression(4), {"key": "conditioning_endurance"}
    )
    # A real (technical-contact) light_combat_day role, possibly stacked with a
    # legal low-load session, must leave the deterministic calendar legal.
    apply_final_calendar_integrity(deepcopy(role_map))


# ---------------------------------------------------------------------------
# S&C-compatible, not day-exclusive: legality is the shared policy's call.
# ---------------------------------------------------------------------------
def _lock_week():
    week_entry = {"week_index": 1, "declared_hard_sparring_days": []}
    athlete = {
        "training_days": list(TRAINING_DAYS),
        "support_work_days": ["wednesday"],
        "hard_sparring_days": [],
    }
    return week_entry, athlete


def test_legal_low_load_sc_stacks_on_light_combat_day():
    week_entry, athlete = _lock_week()
    session_roles = [
        {
            "session_index": 1,
            "category": "conditioning",
            "role_key": "aerobic_support_day",
            "preferred_system": "aerobic",
            "scheduled_day_hint": "wednesday",
            "allowed_on_recovery_day": True,
        }
    ]
    roles, suppressed = _lock_declared_light_combat_roles(
        week_entry, session_roles, [], athlete
    )

    wednesday = {r["role_key"] for r in roles if r.get("scheduled_day_hint") == "wednesday"}
    # A low-load aerobic session is S&C-compatible with light combat, so it stacks
    # on the same day — the light-combat lock is added alongside it, not instead.
    assert wednesday == {LIGHT_COMBAT_ROLE_KEY, "aerobic_support_day"}
    assert not any(s.get("replacement_role_key") == LIGHT_COMBAT_ROLE_KEY for s in suppressed)


def test_zero_load_support_stacks_on_light_combat_day():
    week_entry, athlete = _lock_week()
    session_roles = [
        {
            "session_index": 1,
            "category": "support_insert",
            "role_key": "tactical_cue_card",
            "scheduled_day_hint": "wednesday",
            "stress_class": "support",
            "cost_class": "low",
            "governance": {"meaningful_stress": False},
        }
    ]
    roles, _ = _lock_declared_light_combat_roles(week_entry, session_roles, [], athlete)
    wednesday = {r["role_key"] for r in roles if r.get("scheduled_day_hint") == "wednesday"}
    assert wednesday == {LIGHT_COMBAT_ROLE_KEY, "tactical_cue_card"}


def test_illegal_meaningful_sc_yields_and_light_combat_remains():
    week_entry, athlete = _lock_week()
    session_roles = [
        {
            "session_index": 1,
            "category": "strength",
            "role_key": "strength_touch_day",
            "scheduled_day_hint": "wednesday",
        }
    ]
    roles, suppressed = _lock_declared_light_combat_roles(
        week_entry, session_roles, [], athlete
    )

    wednesday = {r["role_key"] for r in roles if r.get("scheduled_day_hint") == "wednesday"}
    # Meaningful strength cannot share a light-combat day; it yields, the light
    # slot remains, and nothing is relocated to a fresh training day.
    assert wednesday == {LIGHT_COMBAT_ROLE_KEY}
    assert any(
        s.get("replacement_role_key") == LIGHT_COMBAT_ROLE_KEY
        and s.get("role_key") == "strength_touch_day"
        for s in suppressed
    )


# ---------------------------------------------------------------------------
# Frequency preserved: adding light combat must not create an extra training day.
# ---------------------------------------------------------------------------
def test_light_combat_does_not_expand_weekly_training_exposure():
    # Four available training days, one declared as light combat. The mandatory
    # light-combat lock must not push the week onto a fifth physical training day:
    # a displaced legal S&C stacks on the light day instead of taking a new one.
    athlete = _athlete(
        training_days=["monday", "tuesday", "wednesday", "thursday"],
        hard_sparring_days=["monday"],
        support_work_days=["wednesday"],
    )
    role_map = _build_weekly_role_map(
        athlete,
        _gpp_progression(3, {"strength": 1, "conditioning": 2, "recovery": 1}),
        {"key": "conditioning_endurance"},
    )
    # No week may exceed the four declared training days: the mandatory light-combat
    # lock stacks a displaced legal S&C rather than opening a fifth training day.
    for week in role_map["weeks"]:
        used = _distinct_training_days(week)
        assert used <= set(athlete["training_days"]), used
        assert len(used) <= len(athlete["training_days"])
    # The earliest (normal-camp) week still carries the coach-owned light-combat lock.
    assert _light_combat_on(role_map["weeks"][0], "wednesday") is not None
    apply_final_calendar_integrity(deepcopy(role_map))


# ---------------------------------------------------------------------------
# One shared ownership definition, consumed by both planners.
# ---------------------------------------------------------------------------
def test_normal_camp_and_late_fight_agree_on_coach_owned_light_combat():
    athlete = _athlete()

    role_map = _build_weekly_role_map(
        athlete, _gpp_progression(4), {"key": "conditioning_endurance"}
    )
    normal_wednesday = _light_combat_on(role_map["weeks"][0], "wednesday")  # D-21

    spine = ensure_declared_coach_combat_spine(
        [], athlete, _countdown_weekday_map("wednesday", 28)
    )
    late_wednesday = next(
        role
        for role in _visible_calendar_session_sequence(spine)
        if role.get("role_key") == LIGHT_COMBAT_ROLE_KEY
    )

    for role in (normal_wednesday, late_wednesday):
        assert role is not None
        assert role["role_key"] == LIGHT_COMBAT_ROLE_KEY
        assert role["coach_owned"] is True
        assert str(role["scheduled_day_hint"]).lower() == "wednesday"
        assert role_load_class(role) is LoadClass.TECHNICAL_CONTACT
        # Governance is merged onto the shared base, not replaced.
        assert role["governance"]["authority"] == "declared_schedule_lock"
        assert role["governance"]["coach_owned"] is True

    # The late-fight variant keeps its own payload marker on top of the shared base.
    assert late_wednesday["governance"].get("late_fight_payload") is True


# ---------------------------------------------------------------------------
# Shared helper unit contract.
# ---------------------------------------------------------------------------
def test_declared_light_combat_weekdays_excludes_hard_days_and_respects_training():
    athlete = {
        "training_days": ["monday", "tuesday", "wednesday"],
        "support_work_days": ["Wednesday", "Friday", "Monday"],
        "hard_sparring_days": ["monday"],
    }
    # Friday is dropped (not a training day); Monday is dropped (declared hard
    # sparring already owns it); Wednesday remains.
    assert declared_light_combat_weekdays(
        athlete, training_days=athlete["training_days"]
    ) == ["wednesday"]


def test_declared_light_combat_weekdays_falls_back_to_technical_skill_days():
    athlete = {"technical_skill_days": ["Tuesday", "Thursday"]}
    assert declared_light_combat_weekdays(athlete) == ["tuesday", "thursday"]


def test_build_declared_light_combat_role_is_coach_owned_locked():
    role = build_declared_light_combat_role("Wednesday")
    assert role["role_key"] == LIGHT_COMBAT_ROLE_KEY
    assert role["scheduled_day_hint"] == "wednesday"
    assert role["coach_owned"] is True
    assert role["declared_day_locked"] is True
    assert role["placement_basis"] == "locked"
    assert role["governance"]["authority"] == "declared_schedule_lock"
    assert role_load_class(role) is LoadClass.TECHNICAL_CONTACT


def test_build_declared_light_combat_role_merges_governance_override():
    role = build_declared_light_combat_role(
        "wednesday", governance={"late_fight_payload": True}
    )
    # Override is merged onto the canonical base, not replacing it.
    assert role["governance"]["late_fight_payload"] is True
    assert role["governance"]["authority"] == "declared_schedule_lock"
    assert role["governance"]["coach_owned"] is True