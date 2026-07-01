"""Combat pressure conditioning floor (PR 3).

Safe GPP/SPP build weeks must include one controlled hard combat-pressure
conditioning exposure. It must be blocked whenever a real safety rule says the
athlete should stay fresh: taper / D-7 / fight week, high+ fatigue, high+ weight
cut, medical hold, restricted rehab, needs review, active injury, or a bridge
window that already suppresses glycolytic work. A moderate weight cut alone must
NOT suppress it.
"""

from __future__ import annotations

from fightcamp.stage2_role_map import (
    _build_weekly_role_map,
    _combat_pressure_floor_blockers,
    _is_hard_pressure_conditioning_role,
)


LIMITER = {"key": "conditioning_endurance"}


def _progression(phase_by_week, *, conditioning=1, span=7):
    """Build a week-by-week progression far enough out that early weeks are safe.

    ``phase_by_week`` is a list of phase strings, one per week (week 0 is the
    earliest / farthest from the fight; the last week ends on D-0).
    """
    weeks = []
    for idx, phase in enumerate(phase_by_week):
        weeks.append(
            {
                "week_index": idx + 1,
                "phase": phase,
                "stage_key": "general_capacity",
                "span_days": span,
                "session_counts": {"strength": 1, "conditioning": conditioning, "recovery": 1},
                "conditioning_sequence": ["aerobic", "glycolytic"],
            }
        )
    return {"weeks": weeks}


def _base_athlete(**overrides):
    athlete = {
        "sport": "boxing",
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        "fight_date": "2027-07-18",
        "fatigue": "low",
        "cut_severity_bucket": "low",
        "injury_mode": "full_plan",
        "key_goals": ["conditioning"],
        "weaknesses": ["gas_tank"],
    }
    athlete.update(overrides)
    return athlete


def _week(role_map, week_index):
    return next(w for w in role_map["weeks"] if w["week_index"] == week_index)


def _floor_role(week):
    return next(
        (
            role
            for role in week["session_roles"]
            if role.get("category") == "conditioning" and role.get("combat_pressure_floor")
        ),
        None,
    )


# ---------------------------------------------------------------------------
# Gate unit coverage
# ---------------------------------------------------------------------------

def _far_week(phase="GPP", d_day=45):
    return {"phase": phase, "calendar_days": [{"weekday": "monday", "d_day": d_day}]}


class TestFloorGate:
    def test_moderate_cut_is_not_a_blocker(self):
        athlete = _base_athlete(cut_severity_bucket="moderate")
        assert _combat_pressure_floor_blockers(_far_week(), athlete) == []

    def test_low_and_none_cut_allowed(self):
        for bucket in ("none", "low"):
            athlete = _base_athlete(cut_severity_bucket=bucket)
            assert _combat_pressure_floor_blockers(_far_week(), athlete) == []

    def test_high_plus_cut_blocks(self):
        for bucket in ("high", "critical", "extreme"):
            athlete = _base_athlete(cut_severity_bucket=bucket)
            reasons = _combat_pressure_floor_blockers(_far_week(), athlete)
            assert reasons and any("weight_cut" in r for r in reasons)

    def test_high_plus_fatigue_blocks(self):
        for fatigue in ("high", "critical", "extreme"):
            athlete = _base_athlete(fatigue=fatigue)
            assert "high_fatigue" in _combat_pressure_floor_blockers(_far_week(), athlete)

    def test_medical_and_rehab_and_review_block(self):
        for mode in ("medical_hold", "restricted_rehab_only", "needs_review"):
            athlete = _base_athlete(injury_mode=mode)
            assert f"injury_mode_{mode}" in _combat_pressure_floor_blockers(_far_week(), athlete)

    def test_active_injury_blocks(self):
        athlete = _base_athlete(readiness_flags=["injury_management"])
        assert "active_injury_blocks_hard_work" in _combat_pressure_floor_blockers(_far_week(), athlete)

    def test_taper_phase_blocks(self):
        assert _combat_pressure_floor_blockers(_far_week("TAPER"), _base_athlete()) == ["floor_only_in_build_phase"]

    def test_d7_and_closer_blocks(self):
        for d in (7, 5, 1, 0):
            reasons = _combat_pressure_floor_blockers(_far_week("SPP", d), _base_athlete())
            assert "late_taper_or_fight_week" in reasons

    def test_fight_week_flag_blocks(self):
        athlete = _base_athlete(readiness_flags=["fight_week"])
        assert "fight_week_flag" in _combat_pressure_floor_blockers(_far_week(), athlete)


