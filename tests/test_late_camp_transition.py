"""Tests for the normal-camp late-transition (taper morph) overlay."""

from fightcamp.late_camp_transition import apply_late_camp_transition


def _week(session_roles, *, calendar_days=None, intentionally_unused_days=None, **extra):
    week = {
        "session_roles": session_roles,
        "calendar_days": calendar_days or [],
        "intentionally_unused_days": intentionally_unused_days or [],
    }
    week.update(extra)
    return week


def _calendar(day_to_d):
    return [{"weekday": weekday, "d_day": d_day} for weekday, d_day in day_to_d.items()]


def _map(week):
    return {"weeks": [week]}


def _role(role_key, weekday, **extra):
    role = {
        "role_key": role_key,
        "category": "conditioning",
        "scheduled_day_hint": weekday,
    }
    role.update(extra)
    return role


def _find(week, role_key):
    return [r for r in week["session_roles"] if r.get("role_key") == role_key]


# --- Combat-pressure floor ---------------------------------------------------
def test_combat_pressure_floor_d21_to_d18_is_preserved():
    week = _week(
        [
            _role("fight_pace_repeatability_day", "monday", meaningful_stress=True),
            _role("hard_sparring_day", "tuesday", category="sparring", meaningful_stress=True),
        ],
        calendar_days=_calendar({"monday": 21, "tuesday": 18}),
    )
    apply_late_camp_transition(_map(week), {})

    # Both stay exactly as they were — nothing softened inside the floor.
    assert _find(week, "fight_pace_repeatability_day")
    assert _find(week, "hard_sparring_day")
    assert not _find(week, "light_fight_pace_touch_day")
    assert not _find(week, "light_combat_day")


# --- Fight-pace morph --------------------------------------------------------
def test_fight_pace_at_d13_and_closer_morphs_to_rhythm_touch():
    week = _week(
        [
            _role("fight_pace_repeatability_day", "monday", meaningful_stress=True),
            _role("main_fight_pace_day", "wednesday", meaningful_stress=True),
        ],
        calendar_days=_calendar({"monday": 13, "wednesday": 11}),
    )
    apply_late_camp_transition(_map(week), {})

    morphed = _find(week, "light_fight_pace_touch_day")
    assert len(morphed) == 2
    for role in morphed:
        assert role["athlete_facing_label"] == "Rhythm flush"
        assert role["late_camp_transition"] is True


def test_fight_pace_between_d14_and_d17_is_not_morphed():
    week = _week(
        [_role("fight_pace_repeatability_day", "monday", meaningful_stress=True)],
        calendar_days=_calendar({"monday": 14}),
    )
    apply_late_camp_transition(_map(week), {})
    assert _find(week, "fight_pace_repeatability_day")
    assert not _find(week, "light_fight_pace_touch_day")


def test_morphed_rhythm_touch_clears_hard_pressure_metadata():
    week = _week(
        [
            _role(
                "highest_glycolytic_day",
                "monday",
                preferred_system="glycolytic",
                meaningful_stress=True,
                combat_pressure=True,
                governance={
                    "meaningful_stress": True,
                    "main_job": "conditioning",
                    "support_cap": "light_only",
                    "forbidden_secondary_stressors": ["hinge"],
                },
            )
        ],
        calendar_days=_calendar({"monday": 10}),
    )
    apply_late_camp_transition(_map(week), {})

    role = _find(week, "light_fight_pace_touch_day")[0]
    assert role.get("meaningful_stress") is not True
    assert "combat_pressure" not in role
    assert role["preferred_system"] == "aerobic"
    assert role["original_role_key"] == "highest_glycolytic_day"
    assert role["governance"]["meaningful_stress"] is False
    assert "support_cap" not in role["governance"]
    assert role["stress_class"] == "support"


# --- Hard sparring morph -----------------------------------------------------
def test_hard_sparring_at_d17_and_closer_becomes_technical_only():
    week = _week(
        [_role("hard_sparring_day", "friday", category="sparring", meaningful_stress=True, hard_sparring_status="hard_as_planned")],
        calendar_days=_calendar({"friday": 17}),
    )
    apply_late_camp_transition(_map(week), {})

    role = _find(week, "light_combat_day")[0]
    assert role["technical_only"] is True
    assert role["no_extra_sc"] is True
    assert "hard_sparring_status" not in role
    assert role.get("meaningful_stress") is not True


