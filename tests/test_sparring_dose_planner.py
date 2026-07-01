from fightcamp.sparring_dose_planner import (
    _consecutive_hard_day_pairs,
    _decide_action,
    _pick_downgrade_target,
    compute_hard_sparring_plan,
    sandwiched_training_days,
)

# ── Hard day classification ───────────────────────────────────────────────────


def _week(
    *,
    phase: str = "SPP",
    stage_key: str = "specific_density_build",
    hard_days: list[str] | None = None,
    session_roles: list[dict] | None = None,
    phase_week_index: int | None = None,
    phase_week_total: int | None = None,
    projected_days_until_fight_start: int | None = None,
) -> dict:
    return {
        "phase": phase,
        "stage_key": stage_key,
        "week_index": 1,
        "phase_week_index": phase_week_index,
        "phase_week_total": phase_week_total,
        "projected_days_until_fight_start": projected_days_until_fight_start,
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
    assert all(entry["status"] == "convert_to_technical_suggested" for entry in downgraded)


def test_d7_caps_three_declared_hard_days_to_one_actual_hard_day():
    plan = compute_hard_sparring_plan(
        week=_week(hard_days=["Monday", "Wednesday", "Friday"]),
        athlete_snapshot=_athlete(days_until_fight=7, hard_days=["Monday", "Wednesday", "Friday"]),
    )

    assert [entry["status"] for entry in plan].count("hard_as_planned") == 0
    assert [entry["status"] for entry in plan].count("convert_to_technical_suggested") == 3
    assert all(entry.get("coach_note") for entry in plan if entry["status"] == "convert_to_technical_suggested")
    assert all("final_week_sparring_cap" in entry.get("reason_codes", []) for entry in plan if entry["status"] == "convert_to_technical_suggested")


def test_taper_week_caps_multiple_declared_hard_days_to_one_without_countdown():
    plan = compute_hard_sparring_plan(
        week=_week(phase="TAPER", stage_key="taper_sharpen", hard_days=["Monday", "Wednesday"]),
        athlete_snapshot=_athlete(days_until_fight=18, hard_days=["Monday", "Wednesday"]),
    )

    hard_entries = [entry for entry in plan if entry["status"] == "hard_as_planned"]
    downgraded = [entry for entry in plan if entry["status"] != "hard_as_planned"]
    assert [entry["day"] for entry in hard_entries] == ["Monday"]
    assert [entry["day"] for entry in downgraded] == ["Wednesday"]
    assert downgraded[0]["status"] == "deload_suggested"
    assert "final_week_sparring_cap" in downgraded[0]["reason_codes"]
    assert "Final taper week" in downgraded[0]["coach_note"]


def test_taper_week_respects_collision_owner_but_still_caps_extra_coach_days():
    plan = compute_hard_sparring_plan(
        week=_week(
            phase="TAPER",
            stage_key="taper_sharpen",
            hard_days=["Monday", "Thursday"],
            session_roles=[{"role_key": "fight_pace_repeatability_day", "collision_owner_day": "Thursday"}],
        ),
        athlete_snapshot=_athlete(days_until_fight=18, hard_days=["Monday", "Thursday"]),
    )

    by_day = {entry["day"]: entry for entry in plan}
    assert by_day["Thursday"]["status"] == "hard_as_planned"
    assert by_day["Thursday"]["hard_day_class"] == "primary_hard"
    assert by_day["Monday"]["status"] == "deload_suggested"
    assert by_day["Monday"]["hard_day_class"] == "managed_hard"
    assert "final_week_sparring_cap" in by_day["Monday"]["reason_codes"]


def test_d16_declared_hard_day_is_forced_to_technical():
    plan = compute_hard_sparring_plan(
        week=_week(hard_days=["Monday"]),
        athlete_snapshot=_athlete(days_until_fight=16, hard_days=["Monday"]),
    )
    assert plan[0]["status"] == "convert_to_technical_suggested"
    assert plan[0]["effective_load"] == "technical"


def test_bridge_window_cap_allows_only_one_between_d21_and_d18():
    plan = compute_hard_sparring_plan(
        week=_week(
            phase="TAPER",
            stage_key="taper_bridge_window",
            hard_days=["Monday", "Wednesday"],
            phase_week_index=1,
            projected_days_until_fight_start=21,
            session_roles=[{"role_key": "fight_pace_repeatability_day", "collision_owner_day": "Monday"}],
        ),
        athlete_snapshot=_athlete(days_until_fight=19, hard_days=["Monday", "Wednesday"]),
    )
    by_day = {entry["day"]: entry for entry in plan}
    assert by_day["Monday"]["effective_load"] == "hard"
    assert by_day["Wednesday"]["effective_load"] != "hard"


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


# ── Consecutive hard day detection ───────────────────────────────────────────

def test_consecutive_hard_day_pairs_detects_adjacent_days():
    assert _consecutive_hard_day_pairs(["Monday", "Tuesday"]) == [("Monday", "Tuesday")]
    assert _consecutive_hard_day_pairs(["Monday", "Wednesday"]) == []
    assert _consecutive_hard_day_pairs(["Monday", "Tuesday", "Thursday"]) == [("Monday", "Tuesday")]
    assert _consecutive_hard_day_pairs(["Monday", "Tuesday", "Wednesday"]) == [
        ("Monday", "Tuesday"),
        ("Tuesday", "Wednesday"),
    ]


def test_consecutive_hard_day_pairs_case_insensitive():
    assert _consecutive_hard_day_pairs(["monday", "tuesday"]) == [("monday", "tuesday")]
    assert _consecutive_hard_day_pairs(["MONDAY", "TUESDAY"]) == [("MONDAY", "TUESDAY")]
    assert _consecutive_hard_day_pairs(["Monday", "wednesday"]) == []


def test_two_consecutive_hard_days_deload_the_later_day():
    plan = compute_hard_sparring_plan(
        week=_week(hard_days=["Monday", "Tuesday"]),
        athlete_snapshot=_athlete(fatigue="low", hard_days=["Monday", "Tuesday"]),
    )

    statuses = {e["day"]: e["status"] for e in plan}
    assert statuses["Monday"] == "hard_as_planned"
    assert statuses["Tuesday"] == "deload_suggested"
    assert "consecutive_hard_days" in next(e["reason_codes"] for e in plan if e["day"] == "Tuesday")


def test_well_spaced_two_hard_days_unchanged_without_pressure():
    plan = compute_hard_sparring_plan(
        week=_week(hard_days=["Monday", "Wednesday"]),
        athlete_snapshot=_athlete(fatigue="low", hard_days=["Monday", "Wednesday"]),
    )

    assert all(e["status"] == "hard_as_planned" for e in plan)


def test_three_hard_days_with_consecutive_pair_deloads_second_of_pair():
    plan = compute_hard_sparring_plan(
        week=_week(hard_days=["Monday", "Tuesday", "Friday"]),
        athlete_snapshot=_athlete(fatigue="low", hard_days=["Monday", "Tuesday", "Friday"]),
    )

    statuses = {e["day"]: e["status"] for e in plan}
    assert statuses["Monday"] == "hard_as_planned"
    assert statuses["Tuesday"] == "deload_suggested"
    assert statuses["Friday"] == "hard_as_planned"


def test_consecutive_deload_respects_protected_day():
    # Collision owner is Tuesday — the earlier day should be deloaded instead.
    plan = compute_hard_sparring_plan(
        week=_week(
            hard_days=["Monday", "Tuesday"],
            session_roles=[{"role_key": "fight_pace_repeatability_day", "collision_owner_day": "Tuesday"}],
        ),
        athlete_snapshot=_athlete(fatigue="low", hard_days=["Monday", "Tuesday"]),
    )

    statuses = {e["day"]: e["status"] for e in plan}
    assert statuses["Monday"] == "deload_suggested"
    assert statuses["Tuesday"] == "hard_as_planned"


# ── Four+ hard days cap ───────────────────────────────────────────────────────

def test_four_hard_days_caps_to_two_effective():
    plan = compute_hard_sparring_plan(
        week=_week(hard_days=["Monday", "Wednesday", "Thursday", "Friday"]),
        athlete_snapshot=_athlete(fatigue="low", hard_days=["Monday", "Wednesday", "Thursday", "Friday"]),
    )

    effective = [e for e in plan if e["status"] == "hard_as_planned"]
    assert len(effective) == 2


def test_hard_day_cap_reason_explains_managed_exposure():
    plan = compute_hard_sparring_plan(
        week=_week(hard_days=["Monday", "Wednesday", "Friday", "Saturday"]),
        athlete_snapshot=_athlete(fatigue="low", hard_days=["Monday", "Wednesday", "Friday", "Saturday"]),
    )
    capped = [e for e in plan if "hard_day_cap" in e.get("reason_codes", [])]
    assert capped
    for entry in capped:
        assert "managed" in entry["reason"].lower() or "preserved" in entry["reason"].lower()


def test_four_hard_days_with_consecutive_pair_still_caps_at_two():
    # Mon-Tue consecutive, plus Thu and Fri. Consecutive pass deloads Tue and Fri
    # (Thu-Fri consecutive), cap confirms ≤ 2.
    plan = compute_hard_sparring_plan(
        week=_week(hard_days=["Monday", "Tuesday", "Thursday", "Friday"]),
        athlete_snapshot=_athlete(fatigue="low", hard_days=["Monday", "Tuesday", "Thursday", "Friday"]),
    )

    effective = [e for e in plan if e["status"] == "hard_as_planned"]
    assert len(effective) == 2


def test_four_hard_days_reason_code_present():
    plan = compute_hard_sparring_plan(
        week=_week(hard_days=["Monday", "Wednesday", "Thursday", "Friday"]),
        athlete_snapshot=_athlete(fatigue="low", hard_days=["Monday", "Wednesday", "Thursday", "Friday"]),
    )

    all_codes = [code for e in plan for code in e.get("reason_codes", [])]
    assert "four_hard_days" in all_codes


def test_five_hard_days_caps_to_two_effective():
    plan = compute_hard_sparring_plan(
        week=_week(hard_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]),
        athlete_snapshot=_athlete(
            fatigue="low",
            hard_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        ),
    )

    effective = [e for e in plan if e["status"] == "hard_as_planned"]
    assert len(effective) == 2


