"""Tests for the Stage 2 -> StructuredTrainingPlan generation bridge.

Covers the pure validation/repair flow, the biometric strip, the string-load
rejection, and the prompt contract. The actual model call is exercised in
``test_stage2_automation.py``; here we test the network-free logic.
"""
from __future__ import annotations

import copy

from api.structured_plan_generation import (
    BANNED_BIOMETRIC_KEYS,
    build_structured_plan_outcome,
    build_structured_plan_prompt,
    parse_structured_json,
    strip_biometric_fields,
)
from api.structured_plan_models import SCHEMA_VERSION

# Reuse the rich valid-plan factory from the schema tests (tests/ is on sys.path).
from test_structured_plan_models import _valid_plan


def _invalid_plan() -> dict:
    """A structurally broken plan: required plan_metadata is removed."""
    broken = _valid_plan()
    broken.pop("plan_metadata")
    return broken


# --- build_structured_plan_outcome statuses --------------------------------


def test_none_input_is_not_attempted():
    outcome = build_structured_plan_outcome(None)
    assert outcome.status == "not_attempted"
    assert outcome.structured_plan is None
    assert outcome.schema_version is None


def test_valid_plan_outcome_is_valid_and_carries_schema_version():
    outcome = build_structured_plan_outcome(_valid_plan(), raw_markdown="# raw")
    assert outcome.status == "valid"
    assert outcome.schema_version == SCHEMA_VERSION
    assert isinstance(outcome.structured_plan, dict)
    assert outcome.structured_plan["schema_version"] == SCHEMA_VERSION
    # Raw markdown fallback is preserved on the structured object.
    assert outcome.structured_plan["raw_markdown_fallback"]
    assert outcome.errors == []


def test_invalid_without_repair_falls_back():
    outcome = build_structured_plan_outcome(_invalid_plan(), raw_markdown="# raw")
    assert outcome.status == "invalid_fallback_used"
    assert outcome.structured_plan is None
    assert outcome.schema_version is None
    assert outcome.errors  # validation errors recorded for admin/debug


def test_repair_retry_succeeds():
    repaired_payload = _valid_plan()
    calls: list[int] = []

    def repair_fn(_broken, _errors):
        calls.append(1)
        return repaired_payload

    outcome = build_structured_plan_outcome(
        _invalid_plan(), raw_markdown="# raw", repair_fn=repair_fn
    )
    assert len(calls) == 1  # exactly one repair attempt
    assert outcome.status == "repair_attempted_valid"
    assert outcome.schema_version == SCHEMA_VERSION
    assert isinstance(outcome.structured_plan, dict)


def test_repair_retry_still_invalid_falls_back():
    def repair_fn(_broken, _errors):
        return {"still": "broken"}

    outcome = build_structured_plan_outcome(
        _invalid_plan(), raw_markdown="# raw", repair_fn=repair_fn
    )
    assert outcome.status == "invalid_fallback_used"
    assert outcome.structured_plan is None
    assert outcome.errors


def test_repair_not_called_when_first_attempt_is_valid():
    def repair_fn(_broken, _errors):  # pragma: no cover - must not run
        raise AssertionError("repair must not run when first attempt is valid")

    outcome = build_structured_plan_outcome(_valid_plan(), repair_fn=repair_fn)
    assert outcome.status == "valid"


# --- E. machine-readable load enforcement ----------------------------------


