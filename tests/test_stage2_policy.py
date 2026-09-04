from __future__ import annotations

import json

import pytest

from fightcamp import stage2_policy


def _raw_policy() -> dict:
    return json.loads(stage2_policy._POLICY_PATH.read_text(encoding="utf-8"))


def test_hard_stage2_blocker_codes_load_from_shared_json() -> None:
    assert stage2_policy.HARD_STAGE2_BLOCKER_CODES == frozenset(
        _raw_policy()["hard_stage2_blocker_codes"]
    )


def test_goal_preservation_failure_is_always_hard_blocking() -> None:
    assert "goal_preservation_failed" in stage2_policy.HARD_STAGE2_BLOCKER_CODES
    for field in ("errors", "warnings", "review_flags", "blocking_warnings"):
        report = {"errors": [], "warnings": [], "review_flags": [], "blocking_warnings": []}
        report[field] = [{"code": "goal_preservation_failed", "goal": "speed"}]
        decided = stage2_policy.apply_stage2_release_policy(report)
        assert decided["release_decision"] == "hold", field
        assert decided["is_athlete_releasable"] is False, field


def test_late_fight_illegal_exercise_codes_are_hard_not_card_rescuable() -> None:
    illegal_exercise_codes = {
        "late_fight_countdown_blocked_drill",
        "late_fight_window_forbidden_exercise",
    }

    assert illegal_exercise_codes.issubset(stage2_policy.HARD_STAGE2_BLOCKER_CODES)
    assert not illegal_exercise_codes & stage2_policy.CARD_RESCUABLE_SOFT_CODES


def test_late_fight_unapproved_exercise_rendered_is_soft_not_hard_blocker() -> None:
    # Rendering an exercise outside a countdown day's curated allowlist is a
    # soft review flag, not a hard blocker: it must not hold the plan (the
    # dangerous cases are still caught by countdown_blocked_drill /
    # window_forbidden_exercise / hard_sparring_violation).
    assert "late_fight_unapproved_exercise_rendered" not in stage2_policy.HARD_STAGE2_BLOCKER_CODES
    assert "late_fight_unapproved_exercise_rendered" in stage2_policy.CARD_RESCUABLE_SOFT_CODES
    assert not stage2_policy.is_hard_stage2_blocker("late_fight_unapproved_exercise_rendered")


def test_release_policy_classes_load_from_shared_json_and_are_disjoint() -> None:
    assert stage2_policy.ATHLETE_RELEASE_WITH_FLAGS_CODES == frozenset(
        _raw_policy()["athlete_release_with_flags_codes"]
    )
    assert stage2_policy.ADMIN_REVIEW_BLOCKING_CODES == frozenset(
        _raw_policy()["admin_review_blocking_codes"]
    )
    assert not stage2_policy.HARD_STAGE2_BLOCKER_CODES & stage2_policy.ATHLETE_RELEASE_WITH_FLAGS_CODES
    assert not stage2_policy.HARD_STAGE2_BLOCKER_CODES & stage2_policy.ADMIN_REVIEW_BLOCKING_CODES
    assert not stage2_policy.ATHLETE_RELEASE_WITH_FLAGS_CODES & stage2_policy.ADMIN_REVIEW_BLOCKING_CODES


def test_hard_blocker_findings_returns_only_hard_blockers() -> None:
    report = {
        "errors": [
            {"code": "restriction_violation"},
            {"code": "true_internal_system_leak"},
            "not-a-dict",
        ],
        "blocking_warnings": [
            {"code": "calendar_spine_fight_day_protocol_violation"},
            {"code": "missing_required_element"},
        ],
        "warnings": [{"code": "late_fight_hard_sparring_violation"}],
    }

    assert stage2_policy.hard_blocker_findings(report) == [
        {"code": "restriction_violation"},
        {"code": "calendar_spine_fight_day_protocol_violation"},
    ]


def test_prompt_safe_validator_report_excludes_soft_findings_and_review_flags() -> None:
    report = {
        "errors": [
            {"code": "restriction_violation", "line": "Push Press"},
            {"code": "true_internal_system_leak"},
        ],
        "blocking_warnings": [
            {"code": "missing_required_element"},
            {"code": "stage2_output_truncated"},
        ],
        "warnings": [{"code": "generic_filler_phrase"}],
        "review_flags": [{"code": "sport_language_leak"}],
        "restricted_hits": [{"restriction": "heavy_overhead_pressing", "line": "Push Press"}],
    }

    assert stage2_policy.prompt_safe_validator_report(report) == {
        "errors": [{"code": "restriction_violation", "line": "Push Press"}],
        "warnings": [{"code": "missing_required_element"}],
        "blocking_warnings": [
            {"code": "stage2_output_truncated"},
            {"code": "missing_required_element"},
        ],
        "missing_required_elements": [],
        "restricted_hits": [
            {"restriction": "heavy_overhead_pressing", "line": "Push Press"}
        ],
    }


def test_prompt_safe_validator_report_omits_restricted_hits_without_restriction_violation() -> None:
    report = {
        "errors": [{"code": "stage2_output_empty"}],
        "restricted_hits": [{"restriction": "heavy_overhead_pressing", "line": "Push Press"}],
    }

    assert stage2_policy.prompt_safe_validator_report(report)["restricted_hits"] == []


def test_prompt_safe_validator_report_keeps_restricted_hits_for_normalized_restriction_code() -> None:
    report = {
        "errors": [{"code": " restriction_violation "}],
        "restricted_hits": [{"restriction": "heavy_overhead_pressing", "line": "Push Press"}],
    }

    assert stage2_policy.prompt_safe_validator_report(report)["restricted_hits"] == [
        {"restriction": "heavy_overhead_pressing", "line": "Push Press"}
    ]


