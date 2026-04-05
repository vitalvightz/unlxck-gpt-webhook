from fightcamp.sparring_advisories import (
    _highest_risk_entry,
    _injury_risk,
    _sparring_injury_entries,
    build_plan_advisories,
)


def _planning_brief(
    *,
    phase: str = "SPP",
    stage_key: str = "base_build",
    days_until_fight: int = 24,
    fatigue: str = "low",
    readiness_flags: list[str] | None = None,
    injuries: list[str] | None = None,
    weight_cut_pct: float = 0.0,
    hard_sparring_days: list[str] | None = None,
    weeks: list[dict] | None = None,
) -> dict:
    return {
        "athlete_snapshot": {
            "sport": "boxing",
            "days_until_fight": days_until_fight,
            "fatigue": fatigue,
            "short_notice": days_until_fight <= 14,
            "readiness_flags": readiness_flags or [],
            "injuries": injuries or [],
            "weight_cut_pct": weight_cut_pct,
            "hard_sparring_days": hard_sparring_days or ["Tuesday", "Thursday"],
            "technical_skill_days": ["Monday"],
        },
        "weekly_role_map": {
            "weeks": weeks
            or [
                {
                    "phase": phase,
                    "week_index": 1,
                    "phase_week_index": 1,
                    "phase_week_total": 1,
                    "stage_key": stage_key,
                    "declared_hard_sparring_days": hard_sparring_days or ["Tuesday", "Thursday"],
                    "declared_technical_skill_days": ["Monday"],
                    "declared_training_days": ["Monday", "Tuesday", "Thursday", "Saturday"],
                    "session_roles": [],
                    "suppressed_roles": [],
                }
            ]
        },
    }


def test_no_advisory_when_hard_sparring_exists_without_material_week_collision():
    advisories = build_plan_advisories(
        planning_brief=_planning_brief(
            fatigue="low",
            injuries=[],
            weight_cut_pct=0.0,
            readiness_flags=[],
        )
    )

    assert advisories == []


def test_no_advisory_for_mild_stable_issue_in_normal_week():
    advisories = build_plan_advisories(
        planning_brief=_planning_brief(
            fatigue="moderate",
            injuries=["mild stable shoulder soreness"],
            weight_cut_pct=0.0,
            readiness_flags=[],
            phase="SPP",
            stage_key="mid_camp_build",
        )
    )

    assert advisories == []


def test_deload_advisory_requires_real_hard_sparring_collision_in_taper_week():
    advisories = build_plan_advisories(
        planning_brief=_planning_brief(
            phase="TAPER",
            stage_key="fight_week_survival_rhythm",
            days_until_fight=6,
            fatigue="low",
            readiness_flags=["fight_week"],
            injuries=["mild stable shoulder soreness"],
            hard_sparring_days=["Tuesday", "Thursday"],
        )
    )

    assert len(advisories) == 1
    advisory = advisories[0]
    assert advisory["action"] == "deload"
    assert advisory["phase"] == "TAPER"
    assert advisory["days"] == ["Tuesday", "Thursday"]
    assert "fight-week pressure is active" in advisory["reason"]
    assert advisory["title"] == "Coach note"
    assert advisory["disclaimer"] == "Treat this as a flag, not an automatic change to your saved plan."


def test_convert_advisory_for_worsening_instability_during_high_pressure_week():
    advisories = build_plan_advisories(
        planning_brief=_planning_brief(
            phase="TAPER",
            stage_key="fight_week_survival_rhythm",
            days_until_fight=5,
            fatigue="high",
            readiness_flags=["fight_week", "active_weight_cut"],
            injuries=["worsening ankle instability"],
            weight_cut_pct=5.4,
            hard_sparring_days=["Tuesday", "Thursday"],
        )
    )

    assert len(advisories) == 1
    advisory = advisories[0]
    assert advisory["action"] == "convert"
    assert advisory["risk_band"] == "red"
    assert advisory["replacement"] == "Technical rounds with stance-stable pad or bag work."
    assert "worsening ankle instability" in advisory["reason"]