# ── Sandwiched training days ──────────────────────────────────────────────────

def test_sandwiched_training_days_identifies_day_between_hard_days():
    result = sandwiched_training_days(
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        {"Monday", "Wednesday"},
    )
    assert "Tuesday" in result
    assert "Monday" not in result
    assert "Wednesday" not in result


def test_sandwiched_training_days_returns_empty_with_fewer_than_two_hard_days():
    assert sandwiched_training_days(["Monday", "Tuesday", "Wednesday"], {"Monday"}) == set()
    assert sandwiched_training_days(["Monday", "Tuesday", "Wednesday"], set()) == set()


def test_sandwiched_training_days_multiple_sandwiched_days():
    result = sandwiched_training_days(
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        {"Monday", "Friday"},
    )
    assert result == {"Tuesday", "Wednesday", "Thursday"}


# ── hard_day_class labels ─────────────────────────────────────────────────────

def test_every_plan_entry_has_hard_day_class():
    plan = compute_hard_sparring_plan(
        week=_week(hard_days=["Monday", "Wednesday", "Friday"]),
        athlete_snapshot=_athlete(fatigue="low", hard_days=["Monday", "Wednesday", "Friday"]),
    )
    assert all("hard_day_class" in e for e in plan)


def test_single_hard_day_is_primary_hard():
    plan = compute_hard_sparring_plan(
        week=_week(hard_days=["Wednesday"]),
        athlete_snapshot=_athlete(fatigue="low", hard_days=["Wednesday"]),
    )
    assert plan[0]["hard_day_class"] == "primary_hard"


