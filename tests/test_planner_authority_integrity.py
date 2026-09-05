from fightcamp.planner_authority_integrity import planner_authority_findings
from fightcamp.stage2_pipeline import review_stage2_output
from fightcamp.stage2_policy import apply_stage2_release_policy


def _brief(
    *,
    name: str,
    slot_group: str,
    d_day: int,
    week_phase: str,
    category: str,
    source_phase: str,
    loaded_allowed: bool = True,
    phase_days: dict[str, int] | None = None,
) -> dict:
    return {
        "athlete_snapshot": {
            "phase_weeks": {
                "days": phase_days or {"GPP": 19, "SPP": 2, "TAPER": 5},
            }
        },
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": week_phase,
                    "session_roles": [
                        {
                            "role_key": "test_role",
                            "category": category,
                            "scheduled_countdown_label": f"D-{d_day}",
                            "selected_exercise_assignments": [
                                {
                                    "name": name,
                                    "slot_group": slot_group,
                                    "source_phase": source_phase,
                                }
                            ],
                            "effective_strength_envelope": {
                                "loaded_allowed": loaded_allowed,
                            },
                        }
                    ],
                }
            ]
        },
    }


def _codes(brief: dict) -> set[str]:
    return {item["code"] for item in planner_authority_findings(brief)}


def test_gpp_only_hang_power_clean_is_blocked_on_stage1_spp_day() -> None:
    brief = _brief(
        name="Hang Power Clean",
        slot_group="strength_slots",
        d_day=7,
        week_phase="SPP",
        category="strength",
        source_phase="GPP",
    )

    findings = planner_authority_findings(brief)

    assert {item["code"] for item in findings} == {"selected_exercise_phase_ineligible"}
    assert findings[0]["scheduled_phase"] == "SPP"
    assert findings[0]["allowed_phases"] == ["GPP"]


def test_multiphase_back_squat_remains_legal_when_spp_is_in_bank_phases() -> None:
    brief = _brief(
        name="Back Squat",
        slot_group="strength_slots",
        d_day=7,
        week_phase="SPP",
        category="strength",
        # Source provenance is deliberately stale: original bank metadata and
        # scheduled Stage 1 phase decide legality, not this downstream stamp.
        source_phase="GPP",
    )

    assert "selected_exercise_phase_ineligible" not in _codes(brief)


def test_gpp_only_broad_jump_conditioning_is_blocked_on_taper_day() -> None:
    brief = _brief(
        name="Broad Jump Repeats",
        slot_group="conditioning_slots",
        d_day=2,
        week_phase="TAPER",
        category="conditioning",
        source_phase="GPP",
    )

    assert "selected_exercise_phase_ineligible" in _codes(brief)


def test_dated_role_fails_closed_when_stage1_phase_cannot_be_resolved() -> None:
    brief = _brief(
        name="Back Squat",
        slot_group="strength_slots",
        d_day=7,
        week_phase="SPP",
        category="strength",
        source_phase="SPP",
        phase_days={"GPP": 0, "SPP": 0, "TAPER": 0},
    )

    # The stale week/source phase must not rescue an unresolved Stage 1 mapping.
    assert _codes(brief) == {"selected_exercise_phase_unresolved"}


def test_loaded_strength_is_blocked_when_effective_envelope_forbids_loading() -> None:
    brief = _brief(
        name="Hang Power Clean",
        slot_group="strength_slots",
        d_day=20,
        week_phase="GPP",
        category="strength",
        source_phase="GPP",
        loaded_allowed=False,
    )

    assert "selected_loaded_exercise_forbidden" in _codes(brief)
    assert "selected_exercise_phase_ineligible" not in _codes(brief)


def test_review_pipeline_holds_phase_illegal_selected_assignment() -> None:
    brief = _brief(
        name="Hang Power Clean",
        slot_group="strength_slots",
        d_day=7,
        week_phase="SPP",
        category="strength",
        source_phase="GPP",
    )

    review = review_stage2_output(
        planning_brief=brief,
        final_plan_text="D-7 (Monday) — Neural Primer\nHang Power Clean — 2 x 8 @ RPE 6",
    )
    report = review["validator_report"]

    assert report["release_decision"] == "hold"
    assert report["is_athlete_releasable"] is False
    assert report["planner_authority_integrity_hold"] is True
    assert any(
        item.get("code") == "selected_exercise_phase_ineligible"
        for item in report.get("errors", [])
        if isinstance(item, dict)
    )


def test_planner_authority_blocker_forces_hold() -> None:
    report = apply_stage2_release_policy(
        {
            "errors": [
                {
                    "code": "selected_exercise_phase_ineligible",
                    "exercise": "Hang Power Clean",
                    "countdown_label": "D-7",
                    "severity": "blocker",
                }
            ],
            "warnings": [],
            "blocking_warnings": [],
            "review_flags": [],
        }
    )

    assert report["release_decision"] == "hold"
    assert report["is_athlete_releasable"] is False
    assert report["is_publishable"] is False
    assert report["planner_authority_integrity_hold"] is True


def test_unresolved_stage1_phase_blocker_forces_hold() -> None:
    report = apply_stage2_release_policy(
        {
            "errors": [
                {
                    "code": "selected_exercise_phase_unresolved",
                    "exercise": "Back Squat",
                    "countdown_label": "D-7",
                    "severity": "blocker",
                }
            ],
            "warnings": [],
            "blocking_warnings": [],
            "review_flags": [],
        }
    )

    assert report["release_decision"] == "hold"
    assert report["planner_authority_integrity_hold"] is True


def test_ordinary_validator_findings_keep_existing_non_blocking_release_policy() -> None:
    report = apply_stage2_release_policy(
        {
            "errors": [{"code": "restriction_violation", "severity": "blocker"}],
            "warnings": [],
            "blocking_warnings": [],
            "review_flags": [],
        }
    )

    assert report["release_decision"] == "publish_with_flags"
    assert report["is_athlete_releasable"] is True
    assert report.get("planner_authority_integrity_hold") is not True