# ---------------------------------------------------------------------------
# A) Safe GPP gets hard pressure exposure
# ---------------------------------------------------------------------------

def test_safe_gpp_gets_hard_pressure_exposure():
    role_map = _build_weekly_role_map(
        _base_athlete(),
        _progression(["GPP", "GPP", "SPP", "TAPER"], conditioning=1),
        LIMITER,
    )
    week = _week(role_map, 1)
    assert week["combat_pressure_floor"]["active"] is True
    role = _floor_role(week)
    assert role is not None
    assert _is_hard_pressure_conditioning_role(role)
    assert role["preferred_system"] == "glycolytic"
    # RPE around 8 in GPP.
    assert role["prescribed_intensity_rpe"] == "8"
    # Purpose references gas tank / repeatability / pressure.
    purpose = role["floor_purpose"].lower()
    assert any(term in purpose for term in ("gas tank", "repeatability", "pressure"))
    # A protective stop rule that guards technique.
    assert "technique" in role["floor_stop_rule"].lower()
    # Athlete-facing label is fight-pace conditioning, not soft aerobic support.
    assert role["athlete_facing_label"] == "Fight-pace conditioning"


# ---------------------------------------------------------------------------
# B) Safe SPP gets fight-pace pressure exposure
# ---------------------------------------------------------------------------

def test_safe_spp_gets_fight_pace_pressure_exposure():
    role_map = _build_weekly_role_map(
        _base_athlete(),
        _progression(["GPP", "SPP", "SPP", "SPP", "TAPER"], conditioning=2),
        LIMITER,
    )
    # Week 2 is a safe SPP week far out.
    week = _week(role_map, 2)
    assert week["combat_pressure_floor"]["active"] is True
    role = _floor_role(week)
    assert role is not None
    assert role["role_key"] == "fight_pace_repeatability_day"
    assert role["preferred_system"] == "glycolytic"
    # RPE 8-9 in SPP.
    assert role["prescribed_intensity_rpe"] == "8-9"
    assert "fight-pace" in role["floor_purpose"].lower()


def test_safe_spp_single_conditioning_slot_is_upgraded():
    role_map = _build_weekly_role_map(
        _base_athlete(),
        _progression(["GPP", "GPP", "SPP", "SPP", "SPP", "TAPER"], conditioning=1),
        LIMITER,
    )
    # Week 3 is a safe SPP week comfortably outside the bridge window.
    week = _week(role_map, 3)
    floor = week["combat_pressure_floor"]
    assert floor["active"] is True
    assert floor["source"] == "upgraded_conditioning_slot"
    role = _floor_role(week)
    assert role["role_key"] == "fight_pace_repeatability_day"
    assert role.get("upgraded_from_combat_pressure_floor") is True


# ---------------------------------------------------------------------------
# C) Moderate cut does not suppress hard pressure exposure
# ---------------------------------------------------------------------------

def test_moderate_cut_keeps_hard_pressure_exposure():
    role_map = _build_weekly_role_map(
        _base_athlete(cut_severity_bucket="moderate"),
        _progression(["GPP", "GPP", "SPP", "TAPER"], conditioning=1),
        LIMITER,
    )
    week = _week(role_map, 1)
    assert week["combat_pressure_floor"]["active"] is True
    assert _floor_role(week) is not None


# ---------------------------------------------------------------------------
# D) High cut suppresses hard pressure exposure
# ---------------------------------------------------------------------------

def test_high_cut_suppresses_hard_pressure_exposure():
    role_map = _build_weekly_role_map(
        _base_athlete(cut_severity_bucket="high"),
        _progression(["GPP", "GPP", "SPP", "TAPER"], conditioning=1),
        LIMITER,
    )
    week = _week(role_map, 1)
    floor = week["combat_pressure_floor"]
    assert floor["active"] is False
    assert any("weight_cut_high" in r for r in floor["reason_codes"])
    assert _floor_role(week) is None