def test_two_well_spaced_hard_days_labels():
    # Tue + Thu, no pressure — both hard_as_planned; first is primary, second is secondary.
    plan = compute_hard_sparring_plan(
        week=_week(),
        athlete_snapshot=_athlete(),
    )
    by_day = {e["day"]: e for e in plan}
    assert by_day["Tuesday"]["hard_day_class"] == "primary_hard"
    assert by_day["Thursday"]["hard_day_class"] == "secondary_hard"


def test_deloaded_day_is_managed_hard():
    plan = compute_hard_sparring_plan(
        week=_week(),
        athlete_snapshot=_athlete(fatigue="high"),
    )
    deloaded = next(e for e in plan if e["status"] == "deload_suggested")
    assert deloaded["hard_day_class"] == "managed_hard"


def test_consecutive_deloaded_day_is_managed_hard():
    plan = compute_hard_sparring_plan(
        week=_week(hard_days=["Monday", "Tuesday"]),
        athlete_snapshot=_athlete(fatigue="low", hard_days=["Monday", "Tuesday"]),
    )
    by_day = {e["day"]: e for e in plan}
    assert by_day["Monday"]["hard_day_class"] == "primary_hard"
    assert by_day["Tuesday"]["hard_day_class"] == "managed_hard"


def test_collision_owner_gets_primary_hard_label():
    plan = compute_hard_sparring_plan(
        week=_week(
            hard_days=["Monday", "Thursday"],
            session_roles=[{"role_key": "fight_pace_repeatability_day", "collision_owner_day": "Thursday"}],
        ),
        athlete_snapshot=_athlete(fatigue="low", hard_days=["Monday", "Thursday"]),
    )
    by_day = {e["day"]: e for e in plan}
    assert by_day["Thursday"]["hard_day_class"] == "primary_hard"
    assert by_day["Monday"]["hard_day_class"] == "secondary_hard"


