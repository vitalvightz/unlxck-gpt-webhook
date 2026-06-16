"""Tests for the Stage 2 -> StructuredTrainingPlan generation bridge.

Covers the pure validation/repair flow, the biometric strip, the conservative
normalizer, and the prompt contract. The actual model call is exercised in
``test_stage2_automation.py``; here we test the network-free logic.
"""
from __future__ import annotations

import json
from pathlib import Path

from api.structured_plan_generation import (
    BANNED_BIOMETRIC_KEYS,
    _normalize_daily_check_ins,
    _normalize_load,
    _normalize_measured,
    bank_conditioning_to_block,
    bank_strength_to_block,
    build_structured_plan_outcome,
    build_structured_plan_prompt,
    normalize_structured_plan_candidate,
    parse_bank_prescription,
    parse_structured_json,
    should_attempt_structured_plan,
    strip_biometric_fields,
)
from api.structured_plan_models import (
    SCHEMA_VERSION,
    Nutrition,
    SessionBlock,
    validate_structured_plan,
)

# Reuse the rich valid-plan factory from the schema tests (tests/ is on sys.path).
from test_structured_plan_models import _valid_plan

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _first_bank_entry(filename: str) -> dict:
    data = json.loads((_DATA_DIR / filename).read_text(encoding="utf-8"))
    entries = data if isinstance(data, list) else (data.get("items") or data.get("data"))
    return entries[0]


def _invalid_plan():
    """A payload the conservative normalizer cannot salvage.

    The normalizer fills structural defaults for any *dict*, so an unrecoverable
    candidate must be a non-object (here a list). This keeps the repair/fallback
    paths exercisable.
    """
    return ["not", "a", "structured", "plan"]


def _faithful_source(plan: dict) -> str:
    """Markdown faithful to ``plan`` so the faithfulness gate passes.

    The faithfulness gate (part of ``build_structured_plan_outcome``) rejects a
    countdown-claiming card whose source text has no D-day marker. Tests that
    exercise the *outcome machinery* (validation, repair, load normalization,
    biometric stripping, check-in tolerance) still need a faithful source, so
    derive one from the plan: emit each week's countdown bounds and, per day, a
    D-day header followed by every exercise block's display name.
    """
    lines = ["# FIGHT CAMP PLAN", ""]
    for week in plan.get("weeks") or []:
        lines.append(
            f"## Week — SPP ({week.get('countdown_start')} to {week.get('countdown_end')})"
        )
        lines.append("")
        for day in week.get("days") or []:
            label = day.get("countdown_label") or ""
            lines.append(f"### Day ({label}) — Session")
            for session in day.get("sessions") or []:
                for block in session.get("blocks") or []:
                    name = block.get("display_name")
                    if name:
                        lines.append(f"- {name}")
            lines.append("")
    return "\n".join(lines)


# --- build_structured_plan_outcome statuses --------------------------------


def test_none_input_is_not_attempted():
    outcome = build_structured_plan_outcome(None)
    assert outcome.status == "not_attempted"
    assert outcome.structured_plan is None
    assert outcome.schema_version is None


def test_valid_plan_outcome_is_valid_and_carries_schema_version():
    plan = _valid_plan()
    outcome = build_structured_plan_outcome(plan, raw_markdown=_faithful_source(plan))
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
        _invalid_plan(),
        raw_markdown=_faithful_source(repaired_payload),
        repair_fn=repair_fn,
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

    plan = _valid_plan()
    outcome = build_structured_plan_outcome(
        plan, raw_markdown=_faithful_source(plan), repair_fn=repair_fn
    )
    assert outcome.status == "valid"


# --- E. machine-readable load enforcement ----------------------------------