# ---------------------------------------------------------------------------
# E) High fatigue suppresses hard pressure exposure
# ---------------------------------------------------------------------------

def test_high_fatigue_suppresses_hard_pressure_exposure():
    role_map = _build_weekly_role_map(
        _base_athlete(fatigue="high", readiness_flags=["high_fatigue"]),
        _progression(["GPP", "GPP", "SPP", "TAPER"], conditioning=1),
        LIMITER,
    )
    week = _week(role_map, 1)
    assert week["combat_pressure_floor"]["active"] is False
    assert _floor_role(week) is None


# ---------------------------------------------------------------------------
# F) Taper / D-7 blocks hard pressure exposure
# ---------------------------------------------------------------------------

def test_taper_and_fight_week_block_hard_pressure_exposure():
    role_map = _build_weekly_role_map(
        _base_athlete(),
        _progression(["GPP", "SPP", "SPP", "TAPER"], conditioning=2),
        LIMITER,
    )
    for week in role_map["weeks"]:
        min_d = min(day["d_day"] for day in week["calendar_days"])
        if week["phase"] == "TAPER" or min_d <= 7:
            assert week["combat_pressure_floor"]["active"] is False
            assert _floor_role(week) is None


# ---------------------------------------------------------------------------
# G) Bridge rules respected
# ---------------------------------------------------------------------------

class TestBridgeRespected:
    def test_d20_moderate_cut_low_fatigue_allows_pressure_touch(self):
        # Baseline bridge allows one glycolytic touch at D-20 -> floor may use it.
        athlete = _base_athlete(cut_severity_bucket="moderate")
        assert _combat_pressure_floor_blockers(_far_week("SPP", 20), athlete) == []

    def test_bridge_suppression_is_not_overridden(self):
        # D-14 zeros glycolytic in the bridge -> floor must not override it.
        athlete = _base_athlete()
        reasons = _combat_pressure_floor_blockers(_far_week("SPP", 14), athlete)
        assert "bridge_suppresses_glycolytic" in reasons

    def test_floor_does_not_override_baseline_suppressed_glycolytic(self):
        role_map = _build_weekly_role_map(
            _base_athlete(),
            _progression(["GPP", "SPP", "SPP", "SPP", "TAPER"], conditioning=2),
            LIMITER,
        )
        # The last SPP week sits inside the bridge; its glycolytic role must not
        # be re-forced by the floor.
        bridge_week = _week(role_map, 4)
        assert bridge_week["combat_pressure_floor"]["active"] is False


# ---------------------------------------------------------------------------
# H) Generated-plan regression: the visible plan shows the difference
# ---------------------------------------------------------------------------

def test_generated_plan_shows_controlled_hard_exposure_language():
    role_map = _build_weekly_role_map(
        _base_athlete(),
        _progression(["GPP", "GPP", "SPP", "TAPER"], conditioning=1),
        LIMITER,
    )
    week = _week(role_map, 1)
    role = _floor_role(week)
    assert role is not None

    # One controlled combat-pressure exposure with a clear dose and purpose.
    assert "RPE 8" in role["prescribed_dose"]
    assert role["mandatory_hard_conditioning_exposure"] is True

    # Controlled dose: exactly one hard-pressure conditioning exposure this week.
    hard_roles = [
        r
        for r in week["session_roles"]
        if r.get("category") == "conditioning" and _is_hard_pressure_conditioning_role(r)
    ]
    assert len(hard_roles) == 1

    # No reckless language anywhere in the floor's coach text.
    text = " ".join(
        [role.get("floor_purpose", ""), role.get("floor_stop_rule", ""), role.get("prescribed_dose", "")]
    ).lower()
    for banned in ("destroy", "punishment until", "until failure", "ignore pain", "max effort until"):
        assert banned not in text
    # It still reads as controlled, technique-protecting coach language.
    assert "not sloppy" in text or "controlled" in text