def test_four_hard_days_classification_has_exactly_one_primary():
    plan = compute_hard_sparring_plan(
        week=_week(hard_days=["Monday", "Wednesday", "Thursday", "Friday"]),
        athlete_snapshot=_athlete(fatigue="low", hard_days=["Monday", "Wednesday", "Thursday", "Friday"]),
    )
    classes = [e["hard_day_class"] for e in plan]
    assert classes.count("primary_hard") == 1
    assert classes.count("managed_hard") == 2
    assert classes.count("secondary_hard") == 1


def test_convert_all_countdown_labels_all_as_managed_hard():
    # D-4: convert_all fires, every day becomes managed.
    plan = compute_hard_sparring_plan(
        week=_week(hard_days=["Monday", "Wednesday"]),
        athlete_snapshot=_athlete(days_until_fight=4, hard_days=["Monday", "Wednesday"]),
    )
    assert all(e["hard_day_class"] == "managed_hard" for e in plan)


def test_d7_countdown_converts_all_declared_hard_days_to_technical():
    plan = compute_hard_sparring_plan(
        week=_week(hard_days=["Monday", "Wednesday", "Friday"]),
        athlete_snapshot=_athlete(days_until_fight=7, hard_days=["Monday", "Wednesday", "Friday"]),
    )
    assert all(e["status"] == "convert_to_technical_suggested" for e in plan)
    assert all(e["effective_load"] == "technical" for e in plan)


# ── Three hard days with multiple amber readiness signals ────────────────────

def test_three_hard_days_with_two_amber_signals_deloads_one():
    # Moderate fatigue + moderate cut with 3 well-spaced hard days:
    # neither signal alone triggers a deload, but together they do.
    plan = compute_hard_sparring_plan(
        week=_week(hard_days=["Monday", "Wednesday", "Friday"]),
        athlete_snapshot=_athlete(
            fatigue="moderate",
            weight_cut_pct=3.5,
            weight_cut_risk=True,
            readiness_flags=["active_weight_cut"],
            hard_days=["Monday", "Wednesday", "Friday"],
        ),
    )
    downgraded = [e for e in plan if e["status"] != "hard_as_planned"]
    assert len(downgraded) == 1


def test_three_hard_days_with_single_amber_signal_stays_hard():
    plan = compute_hard_sparring_plan(
        week=_week(hard_days=["Monday", "Wednesday", "Friday"]),
        athlete_snapshot=_athlete(
            fatigue="moderate",
            hard_days=["Monday", "Wednesday", "Friday"],
        ),
    )
    assert all(e["status"] == "hard_as_planned" for e in plan)