def test_readiness_only_advisory_omits_risk_band_without_injuries():
    advisories = build_plan_advisories(
        planning_brief=_planning_brief(
            phase="SPP",
            stage_key="mid_camp_build",
            days_until_fight=24,
            fatigue="high",
            readiness_flags=[],
            injuries=[],
            weight_cut_pct=0.0,
            hard_sparring_days=["Tuesday", "Thursday"],
        )
    )

    assert len(advisories) == 1
    assert advisories[0]["action"] == "deload"
    assert "risk_band" not in advisories[0]


def test_sparring_injury_state_scores_are_capped():
    entries = _sparring_injury_entries(
        {
            "injuries": ["worsening shoulder instability with constant pain and cannot move"],
        }
    )

    assert len(entries) == 1
    assert entries[0]["state_score"] == 10


def test_returns_only_one_best_advisory_when_multiple_weeks_qualify():
    advisories = build_plan_advisories(
        planning_brief=_planning_brief(
            weeks=[
                {
                    "phase": "SPP",
                    "week_index": 1,
                    "phase_week_index": 1,
                    "phase_week_total": 2,
                    "stage_key": "late_spp",
                    "declared_hard_sparring_days": ["Tuesday", "Thursday"],
                    "declared_technical_skill_days": ["Monday"],
                    "declared_training_days": ["Monday", "Tuesday", "Thursday", "Saturday"],
                    "session_roles": [],
                    "suppressed_roles": [],
                },
                {
                    "phase": "TAPER",
                    "week_index": 2,
                    "phase_week_index": 1,
                    "phase_week_total": 1,
                    "stage_key": "fight_week_survival_rhythm",
                    "declared_hard_sparring_days": ["Tuesday", "Thursday"],
                    "declared_technical_skill_days": ["Monday"],
                    "declared_training_days": ["Monday", "Tuesday", "Thursday", "Saturday"],
                    "session_roles": [],
                    "suppressed_roles": [],
                },
            ],
            days_until_fight=5,
            fatigue="high",
            readiness_flags=["fight_week", "active_weight_cut"],
            injuries=["worsening ankle instability"],
            weight_cut_pct=5.4,
        )
    )

    assert len(advisories) == 1
    assert advisories[0]["phase"] == "TAPER"
    assert advisories[0]["week_label"] == "Week 2"
    assert advisories[0]["suggestion"].startswith("If high fatigue, an aggressive cut, and worsening ankle instability are still there by Week 2")


def test_future_week_advisory_uses_conditional_static_app_wording():
    advisories = build_plan_advisories(
        planning_brief=_planning_brief(
            weeks=[
                {
                    "phase": "SPP",
                    "week_index": 2,
                    "phase_week_index": 2,
                    "phase_week_total": 4,
                    "stage_key": "late_spp",
                    "declared_hard_sparring_days": ["Tuesday", "Thursday"],
                    "declared_technical_skill_days": ["Monday"],
                    "declared_training_days": ["Monday", "Tuesday", "Thursday", "Saturday"],
                    "session_roles": [],
                    "suppressed_roles": [],
                }
            ],
            days_until_fight=18,
            fatigue="high",
            readiness_flags=["active_weight_cut"],
            injuries=["worsening ankle instability"],
            weight_cut_pct=5.4,
            hard_sparring_days=["Tuesday", "Thursday"],
        )
    )

    assert len(advisories) == 1
    advisory = advisories[0]
    assert advisory["week_label"] == "Week 2"
    assert advisory["reason"].startswith("If the current readiness picture carries into Week 2")
    assert "worsening ankle instability" in advisory["reason"]
    assert advisory["suggestion"].startswith("If high fatigue, an aggressive cut, and worsening ankle instability are still there by Week 2")