def test_string_only_load_is_normalized_to_object():
    plan = _valid_plan()
    plan["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]["load"] = "85%"
    outcome = build_structured_plan_outcome(plan, raw_markdown=_faithful_source(plan))
    assert outcome.status == "valid"
    load = outcome.structured_plan["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]["load"]
    assert load["method"] == "percentage"
    assert load["value"] == 85
    assert load["unit"] == "percent"


def test_unparseable_string_load_becomes_null():
    plan = _valid_plan()
    plan["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]["load"] = "as hard as possible"
    outcome = build_structured_plan_outcome(plan, raw_markdown=_faithful_source(plan))
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
    outcome = build_structured_plan_outcome(good, raw_markdown=_faithful_source(good))
    assert outcome.status == "valid"


# --- F. fake biometric fields are not accepted / not persisted -------------


def test_biometric_fields_are_stripped_before_validation():
    plan = _valid_plan()
    today_card = plan["weeks"][0]["days"][0]["today_card"]
    today_card["hrv_score"] = 88
    today_card["whoop_recovery_score"] = 72
    plan["weeks"][0]["days"][0]["cns_recovery_percent"] = 40
    plan["strain_score"] = 14.2

    outcome = build_structured_plan_outcome(plan, raw_markdown=_faithful_source(plan))
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


def test_normalize_plan_notes_coerces_category_and_drops_empty():
    plan = normalize_structured_plan_candidate(
        {
            "plan_notes": [
                {"category": "Weight_Cut", "label": "Active cut", "text": "~5.7% target."},
                {"category": "bogus", "text": "Stay disciplined."},  # unknown -> general
                {"category": "injury", "text": "   "},  # empty text -> dropped
                "Keep the wound covered.",  # bare string -> general note
                123,  # non-note -> dropped
            ]
        }
    )
    notes = plan["plan_notes"]
    assert [n["category"] for n in notes] == ["weight_cut", "general", "general"]
    assert notes[0] == {"category": "weight_cut", "label": "Active cut", "text": "~5.7% target."}
    assert notes[2]["text"] == "Keep the wound covered."
    # The normalized plan still validates strictly against the schema.
    validate_structured_plan(normalize_structured_plan_candidate({"plan_notes": notes}))


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


# --- _normalize_measured: per-field default units ----------------------------


def test_normalize_measured_uses_default_unit_for_bare_numbers():
    assert _normalize_measured(90, "seconds") == {"value": 90.0, "unit": "seconds"}
    assert _normalize_measured(45, "minutes") == {"value": 45.0, "unit": "minutes"}
    assert _normalize_measured(400, "meters") == {"value": 400.0, "unit": "meters"}


def test_normalize_measured_parses_plain_numeric_strings_with_default_unit():
    assert _normalize_measured("90", "seconds") == {"value": 90.0, "unit": "seconds"}
    assert _normalize_measured("2.5", "minutes") == {"value": 2.5, "unit": "minutes"}


def test_normalize_measured_unit_is_dimension_aware():
    # "m" is minutes in a time field but meters in a distance field.
    assert _normalize_measured("5 m", "minutes") == {"value": 5.0, "unit": "minutes"}
    assert _normalize_measured("5 m", "meters") == {"value": 5.0, "unit": "meters"}
    assert _normalize_measured("90s", "seconds") == {"value": 90.0, "unit": "seconds"}


def test_normalize_measured_unparseable_returns_none():
    assert _normalize_measured("as long as needed", "seconds") is None
    assert _normalize_measured("", "seconds") is None
    assert _normalize_measured(None, "seconds") is None


def test_block_measured_defaults_follow_bank_conventions():
    block = normalize_structured_plan_candidate(
        {
            "weeks": [
                {
                    "days": [
                        {
                            "sessions": [
                                {
                                    "blocks": [
                                        {"work": 30, "rest": 90, "duration": 12, "distance": 400}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    )["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]
    assert block["work"] == {"value": 30.0, "unit": "seconds"}
    assert block["rest"] == {"value": 90.0, "unit": "seconds"}
    assert block["duration"] == {"value": 12.0, "unit": "minutes"}
    assert block["distance"] == {"value": 400.0, "unit": "meters"}


# --- _normalize_load: percentage + optional trailing ref ---------------------


def test_normalize_load_captures_trailing_ref():
    assert _normalize_load("85% 1RM") == {
        "method": "percentage",
        "value": 85.0,
        "unit": "percent",
        "display": "85% 1RM",
        "ref": "1RM",
    }


def test_normalize_load_captures_of_ref():
    load = _normalize_load("85% of 1RM")
    assert load["ref"] == "1RM"
    assert load["value"] == 85.0


def test_normalize_load_range_takes_top_value_with_ref():
    # Bank prescriptions read like "75-85% 1RM"; take the working top end.
    load = _normalize_load("75-85% 1RM")
    assert load["value"] == 85.0
    assert load["ref"] == "1RM"


def test_normalize_load_percent_without_ref_has_no_ref_key():
    load = _normalize_load("85%")
    assert load["method"] == "percentage"
    assert load["value"] == 85.0
    assert "ref" not in load  # group(2) was None and must not be used


def test_normalize_load_bodyweight_and_unparseable():
    assert _normalize_load("bodyweight")["method"] == "bodyweight"
    assert _normalize_load("as hard as possible") is None


# --- weight_cut_warning as a plain string ------------------------------------


def test_normalize_weight_cut_warning_string_is_wrapped():
    nutrition = normalize_structured_plan_candidate(
        {"nutrition": {"weight_cut_warning": "Cut 4% under qualified supervision."}}
    )["nutrition"]
    warning = nutrition["weight_cut_warning"]
    assert warning["risk_level"] == "none"
    assert warning["display_text"] == "Cut 4% under qualified supervision."
    assert warning["requires_professional_support"] is False
    # The wrapped object validates as part of the Nutrition schema.
    Nutrition.model_validate(nutrition)


def test_normalize_weight_cut_warning_empty_string_becomes_none():
    nutrition = normalize_structured_plan_candidate(
        {"nutrition": {"weight_cut_warning": "   "}}
    )["nutrition"]
    assert nutrition["weight_cut_warning"] is None


# --- bank -> StructuredTrainingPlan adapters ---------------------------------


def test_parse_bank_prescription_extracts_sets_reps_load():
    parsed = parse_bank_prescription("3x5 @ 75-85% 1RM")
    assert parsed["sets"] == 3
    assert parsed["reps"] == "5"
    assert parsed["load"]["method"] == "percentage"
    assert parsed["load"]["value"] == 85.0
    assert parsed["load"]["ref"] == "1RM"


def test_parse_bank_prescription_unparseable_is_empty():
    assert parse_bank_prescription("as needed") == {}
    assert parse_bank_prescription(None) == {}


def test_bank_strength_entry_converts_to_valid_block():
    entry = {
        "name": "Barbell Back Squat",
        "method": "strength",
        "category": "lower_body",
        "prescription": "3x5 @ 75-85% 1RM",
        "notes": "Foundational strength builder.",
        "impact_cost": "low",
    }
    block = bank_strength_to_block(entry)
    SessionBlock.model_validate(block)  # respects the schema
    assert block["display_name"] == "Barbell Back Squat"
    assert block["block_type"] == "strength"
    assert block["sets"] == 3
    assert block["load"]["unit"] == "percent"
    assert block["load"]["ref"] == "1RM"


def test_bank_conditioning_entry_converts_to_valid_block():
    entry = {
        "name": "Assault Bike Sprint Intervals",
        "system": "ATP-PCr",
        "work_sec": 10,
        "rest_sec": 50,
        "rounds": 8,
        "total_minutes": 8,
        "rpe": 9,
        "intensity": "max",
        "notes": "Posterior-chain drive without joint pounding.",
        "impact_cost": "low",
    }
    block = bank_conditioning_to_block(entry)
    SessionBlock.model_validate(block)
    assert block["block_type"] == "conditioning"
    assert block["work"] == {"value": 10.0, "unit": "seconds"}
    assert block["rest"] == {"value": 50.0, "unit": "seconds"}
    assert block["duration"] == {"value": 8.0, "unit": "minutes"}
    assert block["rounds"] == 8
    assert block["effort"] == {"method": "RPE", "value": 9, "scale": "1-10"}
    assert block["energy_system"] == "ATP-PCr"
    assert block["intensity"] == "max"


def test_real_bank_entries_convert_to_valid_blocks():
    # Representative live bank entries must convert without error or invention.
    strength = bank_strength_to_block(_first_bank_entry("universal_gpp_strength.json"))
    SessionBlock.model_validate(strength)
    assert strength["display_name"]

    conditioning = bank_conditioning_to_block(_first_bank_entry("conditioning_bank.json"))
    SessionBlock.model_validate(conditioning)
    assert conditioning["block_type"] == "conditioning"
    # work_sec is seconds in the bank; the adapter must keep it in seconds.
    if "work" in conditioning:
        assert conditioning["work"]["unit"] == "seconds"


def test_bank_adapters_do_not_invent_content():
    # An almost-empty entry yields only structural defaults, no fabricated load.
    block = bank_strength_to_block({"name": "Mystery Lift"})
    assert block["display_name"] == "Mystery Lift"
    assert "load" not in block  # no prescription -> no invented load
    assert "sets" not in block


# --- should_attempt_structured_plan: canonical state-machine trigger ---------


def _displayable_plan(status: str) -> dict:
    return {"status": status, "final_plan_text": "# final plan", "structured_plan": None}


def test_should_attempt_for_ready_and_publishable_with_flags():
    assert should_attempt_structured_plan(_displayable_plan("ready"), True) is True
    assert should_attempt_structured_plan(_displayable_plan("publishable_with_flags"), True) is True


def test_should_not_attempt_for_non_displayable_statuses():
    for status in (
        "generated",
        "review_required",
        "held_for_review",
        "triage_blocked",
        "medical_hold",
        "needs_review",
        "restricted_rehab_only",  # safety-gated, intentionally excluded
        "archived",
    ):
        assert should_attempt_structured_plan(_displayable_plan(status), True) is False, status


def test_should_not_attempt_when_env_disabled():
    assert should_attempt_structured_plan(_displayable_plan("ready"), False) is False


def test_should_not_attempt_when_structured_plan_already_present():
    plan = _displayable_plan("ready")
    plan["structured_plan"] = {"schema_version": SCHEMA_VERSION}
    assert should_attempt_structured_plan(plan, True) is False


def test_should_not_attempt_without_final_plan_text():
    plan = _displayable_plan("ready")
    plan["final_plan_text"] = ""
    plan["plan_text"] = ""
    assert should_attempt_structured_plan(plan, True) is False


def test_should_attempt_uses_plan_text_when_final_missing():
    plan = {"status": "ready", "plan_text": "# displayed plan", "structured_plan": None}
    assert should_attempt_structured_plan(plan, True) is True


def test_should_not_attempt_for_non_dict():
    assert should_attempt_structured_plan(None, True) is False
    assert should_attempt_structured_plan("ready", True) is False


# --- PR-1: carry-through of already-supported schema fields ------------------


def test_normalize_preserves_mindset_optional_anchors():
    plan = normalize_structured_plan_candidate(
        {
            "weeks": [
                {
                    "days": [
                        {
                            "today_card": {
                                "mindset_anchor": {
                                    "intent": "Stay sharp",
                                    "focus_cue": "Hands up",
                                    "reset_cue": "Breathe",
                                    "confidence_anchor": "You've banked the work",
                                    "context": "First hard week",
                                }
                            },
                            "sessions": [
                                {
                                    "mindset_anchor": {
                                        "intent": "Move fast",
                                        "focus_cue": "Drive",
                                        "reset_cue": "Reset stance",
                                        "confidence_anchor": "Done this load before",
                                    }
                                }
                            ],
                        }
                    ]
                }
            ]
        }
    )
    day = plan["weeks"][0]["days"][0]
    assert day["today_card"]["mindset_anchor"]["confidence_anchor"] == "You've banked the work"
    assert day["today_card"]["mindset_anchor"]["context"] == "First hard week"
    assert day["sessions"][0]["mindset_anchor"]["confidence_anchor"] == "Done this load before"


def test_normalize_block_carries_coaching_detail():
    block = normalize_structured_plan_candidate(
        {
            "weeks": [
                {
                    "days": [
                        {
                            "sessions": [
                                {
                                    "blocks": [
                                        {
                                            "display_name": "Back Squat",
                                            "coaching_cues": ["Brace hard", "  ", "Knees out"],
                                            "regression_options": ["Goblet squat"],
                                            "substitutions": "Trap-bar deadlift",
                                            "progression_rule": "Add 2.5kg when all reps clean",
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    )["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]
    assert block["coaching_cues"] == ["Brace hard", "Knees out"]  # blanks dropped
    assert block["regression_options"] == ["Goblet squat"]
    assert block["substitutions"] == ["Trap-bar deadlift"]  # lone string wrapped
    assert block["progression_rule"] == "Add 2.5kg when all reps clean"


def test_full_block_and_mindset_detail_round_trips_through_outcome():
    # _valid_plan already carries coaching_cues/regression_options/substitutions on
    # its block; add the optional mindset anchors and confirm they survive.
    plan = _valid_plan()
    plan["weeks"][0]["days"][0]["sessions"][0]["mindset_anchor"]["confidence_anchor"] = "Anchor X"
    outcome = build_structured_plan_outcome(plan, raw_markdown=_faithful_source(plan))
    assert outcome.status == "valid"
    block = outcome.structured_plan["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]
    assert block["coaching_cues"]
    assert block["substitutions"]
    session = outcome.structured_plan["weeks"][0]["days"][0]["sessions"][0]
    assert session["mindset_anchor"]["confidence_anchor"] == "Anchor X"


def test_prompt_requires_block_detail_and_day_mindset():
    prompt = build_structured_plan_prompt(plan_markdown="# plan")
    for needle in (
        '"coaching_cues"',
        '"regression_options"',
        '"substitutions"',
        '"progression_rule"',
        "confidence_anchor",
        "today_card.mindset_anchor",
    ):
        assert needle in prompt, needle
    # Guardrail wording: omit, do not invent.
    assert "invent" in prompt.lower()


# --- malformed daily_check_ins tolerance (PR-7) ------------------------------


def _good_check_in() -> dict:
    return {
        "date": "2026-05-29",
        "morning": {"sleep_quality": 4, "overall_readiness": 4, "pain": 2},
        "decision": "train_as_planned",
        "rules_triggered": [],
    }


def test_missing_daily_check_ins_keeps_safe_empty_default():
    # Requirement 1: a missing key stays the model's empty-list default.
    assert _normalize_daily_check_ins(None) == []
    assert _normalize_daily_check_ins({"x": 1}) == []
    assert _normalize_daily_check_ins([]) == []


def test_valid_check_in_is_preserved():
    out = _normalize_daily_check_ins([_good_check_in()])
    assert len(out) == 1
    assert out[0]["date"] == "2026-05-29"
    assert out[0]["morning"]["sleep_quality"] == 4
    assert out[0]["decision"] == "train_as_planned"


def test_malformed_check_in_does_not_cause_invalid_fallback():
    # Requirement 6: malformed daily_check_ins alone must not sink the plan.
    plan = _valid_plan()
    plan["daily_check_ins"] = [
        {"morning": {"sleep_quality": 4}},  # missing date/decision, partial morning
        {"date": "2026-05-30", "decision": "definitely_yes"},  # bad decision, no morning
        _good_check_in(),  # one fully valid entry survives
    ]
    outcome = build_structured_plan_outcome(plan, raw_markdown=_faithful_source(plan))
    assert outcome.status in {"valid", "repair_attempted_valid"}
    validate_structured_plan(outcome.structured_plan)
    surviving = outcome.structured_plan["daily_check_ins"]
    assert len(surviving) == 1
    assert surviving[0]["date"] == "2026-05-29"


def test_entry_missing_date_is_dropped_when_not_inferable():
    # Requirement 5: no date and no resolvable index -> drop.
    entry = _good_check_in()
    entry.pop("date")
    assert _normalize_daily_check_ins([entry]) == []


def test_entry_missing_date_is_inferred_from_unambiguous_index():
    # Requirement 5: infer from week/day index only when it resolves uniquely.
    entry = _good_check_in()
    entry.pop("date")
    entry["week_index"] = 1
    entry["day_index"] = 0
    weeks = [
        {"week_index": 1, "days": [{"date": "2026-06-01"}, {"date": "2026-06-02"}]},
    ]
    out = _normalize_daily_check_ins([entry], weeks)
    assert len(out) == 1
    assert out[0]["date"] == "2026-06-01"


def test_entry_with_ambiguous_index_is_dropped():
    entry = _good_check_in()
    entry.pop("date")
    entry["week_index"] = 1
    entry["day_index"] = 0
    # Two weeks share week_index 1 -> the index does not resolve uniquely.
    weeks = [
        {"week_index": 1, "days": [{"date": "2026-06-01"}]},
        {"week_index": 1, "days": [{"date": "2026-07-01"}]},
    ]
    assert _normalize_daily_check_ins([entry], weeks) == []


def test_entry_missing_morning_is_dropped_no_fake_biometrics():
    # Requirement 3: no neutral default exists for self-report scores -> drop.
    entry = _good_check_in()
    entry.pop("morning")
    assert _normalize_daily_check_ins([entry]) == []


def test_entry_with_incomplete_morning_is_dropped():
    entry = _good_check_in()
    entry["morning"] = {"sleep_quality": 4, "overall_readiness": 3}  # pain missing
    assert _normalize_daily_check_ins([entry]) == []


def test_entry_with_out_of_range_morning_is_dropped():
    entry = _good_check_in()
    entry["morning"]["overall_readiness"] = 9  # out of 1-5
    assert _normalize_daily_check_ins([entry]) == []


def test_numeric_string_scores_are_coerced_not_invented():
    # Coercing "4" -> 4 is a formatting fix, not fabrication.
    entry = _good_check_in()
    entry["morning"] = {"sleep_quality": "4", "overall_readiness": "5", "pain": "0"}
    out = _normalize_daily_check_ins([entry])
    assert len(out) == 1
    assert out[0]["morning"] == {"sleep_quality": 4, "overall_readiness": 5, "pain": 0}


def test_invalid_decision_is_dropped():
    # Requirement 4: an unrecognized decision is dropped, never defaulted.
    entry = _good_check_in()
    entry["decision"] = "feeling_great"
    assert _normalize_daily_check_ins([entry]) == []


def test_obvious_decision_alias_is_mapped_to_valid_enum():
    # Requirement 4: only obvious aliases map to a real enum value.
    for alias, expected in (
        ("Train_As_Planned", "train_as_planned"),
        ("modified", "modify"),
        ("pull back", "pull_back"),
        ("unavailable", "unavailable"),
    ):
        entry = _good_check_in()
        entry["decision"] = alias
        out = _normalize_daily_check_ins([entry])
        assert len(out) == 1, alias
        assert out[0]["decision"] == expected


def test_no_fake_biometric_keys_introduced():
    # The normalizer never adds biometric/readiness scores beyond self-report.
    out = _normalize_daily_check_ins([_good_check_in()])
    morning_keys = set(out[0]["morning"])
    assert morning_keys <= {"sleep_quality", "overall_readiness", "pain", "location", "injury_specific"}
    assert not (morning_keys & BANNED_BIOMETRIC_KEYS)


def test_plan_with_only_malformed_check_ins_still_valid():
    # Requirement 2/6: drop everything -> empty list, plan still validates.
    plan = _valid_plan()
    plan["daily_check_ins"] = [
        {"morning": {"sleep_quality": 4}},
        {"date": "2026-05-30", "decision": "nope"},
    ]
    outcome = build_structured_plan_outcome(plan, raw_markdown=_faithful_source(plan))
    assert outcome.status in {"valid", "repair_attempted_valid"}
    assert outcome.structured_plan["daily_check_ins"] == []
    validate_structured_plan(outcome.structured_plan)


def test_plan_text_fallback_still_works_for_fully_invalid_structure():
    # The existing fallback is untouched when the whole structure is invalid.
    outcome = build_structured_plan_outcome(_invalid_plan(), raw_markdown="# raw")
    assert outcome.status == "invalid_fallback_used"
    assert outcome.structured_plan is None


def test_prompt_requires_valid_or_omitted_check_ins():
    prompt = build_structured_plan_prompt(plan_markdown="# plan")
    assert "daily_check_ins" in prompt
    assert "fully valid or omitted" in prompt
    assert "partial check-in" in prompt