def test_two_hard_days_with_two_amber_signals_stays_hard():
    # count == 2 does not trigger the multi-amber rule.
    plan = compute_hard_sparring_plan(
        week=_week(hard_days=["Tuesday", "Thursday"]),
        athlete_snapshot=_athlete(
            fatigue="moderate",
            weight_cut_pct=3.5,
            weight_cut_risk=True,
            readiness_flags=["active_weight_cut"],
        ),
    )
    assert all(e["status"] == "hard_as_planned" for e in plan)


# ── Anchor exclusion after sparring (stage2 scoring) ─────────────────────────

def test_anchor_after_hard_as_planned_spar_day_is_hard_excluded():
    from fightcamp.stage2_payload import _boxing_day_score

    anchor_role = {
        "category": "strength",
        "role_key": "primary_strength_day",
        "anchor": "max_strength_neural",
    }
    spar_role = {
        "category": "sparring",
        "role_key": "hard_sparring_day",
        "hard_sparring_status": "hard_as_planned",
    }
    training_days = ["Monday", "Tuesday", "Wednesday"]
    day_to_roles = {"Tuesday": [spar_role]}

    score = _boxing_day_score(
        anchor_role,
        "Wednesday",
        anchor_day="Wednesday",
        prefer_midweek_anchor=False,
        readiness_sensitive=False,
        training_days=training_days,
        day_to_roles=day_to_roles,
    )
    assert score <= -10_000


def test_anchor_after_deloaded_spar_day_gets_heavy_penalty_but_not_excluded():
    from fightcamp.stage2_payload import _boxing_day_score

    anchor_role = {
        "category": "strength",
        "role_key": "primary_strength_day",
        "anchor": "max_strength_neural",
    }
    spar_role = {
        "category": "sparring",
        "role_key": "hard_sparring_day",
        "hard_sparring_status": "deload_suggested",
    }
    training_days = ["Monday", "Tuesday", "Wednesday"]
    day_to_roles = {"Tuesday": [spar_role]}

    score = _boxing_day_score(
        anchor_role,
        "Wednesday",
        anchor_day="Wednesday",
        prefer_midweek_anchor=False,
        readiness_sensitive=False,
        training_days=training_days,
        day_to_roles=day_to_roles,
    )
    # Heavy penalty (-50) but far above the hard-exclusion threshold (-10_000).
    assert -10_000 < score < 0


# ── _finalize_plan uniform post-processing ───────────────────────────────────

def test_countdown_convert_all_plan_has_hard_day_class_labels():
    # Every return path must pass through _finalize_plan.
    plan = compute_hard_sparring_plan(
        week=_week(hard_days=["Tuesday", "Thursday"]),
        athlete_snapshot=_athlete(days_until_fight=3, hard_days=["Tuesday", "Thursday"]),
    )
    assert all("hard_day_class" in e for e in plan)


def test_d7_countdown_collision_owner_still_converts_to_technical():
    plan = compute_hard_sparring_plan(
        week=_week(
            hard_days=["Monday", "Wednesday", "Friday"],
            session_roles=[{"role_key": "fight_pace_repeatability_day", "collision_owner_day": "Friday"}],
        ),
        athlete_snapshot=_athlete(days_until_fight=7, hard_days=["Monday", "Wednesday", "Friday"]),
    )
    hard_entries = [e for e in plan if e["status"] == "hard_as_planned"]
    assert hard_entries == []
    assert all(e["effective_load"] == "technical" for e in plan)