# ---------------------------------------------------------------------------
# Step 0 – Characterization tests: lock current state_score values
# ---------------------------------------------------------------------------


def test_state_score_characterization_for_representative_injury_texts():
    """Lock in current state_score outputs so the refactor cannot silently shift them."""
    cases = {
        "mild stable shoulder soreness": 2,
        "worsening ankle instability": 9,
        "severe improving shoulder tear": 4,
        "moderate worsening knee strain": 5,
        "stiffness in wrist": 2,
        "stable ankle sprain": 2,
        "improving hip tendonitis": 2,
        "mild soreness in elbow": 2,
    }
    for text, expected_score in cases.items():
        entries = _sparring_injury_entries({"injuries": [text]})
        assert len(entries) == 1, f"expected 1 entry for {text!r}"
        assert entries[0]["state_score"] == expected_score, (
            f"{text!r}: expected state_score={expected_score}, got {entries[0]['state_score']}"
        )


def test_injury_risk_characterization_multi_injury():
    entries = _sparring_injury_entries(
        {"injuries": ["worsening ankle instability", "mild stable shoulder soreness"]}
    )
    # v2: instability → red (override floor), worsening low → band_score 7, +1 multi = 8
    assert _injury_risk(entries) == 8


def test_highest_risk_entry_picks_highest_score():
    entries = _sparring_injury_entries(
        {"injuries": ["worsening ankle instability", "mild stable shoulder soreness"]}
    )
    best = _highest_risk_entry(entries)
    assert best is not None
    assert best["raw"] == "worsening ankle instability"
    assert best["state_score"] == 9


# ---------------------------------------------------------------------------
# Step 2 – V2 tiered field tests
# ---------------------------------------------------------------------------


def _entry(text: str) -> dict:
    """Return the single v2-enriched entry for a one-injury snapshot."""
    entries = _sparring_injury_entries({"injuries": [text]})
    assert len(entries) == 1
    return entries[0]


class TestSeverityTierClassification:
    def test_tear_is_high(self):
        assert _entry("shoulder tear")["severity_tier"] == "high"

    def test_severe_keyword_is_high(self):
        assert _entry("severe knee sprain")["severity_tier"] == "high"

    def test_cannot_is_high(self):
        assert _entry("cannot punch")["severity_tier"] == "high"

    def test_strain_is_moderate(self):
        assert _entry("hamstring strain")["severity_tier"] == "moderate"

    def test_sprain_is_moderate(self):
        assert _entry("ankle sprain")["severity_tier"] == "moderate"

    def test_impingement_is_moderate(self):
        assert _entry("shoulder impingement")["severity_tier"] == "moderate"

    def test_soreness_is_low(self):
        assert _entry("mild shoulder soreness")["severity_tier"] == "low"

    def test_stiffness_is_low(self):
        assert _entry("stiffness in wrist")["severity_tier"] == "low"

    def test_no_keywords_is_low(self):
        assert _entry("elbow issue")["severity_tier"] == "low"


class TestTrajectoryExclusiveState:
    def test_worsening_wins_over_improving(self):
        assert _entry("worsening but improving shoulder")["trajectory"] == "worsening"

    def test_stable(self):
        assert _entry("stable ankle sprain")["trajectory"] == "stable"

    def test_improving(self):
        assert _entry("improving hip tendonitis")["trajectory"] == "improving"

    def test_no_keywords_is_unknown(self):
        assert _entry("shoulder soreness")["trajectory"] == "unknown"


