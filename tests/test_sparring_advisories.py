from fightcamp.sparring_advisories import _sparring_injury_entries, build_plan_advisories


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
    assert advisory["replacement"] == "Technical rounds with stance-stable pad or bag work."
    assert "worsening ankle instability" in advisory["reason"]


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