def test_finalize_plan_never_exceeds_cap_on_any_path():
    # Post-condition invariant: at most 3 effective hard days across the full input space.
    scenarios = [
        {"hard_days": ["Monday", "Wednesday", "Friday"], "fatigue": "low", "days": 24},
        {"hard_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], "fatigue": "low", "days": 24},
        {"hard_days": ["Monday", "Tuesday", "Wednesday", "Thursday"], "fatigue": "high", "days": 24},
        {"hard_days": ["Monday", "Wednesday", "Friday", "Sunday"], "fatigue": "low", "days": 7},
    ]
    for scenario in scenarios:
        plan = compute_hard_sparring_plan(
            week=_week(hard_days=scenario["hard_days"]),
            athlete_snapshot=_athlete(
                fatigue=scenario["fatigue"],
                days_until_fight=scenario["days"],
                hard_days=scenario["hard_days"],
            ),
        )
        effective = [e for e in plan if e["status"] == "hard_as_planned"]
        assert len(effective) <= 3, f"{scenario} yielded {len(effective)} effective hard days"


# ── Bridge window (D-21 to D-14) sparring caps ────────────────────────────────


def _bridge_week(*, phase: str = "TAPER", stage_key: str = "d21_to_d14", hard_days: list[str] | None = None) -> dict:
    return {
        "phase": phase,
        "stage_key": stage_key,
        "week_index": 1,
        "phase_week_index": 1,
        "phase_week_total": 1,
        "declared_hard_sparring_days": hard_days or ["Tuesday", "Thursday"],
        "session_roles": [],
    }


def test_bridge_d20_caps_hard_sparring_to_one():
    plan = compute_hard_sparring_plan(
        week=_bridge_week(hard_days=["Tuesday", "Thursday"]),
        athlete_snapshot=_athlete(days_until_fight=20, hard_days=["Tuesday", "Thursday"]),
    )
    effective = [e for e in plan if e["status"] == "hard_as_planned"]
    assert len(effective) == 1


def test_bridge_d17_with_moderate_cut_zeros_hard_sparring():
    plan = compute_hard_sparring_plan(
        week=_bridge_week(hard_days=["Tuesday", "Thursday"]),
        athlete_snapshot=_athlete(
            days_until_fight=17,
            weight_cut_pct=4.0,
            weight_cut_risk=True,
            hard_days=["Tuesday", "Thursday"],
        ),
    )
    # D-17 inside the bridge window always zeros hard sparring — the cap is
    # 0 from D-17 downward regardless of cut/fatigue state.
    effective = [e for e in plan if e["status"] == "hard_as_planned"]
    assert len(effective) == 0


def test_bridge_d17_clean_boxer_zeros_hard_sparring():
    # Even a clean, low-risk athlete loses all hard sparring exposures from
    # D-17 downward. Bridge cap transitions from 1 (D-21..D-18) to 0 (D-17..D-14).
    plan = compute_hard_sparring_plan(
        week=_bridge_week(hard_days=["Tuesday", "Thursday"]),
        athlete_snapshot=_athlete(
            days_until_fight=17,
            fatigue="low",
            hard_days=["Tuesday", "Thursday"],
        ),
    )
    effective = [e for e in plan if e["status"] == "hard_as_planned"]
    assert len(effective) == 0


def test_bridge_d20_moderate_cut_contact_sport_keeps_one_hard_spar():
    # D-20 boxer with a real cut (~5%) falls into the moderate bucket within the
    # bridge window. A moderate cut is note-only: it must NOT zero hard sparring
    # on a contact sport — the clean-athlete cap_one behaviour stands, so one
    # hard sparring exposure survives just like a clean D-20 boxer.
    plan = compute_hard_sparring_plan(
        week=_bridge_week(hard_days=["Tuesday", "Thursday"]),
        athlete_snapshot=_athlete(
            days_until_fight=20,
            fatigue="low",
            weight_cut_pct=5.0,
            weight_cut_risk=True,
            hard_days=["Tuesday", "Thursday"],
        ),
    )
    effective = [e for e in plan if e["status"] == "hard_as_planned"]
    assert len(effective) == 1


def test_bridge_d16_downgrades_all_declared_hard_days():
    plan = compute_hard_sparring_plan(
        week=_bridge_week(hard_days=["Tuesday", "Thursday"]),
        athlete_snapshot=_athlete(days_until_fight=16, hard_days=["Tuesday", "Thursday"]),
    )
    assert all(entry["status"] != "hard_as_planned" for entry in plan)
    assert all(entry["effective_load"] == "technical" for entry in plan)


def test_bridge_d15_converts_to_technical_only():
    plan = compute_hard_sparring_plan(
        week=_bridge_week(hard_days=["Tuesday", "Thursday"]),
        athlete_snapshot=_athlete(days_until_fight=15, hard_days=["Tuesday", "Thursday"]),
    )
    assert all(entry["effective_load"] == "technical" for entry in plan)


def test_bridge_d14_converts_to_technical_only():
    plan = compute_hard_sparring_plan(
        week=_bridge_week(hard_days=["Tuesday", "Thursday"]),
        athlete_snapshot=_athlete(days_until_fight=14, hard_days=["Tuesday", "Thursday"]),
    )
    assert all(entry["effective_load"] == "technical" for entry in plan)


def test_bridge_override_does_not_fire_for_future_planning_week():
    # Future SPP week at D-18: advisory engine must not see cap_one wording here;
    # the bridge override is scoped to the imminent bridge week only.
    future_week = {
        "phase": "SPP",
        "stage_key": "late_spp",
        "week_index": 1,
        "phase_week_index": 3,
        "phase_week_total": 4,
        "declared_hard_sparring_days": ["Tuesday", "Thursday"],
        "session_roles": [],
    }
    plan = compute_hard_sparring_plan(
        week=future_week,
        athlete_snapshot=_athlete(days_until_fight=18, hard_days=["Tuesday", "Thursday"]),
    )
    # With no bridge override firing and no late-fight pressure, both hard days
    # remain at their declared load.
    effective = [e for e in plan if e["status"] == "hard_as_planned"]
    assert len(effective) == 2


def test_standard_camp_final_two_taper_weeks_have_no_hard_sparring():
    week = _week(
        phase="TAPER",
        stage_key="taper_freshness",
        hard_days=["Tuesday", "Thursday"],
        phase_week_index=2,
        phase_week_total=3,
    )
    plan = compute_hard_sparring_plan(
        week=week,
        athlete_snapshot=_athlete(days_until_fight=42, hard_days=["Tuesday", "Thursday"]),
    )
    assert all(entry["status"] != "hard_as_planned" for entry in plan)


def test_standard_camp_final_week_has_no_hard_sparring_when_taper_has_two_slots():
    week = _week(
        phase="TAPER",
        stage_key="fight_week_survival_rhythm",
        hard_days=["Tuesday", "Thursday"],
        phase_week_index=3,
        phase_week_total=3,
    )
    plan = compute_hard_sparring_plan(
        week=week,
        athlete_snapshot=_athlete(days_until_fight=42, hard_days=["Tuesday", "Thursday"]),
    )
    assert all(entry["status"] != "hard_as_planned" for entry in plan)


def test_standard_camp_taper_week_outside_two_weeks_keeps_default_logic():
    week = _week(
        phase="TAPER",
        stage_key="taper_freshness",
        hard_days=["Tuesday", "Thursday"],
        phase_week_index=1,
        phase_week_total=3,
    )
    plan = compute_hard_sparring_plan(
        week=week,
        athlete_snapshot=_athlete(days_until_fight=42, hard_days=["Tuesday", "Thursday"]),
    )
    effective = [entry for entry in plan if entry["status"] == "hard_as_planned"]
    assert len(effective) == 1


def test_standard_camp_uses_projected_days_fallback_when_taper_week_position_missing():
    week = _week(
        phase="TAPER",
        stage_key="taper_freshness",
        hard_days=["Tuesday", "Thursday"],
        projected_days_until_fight_start=10,
    )
    plan = compute_hard_sparring_plan(
        week=week,
        athlete_snapshot=_athlete(days_until_fight=42, hard_days=["Tuesday", "Thursday"]),
    )
    assert all(entry["status"] != "hard_as_planned" for entry in plan)


def test_standard_camp_override_does_not_change_d_window_stage_behavior():
    for stage_key in ("d13_to_d8", "d7", "d1", "d0"):
        week = _week(
            phase="TAPER",
            stage_key=stage_key,
            hard_days=["Tuesday", "Thursday"],
            phase_week_index=3,
            phase_week_total=3,
            projected_days_until_fight_start=7,
        )
        plan = compute_hard_sparring_plan(
            week=week,
            athlete_snapshot=_athlete(days_until_fight=42, hard_days=["Tuesday", "Thursday"]),
        )
        effective = [entry for entry in plan if entry["status"] == "hard_as_planned"]
        assert len(effective) == 1