def test_hard_sparring_inside_floor_d18_stays_hard():
    week = _week(
        [_role("hard_sparring_day", "friday", category="sparring")],
        calendar_days=_calendar({"friday": 18}),
    )
    apply_late_camp_transition(_map(week), {})
    assert _find(week, "hard_sparring_day")
    assert not _find(week, "light_combat_day")


# --- Extra-insert safety gating ----------------------------------------------
def _week_with_unused_taper_day(**athlete_flags):
    week = _week(
        [_role("alactic_sharpness_day", "monday")],
        calendar_days=_calendar({"monday": 11, "wednesday": 9}),
        intentionally_unused_days=[{"day": "wednesday", "role": "recovery_only_day"}],
    )
    return week


def test_clean_taper_day_gets_one_rhythm_touch():
    # Baseline: with no safety pressure the unused taper day keeps a rhythm touch,
    # proving the safety gates below are not vacuous.
    week = _week_with_unused_taper_day()
    apply_late_camp_transition(_map(week), {"fatigue": "low"})
    assert _find(week, "light_fight_pace_touch_day")
    assert week["intentionally_unused_days"] == []


def test_safety_reason_unused_day_is_not_refilled():
    week = _week(
        [_role("alactic_sharpness_day", "monday")],
        calendar_days=_calendar({"monday": 11, "wednesday": 9}),
        intentionally_unused_days=[
            {"day": "wednesday", "role": "recovery_only_day", "reason": "Intentional compression from hard sparring load."}
        ],
    )
    apply_late_camp_transition(_map(week), {"fatigue": "low"})
    assert not _find(week, "light_fight_pace_touch_day")
    assert week["intentionally_unused_days"]


def test_moderate_fatigue_blocks_extra_inserts():
    week = _week_with_unused_taper_day()
    apply_late_camp_transition(_map(week), {"fatigue": "moderate"})
    assert not _find(week, "light_fight_pace_touch_day")
    assert week["intentionally_unused_days"]


def test_active_weight_cut_blocks_extra_inserts():
    week = _week_with_unused_taper_day()
    apply_late_camp_transition(_map(week), {"fatigue": "low", "weight_cut_risk": True})
    assert not _find(week, "light_fight_pace_touch_day")
    assert week["intentionally_unused_days"]


def test_active_injury_blocks_extra_inserts():
    week = _week_with_unused_taper_day()
    apply_late_camp_transition(
        _map(week), {"fatigue": "low", "active_injury": "acute knee sprain, worsening"}
    )
    assert not _find(week, "light_fight_pace_touch_day")
    assert week["intentionally_unused_days"]


def test_compressed_week_blocks_extra_inserts():
    week = _week(
        [_role("alactic_sharpness_day", "monday")],
        calendar_days=_calendar({"monday": 11, "wednesday": 9}),
        intentionally_unused_days=[{"day": "wednesday", "role": "recovery_only_day"}],
        intentional_compression=True,
    )
    apply_late_camp_transition(_map(week), {"fatigue": "low"})
    assert not _find(week, "light_fight_pace_touch_day")


def test_stable_surface_injury_does_not_create_mobility_rehab_inserts():
    week = _week_with_unused_taper_day()
    apply_late_camp_transition(
        _map(week),
        {"fatigue": "low", "active_injury": "mild stable surface graze on shin, improving"},
    )
    # A stable surface injury never triggers a mobility/rehab insert; the only
    # thing this overlay ever adds is a low-cost rhythm/freshness touch.
    for role in week["session_roles"]:
        assert "mobility" not in str(role.get("role_key") or "")
        assert "rehab" not in str(role.get("role_key") or "")


def test_no_calendar_day_is_a_noop():
    week = _week(
        [_role("fight_pace_repeatability_day", "monday", meaningful_stress=True)],
        calendar_days=[],
    )
    apply_late_camp_transition(_map(week), {})
    assert _find(week, "fight_pace_repeatability_day")
