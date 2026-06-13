"""Tests for the Stage 2 -> StructuredTrainingPlan generation bridge.

Covers the pure validation/repair flow, the biometric strip, the conservative
normalizer, and the prompt contract. The actual model call is exercised in
``test_stage2_automation.py``; here we test the network-free logic.
"""
from __future__ import annotations

import copy

from api.structured_plan_generation import (
    BANNED_BIOMETRIC_KEYS,
    build_structured_plan_outcome,
    build_structured_plan_prompt,
    normalize_structured_plan_candidate,
    parse_structured_json,
    strip_biometric_fields,
)
from api.structured_plan_models import SCHEMA_VERSION, validate_structured_plan

# Reuse the rich valid-plan factory from the schema tests (tests/ is on sys.path).
from test_structured_plan_models import _valid_plan


def _invalid_plan():
    """A payload the conservative normalizer cannot salvage.

    The normalizer fills structural defaults for any *dict*, so an unrecoverable
    candidate must be a non-object (here a list). This keeps the repair/fallback
    paths exercisable.
    """
    return ["not", "a", "structured", "plan"]


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
        return ["still", "broken"]  # non-object: normalizer can't salvage it

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


def test_string_only_load_is_normalized_to_object():
    plan = _valid_plan()
    plan["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]["load"] = "85%"
    outcome = build_structured_plan_outcome(plan, raw_markdown="# raw")
    assert outcome.status == "valid"
    load = outcome.structured_plan["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]["load"]
    assert load["method"] == "percentage"
    assert load["value"] == 85
    assert load["unit"] == "percent"


def test_unparseable_string_load_becomes_null():
    plan = _valid_plan()
    plan["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]["load"] = "as hard as possible"
    outcome = build_structured_plan_outcome(plan, raw_markdown="# raw")
    assert outcome.status == "valid"
    assert (
        outcome.structured_plan["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]["load"]
        is None
    )


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
    # source-of-truth + no-invention guardrails
    assert "SOURCE OF TRUTH" in prompt
    assert "Do NOT invent" in prompt
    # exact root skeleton with the nested objects that were failing live
    assert "EXACT ROOT SKELETON" in prompt
    for skeleton_marker in (
        '"load_focus"',
        '"progression"',
        '"today_card"',
        '"mindset_anchor"',
        '"blocks"',
        '"daily_check_ins": []',
        '"weight_cut_warning"',
    ):
        assert skeleton_marker in prompt


def test_repair_prompt_instructs_shape_only_fix_and_includes_skeleton():
    prompt = build_structured_plan_prompt(
        plan_markdown="# plan",
        repair_errors=["weeks.0.load_focus: field required"],
        broken_json='{"weeks": [{}]}',
    )
    assert "Fix ONLY the JSON structure" in prompt
    assert "Do NOT change the training content." in prompt
    # The repair prompt still carries the exact skeleton to anchor the shape.
    assert "EXACT ROOT SKELETON" in prompt


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


# --- normalize_structured_plan_candidate (conservative shape fixes) ----------


def _live_malformed_plan() -> dict:
    """A plan in the right shape but with the validation failures seen live."""
    return {
        # schema_version missing entirely
        "plan_metadata": {"title": "Camp"},  # missing sport/plan_type/timezone/status
        "athlete_context": {},  # missing sport_profile
        "event_context": {"event_type": "boxing_match"},  # invalid enum
        "countdown_labels": ["D-28", "D0", "D+1"],  # strings, not objects
        "red_flag_rules": [{"display_text": "Stop if dizzy"}],  # missing required fields
        "weeks": [
            {
                "phase_label": "spp",  # wrong case
                "days": [
                    {
                        "day_type": "HARD",  # invalid enum
                        "today_card": {"headline": "Go"},  # missing readiness/mindset
                        "sessions": [
                            {
                                "session_type": "strength",  # alias -> strength_power
                                "blocks": [
                                    {
                                        "block_type": "warmup",  # alias -> preparation
                                        "display_name": "Skips",
                                        "load": "85%",  # string -> object
                                        "rest": "90s",  # string -> object
                                        "duration": "45 min",  # string -> object
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
        "daily_check_ins": None,  # not a list
        "nutrition": {"summary": "Eat well"},  # incomplete
        "progression_notes": ["note one", "note two"],  # list, not string
        "raw_markdown_fallback": "# Plan\nThe real plan text.",
    }


def test_normalize_recovers_live_style_malformed_plan():
    outcome = build_structured_plan_outcome(_live_malformed_plan(), raw_markdown="# raw")
    assert outcome.status == "valid"
    # The normalized object still validates strictly against the schema.
    validate_structured_plan(outcome.structured_plan)


def test_normalize_fills_missing_plan_metadata_fields():
    plan = normalize_structured_plan_candidate({"plan_metadata": {"title": "Camp"}})
    meta = plan["plan_metadata"]
    assert meta["plan_type"] in {
        "fight_camp",
        "explosive_athlete",
        "match_week",
        "reintegration",
        "general_performance",
    }
    assert meta["status"] == "active"
    assert meta["timezone"] == "UTC"
    assert isinstance(meta["sport"], str)
    assert plan["athlete_context"]["sport_profile"] == ""


def test_normalize_invalid_event_type_maps_to_none():
    plan = normalize_structured_plan_candidate(
        {"event_context": {"event_type": "boxing_match", "fight_date": "2026-06-13"}}
    )
    assert plan["event_context"]["event_type"] == "none"
    # A valid event_type is preserved untouched.
    plan2 = normalize_structured_plan_candidate({"event_context": {"event_type": "fight"}})
    assert plan2["event_context"]["event_type"] == "fight"


def test_normalize_countdown_label_strings_become_objects():
    plan = normalize_structured_plan_candidate({"countdown_labels": ["D-28", "D0", "D+1"]})
    labels = plan["countdown_labels"]
    assert labels[0] == {"date": "", "days_to_event": 28, "label": "D-28", "anchor": "event_countdown"}
    assert labels[1]["days_to_event"] == 0
    assert labels[2]["days_to_event"] == -1


def test_normalize_red_flag_rules_get_required_fields():
    plan = normalize_structured_plan_candidate(
        {"red_flag_rules": [{"display_text": "Stop if dizzy"}]}
    )
    rule = plan["red_flag_rules"][0]
    assert rule["rule_id"]
    assert rule["when"] == "morning_check_in"
    assert rule["severity"] == "amber"
    assert rule["action"] == ""


def test_normalize_session_and_block_type_aliases():
    plan = normalize_structured_plan_candidate(
        {
            "weeks": [
                {
                    "days": [
                        {
                            "sessions": [
                                {
                                    "session_type": "strength",
                                    "blocks": [
                                        {"block_type": "warmup", "display_name": "Skips"},
                                        {"block_type": "made_up", "display_name": "Mystery"},
                                    ],
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    )
    session = plan["weeks"][0]["days"][0]["sessions"][0]
    assert session["session_type"] == "strength_power"
    assert session["blocks"][0]["block_type"] == "preparation"
    assert session["blocks"][1]["block_type"] == "accessory"  # unknown -> accessory


def test_normalize_rest_duration_strings_become_objects():
    plan = normalize_structured_plan_candidate(
        {
            "weeks": [
                {
                    "days": [
                        {
                            "sessions": [
                                {
                                    "blocks": [
                                        {"rest": "90s", "duration": "2 min"},
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    )
    block = plan["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]
    assert block["rest"] == {"value": 90.0, "unit": "seconds"}
    assert block["duration"] == {"value": 2.0, "unit": "minutes"}


def test_normalize_daily_check_ins_non_list_becomes_empty_list():
    assert normalize_structured_plan_candidate({"daily_check_ins": None})["daily_check_ins"] == []
    assert normalize_structured_plan_candidate({"daily_check_ins": {"x": 1}})["daily_check_ins"] == []


def test_normalize_incomplete_nutrition_gets_structural_defaults():
    nutrition = normalize_structured_plan_candidate({"nutrition": {"summary": "Eat well"}})["nutrition"]
    for key in ("summary", "daily_focus", "training_day_guidance", "fight_week_guidance"):
        assert isinstance(nutrition[key], str)
    assert nutrition["summary"] == "Eat well"


def test_normalize_progression_notes_coerced_to_string():
    assert normalize_structured_plan_candidate({"progression_notes": ["a", "b"]})["progression_notes"] == "a b"
    assert normalize_structured_plan_candidate({"progression_notes": None})["progression_notes"] == ""
    assert normalize_structured_plan_candidate({"progression_notes": {"x": 1}})["progression_notes"] == ""


def test_normalize_preserves_raw_markdown_fallback_and_does_not_invent_content():
    plan = normalize_structured_plan_candidate(_live_malformed_plan())
    assert plan["raw_markdown_fallback"] == "# Plan\nThe real plan text."
    # No weeks/sessions/blocks were invented beyond what the input contained.
    assert len(plan["weeks"]) == 1
    assert len(plan["weeks"][0]["days"][0]["sessions"][0]["blocks"]) == 1


def test_normalize_leaves_non_dict_untouched_so_schema_can_reject():
    # Fallback safety: a non-object payload is not salvageable and must stay invalid.
    assert normalize_structured_plan_candidate(["not", "a", "plan"]) == ["not", "a", "plan"]
    outcome = build_structured_plan_outcome(["not", "a", "plan"], raw_markdown="# raw")
    assert outcome.status == "invalid_fallback_used"
    assert outcome.structured_plan is None