def test_policy_findings_dedupe_warning_sources() -> None:
    report = {
        "warnings": [{"code": "option_overload", "phase": "SPP"}],
        "review_flags": [{"code": "option_overload", "phase": "SPP"}],
        "blocking_warnings": [{"code": "missing_required_element", "phase": "SPP"}],
    }

    assert stage2_policy.athlete_release_with_flags_findings(report) == [
        {"code": "option_overload", "phase": "SPP"}
    ]
    assert stage2_policy.admin_review_blocking_findings(report) == [
        {"code": "missing_required_element", "phase": "SPP"}
    ]


@pytest.mark.parametrize("code", sorted(stage2_policy.ATHLETE_RELEASE_WITH_FLAGS_CODES))
def test_low_risk_quality_code_releases_with_flags(code: str) -> None:
    report = stage2_policy.apply_stage2_release_policy(
        {
            "errors": [],
            "warnings": [{"code": code}],
            "review_flags": [{"code": code}],
            "blocking_warnings": [{"code": code}],
        }
    )

    assert report["release_decision"] == "publish_with_flags"
    assert report["is_athlete_releasable"] is True
    assert report["is_publishable"] is True
    assert report["blocking_warnings"] == []
    assert report["quality_review_flags"] == [{"code": code}]


@pytest.mark.parametrize("code", sorted(stage2_policy.ADMIN_REVIEW_BLOCKING_CODES))
def test_context_or_programme_failure_holds(code: str) -> None:
    report = stage2_policy.apply_stage2_release_policy(
        {"errors": [], "warnings": [{"code": code}], "blocking_warnings": []}
    )

    assert report["release_decision"] == "hold"
    assert report["is_athlete_releasable"] is False
    assert report["is_publishable"] is False
    assert report["admin_review_blocking_flags"] == [{"code": code}]


def test_mixed_release_and_blocking_codes_hold() -> None:
    report = stage2_policy.apply_stage2_release_policy(
        {
            "errors": [],
            "warnings": [
                {"code": "option_overload"},
                {"code": "missing_required_element"},
            ],
            "blocking_warnings": [],
        }
    )

    assert report["release_decision"] == "hold"
    assert report["is_publishable"] is False
    assert report["quality_review_flags"] == [{"code": "option_overload"}]
    assert report["admin_review_blocking_flags"] == [{"code": "missing_required_element"}]


def test_unknown_blocking_code_fails_closed() -> None:
    report = stage2_policy.apply_stage2_release_policy(
        {
            "errors": [],
            "warnings": [],
            "review_flags": [],
            "blocking_warnings": [{"code": "brand_new_warning_code"}],
        }
    )

    assert report["release_decision"] == "hold"
    assert report["is_athlete_releasable"] is False
    assert report["is_publishable"] is False


@pytest.mark.parametrize(
    "field",
    ["errors", "warnings", "review_flags", "blocking_warnings"],
)
@pytest.mark.parametrize(
    "malformed_value",
    [
        pytest.param({"code": "restriction_violation"}, id="dict"),
        pytest.param("not-a-list", id="string"),
        pytest.param(object(), id="object"),
    ],
)
def test_malformed_release_collection_fails_closed(
    field: str,
    malformed_value: object,
) -> None:
    validator_report: dict[str, object] = {
        "errors": [],
        "warnings": [],
        "review_flags": [],
        "blocking_warnings": [],
    }
    validator_report[field] = malformed_value

    report = stage2_policy.apply_stage2_release_policy(validator_report)

    assert report["release_policy_malformed_fields"] == [field]
    assert report["release_decision"] == "hold"
    assert report["is_athlete_releasable"] is False
    assert report["is_publishable"] is False


def test_plan_mapper_keeps_malformed_review_required_report_held() -> None:
    from api.plan_mappers import _map_plan_summary

    summary = _map_plan_summary(
        {
            "id": "plan-1",
            "athlete_id": "athlete-1",
            "status": "review_required",
            "stage2_validator_report": {
                "errors": [],
                "warnings": [],
                "review_flags": [],
                "blocking_warnings": {"code": "restriction_violation"},
            },
            "technical_style": [],
        }
    )

    assert summary.status == "held_for_review"
    assert summary.review_reason is not None


def test_release_status_matches_validator_publishability() -> None:
    report = stage2_policy.apply_stage2_release_policy(
        {
            "errors": [],
            "warnings": [{"code": "template_like_session_render"}],
            "blocking_warnings": [],
        }
    )

    assert report["release_decision"] == "publish_with_flags"
    assert report["is_publishable"] is True
    assert report["is_athlete_releasable"] is True


def test_required_athlete_context_failures_are_admin_blocking() -> None:
    required_blockers = {
        "high_pressure_weight_cut_underaddressed",
        "weight_cut_state_contradiction",
        "missing_weight_cut_acknowledgement",
        "missing_injury_lead_summary",
        "missing_required_element",
        "equipment_incongruent_selection",
        "unresolved_access_fallback",
        "late_camp_session_incomplete",
        "weekly_session_overage",
        "support_recovery_day_stress_leak",
    }

    assert required_blockers.issubset(stage2_policy.ADMIN_REVIEW_BLOCKING_CODES)
    assert not required_blockers & stage2_policy.ATHLETE_RELEASE_WITH_FLAGS_CODES