class TestOverrideFlagsDetection:
    def test_instability_detected(self):
        assert "instability" in _entry("ankle instability")["override_flags"]

    def test_daily_symptoms_detected(self):
        assert "daily_symptoms" in _entry("daily knee pain")["override_flags"]

    def test_rest_pain_detected(self):
        assert "rest_pain" in _entry("rest pain in shoulder")["override_flags"]

    def test_cannot_load_detected(self):
        assert "cannot_load" in _entry("cannot punch")["override_flags"]

    def test_giving_way_detected(self):
        assert "giving_way" in _entry("knee giving way")["override_flags"]

    def test_clean_injury_has_no_flags(self):
        assert _entry("mild shoulder soreness")["override_flags"] == []

    def test_multiple_flags(self):
        flags = _entry("rest pain daily instability")["override_flags"]
        assert "instability" in flags
        assert "daily_symptoms" in flags
        assert "rest_pain" in flags


class TestCollisionContextClassification:
    def test_knee_is_lower_limb(self):
        assert _entry("knee strain")["collision_context"] == "lower_limb"

    def test_ankle_is_lower_limb(self):
        assert _entry("ankle sprain")["collision_context"] == "lower_limb"

    def test_shoulder_is_upper_body(self):
        assert _entry("shoulder impingement")["collision_context"] == "upper_body_collision"

    def test_wrist_is_low_collision(self):
        assert _entry("stiffness in wrist")["collision_context"] == "low_collision"

    def test_elbow_is_low_collision(self):
        assert _entry("mild soreness in elbow")["collision_context"] == "low_collision"


class TestRiskBandKeyRules:
    def test_severe_worsening_is_black(self):
        assert _entry("severe worsening ankle tear")["risk_band"] == "black"

    def test_severe_improving_is_red(self):
        assert _entry("severe improving shoulder tear")["risk_band"] == "red"

    def test_severe_stable_is_red(self):
        assert _entry("severe stable knee rupture")["risk_band"] == "red"

    def test_instability_forces_minimum_red(self):
        assert _entry("ankle instability")["risk_band"] == "red"

    def test_daily_symptoms_forces_minimum_red(self):
        assert _entry("daily knee pain")["risk_band"] == "red"

    def test_moderate_worsening_is_red(self):
        assert _entry("worsening knee strain")["risk_band"] == "red"

    def test_moderate_improving_is_amber(self):
        assert _entry("improving ankle sprain")["risk_band"] == "amber"

    def test_moderate_stable_is_amber(self):
        assert _entry("stable ankle sprain")["risk_band"] == "amber"

    def test_mild_stable_high_collision_is_amber(self):
        assert _entry("mild stable shoulder soreness")["risk_band"] == "amber"

    def test_mild_stable_low_collision_is_green(self):
        assert _entry("mild soreness in elbow")["risk_band"] == "green"

    def test_mild_worsening_is_amber(self):
        assert _entry("worsening elbow stiffness")["risk_band"] == "amber"

    def test_mild_improving_is_green(self):
        assert _entry("improving wrist stiffness")["risk_band"] == "green"


class TestRiskBandScoreDerives:
    def test_green_score_range(self):
        score = _entry("mild soreness in elbow")["risk_band_score"]
        assert 0 <= score <= 2

    def test_amber_score_range(self):
        score = _entry("stable ankle sprain")["risk_band_score"]
        assert 3 <= score <= 5

    def test_red_score_range(self):
        score = _entry("severe improving shoulder tear")["risk_band_score"]
        assert 6 <= score <= 8

    def test_black_score_range(self):
        score = _entry("severe worsening ankle tear")["risk_band_score"]
        assert 9 <= score <= 10


class TestWithinBandOrdering:
    def test_highest_risk_entry_uses_secondary_order_inside_same_band(self):
        entries = _sparring_injury_entries(
            {"injuries": ["ankle instability", "severe improving shoulder tear"]}
        )

        best = _highest_risk_entry(entries)

        assert best is not None
        assert best["risk_band"] == "red"
        assert best["raw"] == "severe improving shoulder tear"

    def test_injury_risk_uses_best_secondary_score_inside_same_band(self):
        entries = _sparring_injury_entries(
            {"injuries": ["ankle instability", "severe improving shoulder tear"]}
        )

        assert _injury_risk(entries) == 8
