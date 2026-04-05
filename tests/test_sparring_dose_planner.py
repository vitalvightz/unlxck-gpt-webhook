from fightcamp.sparring_dose_planner import (
    _decide_action,
    _pick_downgrade_target,
    compute_hard_sparring_plan,
)


def _week(*, phase: str = "SPP", stage_key: str = "specific_density_build", hard_days: list[str] | None = None, session_roles: list[dict] | None = None) -> dict:
    return {
        "phase": phase,
        "stage_key": stage_key,
        "week_index": 1,
        "declared_hard_sparring_days": hard_days or ["Tuesday", "Thursday"],
        "session_roles": session_roles or [],
    }


def _athlete(
    *,
    fatigue: str = "low",
    days_until_fight: int = 24,
    short_notice: bool = False,
    weight_cut_pct: float = 0.0,
    weight_cut_risk: bool = False,
    readiness_flags: list[str] | None = None,
    injuries: list[str] | None = None,
    hard_days: list[str] | None = None,
) -> dict:
    return {
        "sport": "boxing",
        "fatigue": fatigue,
        "days_until_fight": days_until_fight,
        "short_notice": short_notice,
        "weight_cut_pct": weight_cut_pct,
        "weight_cut_risk": weight_cut_risk,
        "readiness_flags": readiness_flags or [],
        "injuries": injuries or [],
        "hard_sparring_days": hard_days or ["Tuesday", "Thursday"],
    }


def test_two_hard_spar_days_normal_week_stay_hard_as_planned():
    plan = compute_hard_sparring_plan(
        week=_week(),
        athlete_snapshot=_athlete(),
    )

    assert [entry["status"] for entry in plan] == ["hard_as_planned", "hard_as_planned"]


def test_high_fatigue_with_two_hard_days_downgrades_exactly_one_day():
    plan = compute_hard_sparring_plan(
        week=_week(),
        athlete_snapshot=_athlete(fatigue="high"),
    )

    downgraded = [entry for entry in plan if entry["status"] != "hard_as_planned"]
    assert len(downgraded) == 1
    assert downgraded[0]["day"] == "Thursday"
    assert downgraded[0]["status"] == "deload_suggested"


def test_moderate_fatigue_and_moderate_cut_do_not_downgrade():
    plan = compute_hard_sparring_plan(
        week=_week(),
        athlete_snapshot=_athlete(
            fatigue="moderate",
            weight_cut_pct=3.8,
            weight_cut_risk=True,
            readiness_flags=["active_weight_cut"],
        ),
    )

    assert all(entry["status"] == "hard_as_planned" for entry in plan)


def test_high_week_pressure_and_mild_injury_do_not_downgrade():
    plan = compute_hard_sparring_plan(
        week=_week(phase="TAPER", stage_key="fight_week_survival_rhythm", hard_days=["Thursday"]),
        athlete_snapshot=_athlete(
            days_until_fight=6,
            readiness_flags=["fight_week"],
            injuries=["mild stable shoulder soreness"],
            hard_days=["Thursday"],
        ),
    )

    # D-6 countdown override deloads all hard sparring days
    assert all(entry["status"] != "hard_as_planned" for entry in plan)
    assert plan[0]["coach_note"]


def test_high_week_pressure_and_moderate_injury_deloads():
    plan = compute_hard_sparring_plan(
        week=_week(phase="TAPER", stage_key="fight_week_survival_rhythm"),
        athlete_snapshot=_athlete(
            days_until_fight=6,
            readiness_flags=["fight_week"],
            injuries=["moderate shoulder strain"],
        ),
    )

    # D-6 countdown override deloads ALL days, not just one
    downgraded = [entry for entry in plan if entry["status"] != "hard_as_planned"]
    assert len(downgraded) == 2
    assert all(entry["status"] == "deload_suggested" for entry in downgraded)


def test_d7_caps_three_declared_hard_days_to_one_actual_hard_day():
    plan = compute_hard_sparring_plan(
        week=_week(hard_days=["Monday", "Wednesday", "Friday"]),
        athlete_snapshot=_athlete(days_until_fight=7, hard_days=["Monday", "Wednesday", "Friday"]),
    )

    assert [entry["status"] for entry in plan].count("hard_as_planned") == 1
    assert [entry["status"] for entry in plan].count("deload_suggested") == 2
    assert all(entry.get("coach_note") for entry in plan if entry["status"] == "deload_suggested")


def test_instability_or_daily_symptoms_convert():
    instability_plan = compute_hard_sparring_plan(
        week=_week(),
        athlete_snapshot=_athlete(injuries=["ankle instability"]),
    )
    daily_symptom_plan = compute_hard_sparring_plan(
        week=_week(),
        athlete_snapshot=_athlete(injuries=["shoulder pain with daily sleep disruption"]),
    )

    assert any(entry["status"] == "convert_to_technical_suggested" for entry in instability_plan)
    assert any(entry["status"] == "convert_to_technical_suggested" for entry in daily_symptom_plan)


def test_worsening_high_risk_converts():
    plan = compute_hard_sparring_plan(
        week=_week(),
        athlete_snapshot=_athlete(injuries=["worsening knee instability"]),
    )

    assert any(entry["status"] == "convert_to_technical_suggested" for entry in plan)


def test_borderline_cases_return_none_action():
    assert _decide_action(
        hard_day_count=2,
        fatigue="moderate",
        cut="moderate",
        week_press="none",
        injury={"severity": "none", "high_risk": False, "worsening": False, "instability": False, "daily_symptoms": False},
    ) is None
    assert _decide_action(
        hard_day_count=1,
        fatigue="low",
        cut="none",
        week_press="high",
        injury={"severity": "mild", "high_risk": False, "worsening": False, "instability": False, "daily_symptoms": False},
    ) is None


def test_pick_downgrade_target_defaults_to_latest_declared_day():
    target = _pick_downgrade_target(["Tuesday", "Thursday"], week=_week())

    assert target == "Thursday"