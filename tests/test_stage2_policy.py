from __future__ import annotations

import json
from pathlib import Path

from api import stage2_automation
from fightcamp import stage2_policy


def _raw_policy() -> dict:
    policy_path = Path(__file__).resolve().parents[1] / "shared" / "stage2-policy.json"
    return json.loads(policy_path.read_text(encoding="utf-8"))


def test_hard_stage2_blocker_codes_load_from_shared_json() -> None:
    assert stage2_policy.HARD_STAGE2_BLOCKER_CODES == frozenset(
        _raw_policy()["hard_stage2_blocker_codes"]
    )


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
        "blocking_warnings": [{"code": "stage2_output_truncated"}],
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


def test_stage2_hold_rescue_uses_shared_soft_code_list() -> None:
    shared_soft_code = next(iter(stage2_policy.CARD_RESCUABLE_SOFT_CODES))

    assert stage2_automation._stage2_hold_is_card_rescuable(
        {"errors": [{"code": shared_soft_code}], "blocking_warnings": []}
    )
    assert not stage2_automation._stage2_hold_is_card_rescuable(
        {"errors": [{"code": "unknown_future_soft_code"}], "blocking_warnings": []}
    )