def test_string_only_load_is_rejected():
    bad = _valid_plan()
    bad["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]["load"] = "85%"
    outcome = build_structured_plan_outcome(bad, raw_markdown="# raw")
    assert outcome.status == "invalid_fallback_used"
    assert outcome.structured_plan is None


def test_machine_readable_load_is_accepted():
    good = _valid_plan()
    good["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]["load"] = {
        "method": "percentage",
        "value": 85,
        "unit": "percent",
        "ref": "1RM",
        "display": "85% 1RM",
    }
    outcome = build_structured_plan_outcome(good, raw_markdown="# raw")
    assert outcome.status == "valid"


# --- F. fake biometric fields are not accepted / not persisted -------------


def test_biometric_fields_are_stripped_before_validation():
    plan = _valid_plan()
    today_card = plan["weeks"][0]["days"][0]["today_card"]
    today_card["hrv_score"] = 88
    today_card["whoop_recovery_score"] = 72
    plan["weeks"][0]["days"][0]["cns_recovery_percent"] = 40
    plan["strain_score"] = 14.2

    outcome = build_structured_plan_outcome(plan, raw_markdown="# raw")
    assert outcome.status == "valid"
    dumped = repr(outcome.structured_plan)
    for banned in ("hrv_score", "whoop_recovery_score", "cns_recovery_percent", "strain_score"):
        assert banned not in dumped


def test_strip_biometric_fields_reports_removed_paths_in_nested_lists():
    data = {
        "weeks": [
            {"days": [{"hrv": 50, "today_card": {"strain_score": 3}}]},
            {"days": [{"keep": True}]},
        ]
    }
    cleaned, removed = strip_biometric_fields(data)
    assert cleaned["weeks"][0]["days"][0] == {"today_card": {}}
    assert cleaned["weeks"][1]["days"][0] == {"keep": True}
    assert "weeks[0].days[0].hrv" in removed
    assert "weeks[0].days[0].today_card.strain_score" in removed


def test_all_banned_keys_are_lowercase_and_stripped_case_insensitively():
    # Guard: every constant is lowercase so the case-insensitive match works.
    assert all(key == key.lower() for key in BANNED_BIOMETRIC_KEYS)
    cleaned, removed = strip_biometric_fields({"HRV_Score": 1, "ok": 2})
    assert cleaned == {"ok": 2}
    assert removed == ["HRV_Score"]


# --- G + format. prompt contract -------------------------------------------


def test_prompt_carries_schema_and_safety_rules():
    prompt = build_structured_plan_prompt(
        plan_markdown="# Fight Camp\n- squat",
        planning_brief={"main_limiter": "conditioning"},
        event_date="2026-06-13",
    )
    # schema_version + hierarchy + machine-readable load
    assert SCHEMA_VERSION in prompt
    assert "weeks[] -> days[] -> sessions[] -> blocks[]" in prompt
    assert '"method": "percentage"' in prompt
    assert 'NEVER a string' in prompt
    # Root shape must be unambiguous: no top-level "plan" wrapper.
    assert "Do NOT wrap it inside a top-level" in prompt
    assert "StructuredTrainingPlan" in prompt
    assert "plan -> weeks[]" not in prompt
    assert '"plan": {' not in prompt
    # Every required top-level key is named so the model emits the real root.
    for top_level_key in (
        "schema_version",
        "plan_metadata",
        "athlete_context",
        "event_context",
        "countdown_labels",
        "red_flag_rules",
        "weeks",
        "daily_check_ins",
        "nutrition",
        "progression_notes",
        "raw_markdown_fallback",
    ):
        assert top_level_key in prompt
    # phases
    for phase in ("GPP", "SPP", "TAPER", "FIGHT_WEEK", "REINTEGRATION"):
        assert phase in prompt
    # self-report only / no biometrics
    assert "self-report" in prompt.lower()
    assert "WHOOP" in prompt
    # weight-cut safety: risk, not direct acute-cut instructions
    assert "weight_cut_warning" in prompt
    assert "NEVER direct acute-cut instructions" in prompt
    # raw markdown fallback + countdown labels + completion_status + mindset
    assert "raw_markdown_fallback" in prompt
    assert "countdown" in prompt.lower()
    assert "completion_status" in prompt
    assert "mindset_anchor" in prompt
    # the original plan is included for fidelity
    assert "# Fight Camp" in prompt
    assert "2026-06-13" in prompt


def test_repair_prompt_includes_errors_and_broken_json():
    prompt = build_structured_plan_prompt(
        plan_markdown="# plan",
        repair_errors=["plan_metadata: field required"],
        broken_json='{"weeks": []}',
    )
    assert "failed schema validation" in prompt
    assert "plan_metadata: field required" in prompt
    assert '{"weeks": []}' in prompt
    assert "corrected" in prompt.lower()


# --- parse_structured_json --------------------------------------------------


def test_parse_structured_json_plain_object():
    assert parse_structured_json('{"a": 1}') == {"a": 1}


def test_parse_structured_json_recovers_from_prose_wrapper():
    assert parse_structured_json('Here is the plan: {"a": 1} thanks') == {"a": 1}


def test_parse_structured_json_returns_none_on_garbage():
    assert parse_structured_json("not json at all") is None
    assert parse_structured_json("") is None


def test_parse_structured_json_ignores_trailing_prose_with_braces():
    # rfind would over-extend to the stray closing brace in the trailing prose.
    text = 'Plan: {"a": 1} -- done (see notes }below)'
    assert parse_structured_json(text) == {"a": 1}


def test_parse_structured_json_handles_code_fence_and_braces_in_strings():
    text = '```json\n{"display": "85% {1RM}", "value": 85}\n```'
    assert parse_structured_json(text) == {"display": "85% {1RM}", "value": 85}
