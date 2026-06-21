from dataclasses import replace
from types import SimpleNamespace

import pytest

from fightcamp.injury_triage import (
    FULL_PLAN,
    InjuryTriageResult,
    MEDICAL_HOLD,
    NEEDS_REVIEW,
    RESTRICTED_REHAB_ONLY,
    _collect_guided_card_evidence,
    blocked_mode_output,
    normalize_triage_category,
    triage_injuries,
)
from fightcamp.input_parsing import GuidedInjury, PlanInput
from fightcamp.main import generate_plan_sync
from fightcamp.triage_features import build_triage_features, parse_guided_note_tags
from support import _build_request


def _base_payload() -> dict:
    return _build_request().to_payload()


def _payload_with_injury(injury_text: str) -> dict:
    data = _base_payload()
    for field in data["data"]["fields"]:
        if field.get("label") == "Any injuries or areas you need to work around?":
            field["value"] = injury_text
            break
    return data


def test_mild_soreness_allows_full_planning():
    parsed = PlanInput.from_payload(_payload_with_injury("mild calf soreness after sprints"))
    triage = triage_injuries(parsed)

    assert triage.mode == FULL_PLAN
    assert triage.should_block_stage2 is False


@pytest.mark.parametrize("injury_text", ["left knee swelling", "left knee instability"])
def test_swelling_or_instability_alone_do_not_force_triage_block(injury_text: str):
    parsed = PlanInput.from_payload(_payload_with_injury(injury_text))
    triage = triage_injuries(parsed)

    assert triage.mode == FULL_PLAN
    assert triage.should_block_stage2 is False


def test_ankle_swelling_alone_does_not_block_triage():
    parsed = PlanInput.from_payload(_payload_with_injury("ankle swelling"))
    triage = triage_injuries(parsed)

    assert triage.mode == FULL_PLAN
    assert triage.should_block_stage2 is False


def test_rapid_swelling_after_tackle_and_cannot_bear_weight_blocks_triage():
    parsed = PlanInput.from_payload(
        _payload_with_injury("rapid ankle swelling after tackle and cannot bear weight")
    )
    triage = triage_injuries(parsed)

    assert triage.mode != FULL_PLAN
    assert triage.should_block_stage2 is True


def test_instability_with_giving_way_and_buckling_blocks_triage():
    parsed = PlanInput.from_payload(_payload_with_injury("knee instability with giving way and buckled twice"))
    triage = triage_injuries(parsed)

    assert triage.mode != FULL_PLAN
    assert triage.should_block_stage2 is True


def test_fracture_routes_to_restricted_rehab_only_and_matches_existing_signals():
    parsed = PlanInput.from_payload(
        _payload_with_injury("right ankle fracture with worsening swelling and cannot bear weight")
    )
    triage = triage_injuries(parsed)

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert triage.should_block_stage2 is True
    assert "urgent_fracture" in triage.urgent_flags
    assert triage.sparring_risk_band in {"red", "black"}


def test_free_text_broke_it_last_week_is_not_treated_as_normal_moderate_stable():
    parsed = PlanInput.from_payload(
        _payload_with_injury("Right ankle — moderate, stable. Notes: broke it last week")
    )
    triage = triage_injuries(parsed)

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert triage.should_block_stage2 is True
    assert triage.clinician_clearance_required is True
    assert "fracture" in triage.matched_high_risk_categories
    assert "raw_injury:structural_broke_signal" in triage.routing_reasons


def test_not_broken_it_does_not_route_fracture():
    parsed = PlanInput.from_payload(
        _payload_with_injury("Right ankle not broken, mild sprain only")
    )
    triage = triage_injuries(parsed)

    assert triage.mode == FULL_PLAN
    assert "fracture" not in triage.matched_high_risk_categories


def test_ruled_out_fracture_after_thought_i_broke_it_does_not_route_fracture():
    parsed = PlanInput.from_payload(
        _payload_with_injury("Scan ruled out fracture after I thought I broke it")
    )
    triage = triage_injuries(parsed)

    assert triage.mode == FULL_PLAN
    assert "fracture" not in triage.matched_high_risk_categories


@pytest.mark.parametrize(
    "injury_text",
    [
        "neck cracked but no pain",
        "knee snapped while stretching but no pain",
        "ankle crack sound only, no pain or swelling",
        "ankle clicked but can walk, no swelling, no deformity",
        "ankle popped but no pain, no swelling, can walk",
    ],
)
def test_benign_structural_break_words_without_symptoms_do_not_route_fracture(injury_text: str):
    parsed = PlanInput.from_payload(_payload_with_injury(injury_text))
    triage = triage_injuries(parsed)

    assert triage.mode == FULL_PLAN
    assert "fracture" not in triage.matched_high_risk_categories


@pytest.mark.parametrize(
    "injury_text",
    [
        "ankle snapped and now swollen after tackle",
        "knee snapped and gave way",
        "heard a snap and cannot bear weight",
    ],
)
def test_joint_noise_with_escalation_still_routes_fracture(injury_text: str):
    parsed = PlanInput.from_payload(_payload_with_injury(injury_text))
    triage = triage_injuries(parsed)

    assert triage.mode != FULL_PLAN
    # Escalated joint-noise routes to a high-severity structural category. The
    # specific "fracture" label may be folded into the consolidated
    # "structural_high_severity" bucket; either satisfies the block.
    assert {"fracture", "structural_high_severity"} & set(
        triage.matched_high_risk_categories
    )




@pytest.mark.parametrize(
    "injury_text",
    [
        "shoulder popped out during sparring",
        "knee buckled and gave way twice",
        "ankle popped and cannot bear weight",
    ],
)
def test_danger_terms_do_not_route_to_full_plan(injury_text: str):
    parsed = PlanInput.from_payload(_payload_with_injury(injury_text))
    triage = triage_injuries(parsed)

    assert triage.mode != FULL_PLAN
    assert triage.should_block_stage2 is True


def test_shoulder_popped_out_routes_dislocation_restriction():
    parsed = PlanInput.from_payload(_payload_with_injury("shoulder popped out during sparring"))
    triage = triage_injuries(parsed)

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert "dislocation" in triage.matched_high_risk_categories


def test_benign_ankle_pop_with_no_symptoms_stays_full_plan():
    parsed = PlanInput.from_payload(_payload_with_injury("ankle popped but no pain, no swelling, can walk"))
    triage = triage_injuries(parsed)

    assert triage.mode == FULL_PLAN
def test_concussion_routes_to_medical_hold():
    parsed = PlanInput.from_payload(
        _payload_with_injury("suspected concussion with headache after sparring")
    )
    triage = triage_injuries(parsed)

    assert triage.mode == MEDICAL_HOLD
    assert triage.should_block_stage2 is True


def test_urgent_neurological_symptoms_route_to_medical_hold():
    parsed = PlanInput.from_payload(
        _payload_with_injury("neck pain with numbness, tingling, weakness, and loss of consciousness")
    )
    triage = triage_injuries(parsed)

    assert triage.mode == MEDICAL_HOLD
    assert triage.should_block_stage2 is True
    assert "loss_of_consciousness" in triage.red_flags
    assert "neurological_red_flag_combination" in triage.routing_reasons


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        ("tendon_rupture", "tendon_rupture_or_avulsion"),
        ("ligament_tear", "complete_ligament_tear"),
        ("mcl_tear", "complete_ligament_tear"),
        ("lcl_tear", "complete_ligament_tear"),
        ("pcl_tear", "pcl_tear"),
        ("acl_tear", "acl_tear"),
        ("nerve_involvement", "neurological_symptoms"),
        ("infection", "septic_joint_or_bone_infection"),
    ],
)
def test_normalize_triage_category_aliases(category: str, expected: str):
    assert normalize_triage_category(category) == expected


def test_tendon_rupture_alias_in_parsed_injury_routes_restricted():
    parsed = PlanInput.from_payload(_payload_with_injury("felt tendon pop in achilles"))
    parsed = replace(
        parsed,
        parsed_injuries=[{"location": "achilles", "injury_type": "tendon_rupture", "severity": "moderate"}],
    )

    triage = triage_injuries(parsed)

    assert triage.mode != FULL_PLAN
    assert "tendon_rupture_or_avulsion" in triage.matched_high_risk_categories
    assert triage.clinician_clearance_required is True


def test_ligament_tear_alias_in_parsed_injury_routes_restricted():
    parsed = PlanInput.from_payload(_payload_with_injury("knee ligament tear"))
    parsed = replace(
        parsed,
        parsed_injuries=[{"location": "knee", "injury_type": "ligament_tear", "severity": "moderate"}],
    )

    triage = triage_injuries(parsed)

    assert triage.mode != FULL_PLAN
    assert "complete_ligament_tear" in triage.matched_high_risk_categories


def test_neurological_signals_still_require_review():
    parsed = PlanInput.from_payload(_payload_with_injury("neck pain with numbness and tingling"))
    triage = triage_injuries(parsed)

    assert {"numbness", "tingling"}.intersection(set(triage.red_flags))
    assert triage.mode != FULL_PLAN

def test_guided_injury_and_restrictions_are_used_for_triage():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "left rib",
        "severity": "high",
        "trend": "worsening",
        "avoid": "contact and hard sparring",
        "notes": "pain breathing deeply after impact",
    }

    parsed = PlanInput.from_payload(payload)
    triage = triage_injuries(parsed)

    assert triage.mode == MEDICAL_HOLD
    assert "breathing_pain" in triage.red_flags
    assert "guided_injury:worsening" in triage.routing_reasons
    assert "rib_breathing_red_flag_combination" in triage.routing_reasons


def test_text_escalation_overrides_guided_low_and_still_blocks_stage2():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "left knee",
        "severity": "low",
        "trend": "stable",
        "notes": "sharp pain, swelling, and cannot bear weight",
    }

    parsed = PlanInput.from_payload(payload)
    escalated = parsed.parsed_injuries[0]
    triage = triage_injuries(parsed)

    assert escalated["severity"] == "high"
    assert escalated["severity_source"] == "text_escalation"
    assert "sharp" in escalated["severity_evidence"]
    assert "swelling" in escalated["severity_evidence"]
    assert triage.should_block_stage2 is True
    assert triage.mode != FULL_PLAN


def test_second_guided_card_can_trigger_medical_hold():
    payload = _payload_with_injury("")
    payload["guided_injuries"] = [
        {
            "area": "rolled left ankle",
            "injury_type": "tendon_ligament",
            "severity": "moderate",
            "trend": "stable",
            "notes": "Can bear weight. No deformity.",
        },
        {
            "area": "head impact",
            "injury_type": "impact",
            "severity": "moderate",
            "trend": "stable",
            "notes": "Vomited after head impact.",
        },
    ]
    parsed = PlanInput.from_payload(payload)

    triage = triage_injuries(parsed)

    assert triage.mode == MEDICAL_HOLD
    assert "vomiting_after_head_impact" in triage.red_flags
    assert any("medical_hold" in reason or "red_flag" in reason for reason in triage.routing_reasons)


def test_second_guided_card_negated_safety_fields_do_not_false_trigger():
    payload = _payload_with_injury("")
    payload["guided_injuries"] = [
        {"area": "rolled left ankle", "injury_type": "tendon_ligament", "notes": "Can bear weight."},
        {
            "area": "head impact",
            "injury_type": "impact",
            "notes": "Head impact. No vomiting. No severe headache. No confusion.",
        },
    ]
    parsed = PlanInput.from_payload(payload)

    triage = triage_injuries(parsed)

    assert "vomiting_after_head_impact" not in triage.red_flags
    assert "severe_headache_after_head_impact" not in triage.red_flags
    assert "confusion" not in triage.red_flags


def test_second_guided_card_restriction_is_preserved():
    payload = _payload_with_injury("")
    payload["guided_injuries"] = [
        {"area": "left wrist", "severity": "mild", "trend": "stable", "notes": "mild wrist tightness"},
        {
            "area": "left knee",
            "severity": "moderate",
            "trend": "stable",
            "avoid": "hard cutting and jumping",
            "notes": "knee pain with changes of direction",
        },
    ]
    parsed = PlanInput.from_payload(payload)
    triage = triage_injuries(parsed)

    assert any("knee" in (entry.get("region") or "") for entry in parsed.restrictions)
    assert "avoid_high_load" in triage.routing_reasons or "guided_injury:avoid_high_load" in triage.routing_reasons


def test_structured_clinician_restriction_signals_accumulate_across_guided_cards():
    payload = _payload_with_injury("")
    payload["guided_injuries"] = [
        {
            "area": "right forearm",
            "injury_type": "surface_injury",
            "surface_type": "bruise",
            "notes": "minor bruise",
        },
        {
            "area": "left knee",
            "injury_type": "post_surgery",
            "cleared": "no",
            "notes": "post-op reconstruction phase",
        },
    ]

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert "clinician_restriction_signal" in triage.routing_reasons


def test_guided_injury_acl_rupture_routes_to_restricted_rehab_only():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "right knee",
        "severity": "high",
        "trend": "stable",
        "notes": "slide tackle went wrong which caused me to rupture acl",
    }

    parsed = PlanInput.from_payload(payload)
    triage = triage_injuries(parsed)

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert triage.should_block_stage2 is True
    assert "acl_tear" in triage.matched_high_risk_categories


def test_guided_injury_structural_tear_not_limited_to_acl():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "left shoulder",
        "severity": "high",
        "trend": "stable",
        "notes": "full thickness rotator cuff tear after fall",
    }

    parsed = PlanInput.from_payload(payload)
    triage = triage_injuries(parsed)

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert triage.should_block_stage2 is True
    assert "scored_structural_severe_signal" in triage.routing_reasons


def test_structured_parsed_hyperextension_does_not_escalate_from_guided_metadata():
    features = build_triage_features(
        injuries="",
        parsed_injuries=[
            {
                "injury_type": "hyperextension",
                "guided_injury_type": "tendon_ligament",
                "canonical_location": "knee",
            }
        ],
        guided_injury=None,
        restrictions=None,
    )
    assert "tendon_rupture_or_avulsion" not in features.high_risk_diagnoses
    assert "complete_ligament_tear" not in features.high_risk_diagnoses


def test_structured_parsed_fracture_maps_directly_to_high_risk():
    features = build_triage_features(
        injuries="",
        parsed_injuries=[
            {
                "injury_type": "fracture",
                "injury_type_source": "guided_serious_type",
                "canonical_location": "hand",
            }
        ],
        guided_injury=None,
        restrictions=None,
    )
    assert "fracture" in features.high_risk_diagnoses


def test_structured_parsed_dislocation_maps_directly_to_high_risk():
    features = build_triage_features(
        injuries="",
        parsed_injuries=[
            {
                "injury_type": "dislocation",
                "injury_type_source": "guided_serious_type",
                "canonical_location": "shoulder",
            }
        ],
        guided_injury=None,
        restrictions=None,
    )
    assert "dislocation" in features.high_risk_diagnoses


def test_structured_surface_contusion_does_not_auto_escalate_to_high_risk():
    features = build_triage_features(
        injuries="",
        parsed_injuries=[
            {
                "injury_type": "contusion",
                "guided_surface_type": "bruise",
                "canonical_location": "knee",
            }
        ],
        guided_injury=None,
        restrictions=None,
    )
    assert "fracture" not in features.high_risk_diagnoses
    assert "dislocation" not in features.high_risk_diagnoses
    assert "tendon_rupture_or_avulsion" not in features.high_risk_diagnoses


def test_structured_parsed_tendon_rupture_maps_directly_to_high_risk():
    features = build_triage_features(
        injuries="",
        parsed_injuries=[
            {
                "injury_type": "tendon_rupture_or_avulsion",
                "injury_type_source": "guided_tendon_ligament",
                "canonical_location": "knee",
            }
        ],
        guided_injury=None,
        restrictions=None,
    )
    assert "tendon_rupture_or_avulsion" in features.high_risk_diagnoses


def test_structured_soft_tissue_joint_issue_does_not_override_resolved_injury_type():
    features = build_triage_features(
        injuries="",
        parsed_injuries=[
            {
                "injury_type": "soft_tissue_joint_issue",
                "guided_injury_type": "tendon_ligament",
                "canonical_location": "knee",
            }
        ],
        guided_injury=None,
        restrictions=None,
    )
    assert "tendon_rupture_or_avulsion" not in features.high_risk_diagnoses


def test_guided_injury_type_dislocation_does_not_override_resolved_parsed_hyperextension():
    features = build_triage_features(
        injuries="",
        parsed_injuries=[
            {
                "injury_type": "hyperextension",
                "injury_type_source": "parser",
                "guided_injury_type": "dislocation",
                "canonical_location": "shoulder",
            }
        ],
        guided_injury=SimpleNamespace(
            area="hyperextended right shoulder",
            severity=None,
            trend=None,
            avoid=None,
            notes=None,
            injury_type="dislocation",
            surface_type=None,
            timeframe=None,
            cleared=None,
            open_wound=None,
            bleeding_status=None,
            infection_signs=None,
            impact_related=None,
            sensitive_area=None,
        ),
        restrictions=None,
    )
    assert "dislocation" not in features.high_risk_diagnoses


def test_guided_injury_type_fracture_does_not_override_resolved_parsed_hyperextension():
    features = build_triage_features(
        injuries="",
        parsed_injuries=[
            {
                "injury_type": "hyperextension",
                "injury_type_source": "parser",
                "guided_injury_type": "fracture",
                "canonical_location": "knee",
            }
        ],
        guided_injury=SimpleNamespace(
            area="hyperextended right knee",
            severity=None,
            trend=None,
            avoid=None,
            notes=None,
            injury_type="fracture",
            surface_type=None,
            timeframe=None,
            cleared=None,
            open_wound=None,
            bleeding_status=None,
            infection_signs=None,
            impact_related=None,
            sensitive_area=None,
        ),
        restrictions=None,
    )
    assert "fracture" not in features.high_risk_diagnoses


def test_guided_injury_type_fracture_can_still_be_used_when_no_parsed_injuries_exist():
    features = build_triage_features(
        injuries="",
        parsed_injuries=None,
        guided_injury=SimpleNamespace(
            area="hand injury",
            severity="high",
            trend="worsening",
            avoid=None,
            notes=None,
            injury_type="fracture",
            surface_type=None,
            timeframe=None,
            cleared=None,
            open_wound=None,
            bleeding_status=None,
            infection_signs=None,
            impact_related=None,
            sensitive_area=None,
        ),
        restrictions=None,
    )
    assert "fracture" in features.high_risk_diagnoses


def test_triage_resolved_parsed_hyperextension_blocks_guided_dislocation_override():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "hyperextended right shoulder",
        "injury_type": "dislocation",
        "severity": "moderate",
        "trend": "stable",
    }
    parsed = PlanInput.from_payload(payload)
    parsed = replace(
        parsed,
        parsed_injuries=[
            {
                "injury_type": "hyperextension",
                "injury_type_source": "parser",
                "guided_injury_type": "dislocation",
                "canonical_location": "shoulder",
            }
        ],
    )

    triage = triage_injuries(parsed)

    assert "dislocation" not in triage.matched_high_risk_categories
    assert triage.mode != RESTRICTED_REHAB_ONLY
    assert "structured:dislocation" not in triage.routing_reasons


def test_triage_resolved_parsed_hyperextension_blocks_guided_fracture_override():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "hyperextended right knee",
        "injury_type": "fracture",
        "severity": "moderate",
        "trend": "stable",
    }
    parsed = PlanInput.from_payload(payload)
    parsed = replace(
        parsed,
        parsed_injuries=[
            {
                "injury_type": "hyperextension",
                "injury_type_source": "parser",
                "guided_injury_type": "fracture",
                "canonical_location": "knee",
            }
        ],
    )

    triage = triage_injuries(parsed)

    assert "fracture" not in triage.matched_high_risk_categories


def test_triage_guided_fracture_fallback_still_applies_when_parsed_injuries_absent():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "right hand",
        "injury_type": "fracture",
        "severity": "moderate",
        "trend": "stable",
    }
    parsed = PlanInput.from_payload(payload)
    parsed = replace(parsed, parsed_injuries=[])

    triage = triage_injuries(parsed)

    assert "fracture" in triage.matched_high_risk_categories
    assert triage.mode == RESTRICTED_REHAB_ONLY


def test_triage_guided_safety_signals_still_apply_with_resolved_parsed_injury():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "hyperextended right knee",
        "injury_type": "fracture",
        "severity": "moderate",
        "trend": "stable",
        "impact_related": "yes",
        "notes": "cannot bear weight",
    }
    parsed = PlanInput.from_payload(payload)
    parsed = replace(
        parsed,
        guided_injury=GuidedInjury(
            **{
                **parsed.guided_injury.__dict__,
                "notes": "pain during movement, cannot bear weight",
            }
        ),
        parsed_injuries=[
            {
                "injury_type": "hyperextension",
                "canonical_location": "knee",
            }
        ],
    )

    triage = triage_injuries(parsed)

    assert "fracture" not in triage.matched_high_risk_categories
    assert "cannot_bear_weight" in triage.red_flags
    assert "structural_function_red_flag" in triage.routing_reasons


def test_negated_bear_weight_and_deformity_do_not_trigger_red_flags():
    text = "Rolled left ankle. Can bear weight. No deformity."
    features = build_triage_features(
        injuries=text,
        parsed_injuries=None,
        guided_injury=None,
        restrictions=None,
    )

    assert "cannot_bear_weight" not in features.red_flags
    assert "deformity" not in features.red_flags
    assert "cannot_bear_weight" not in features.function_loss_signals


def test_cannot_bear_weight_and_visible_deformity_still_trigger_red_flags():
    text = "Rolled left ankle. Cannot bear weight. Visible deformity."
    features = build_triage_features(
        injuries=text,
        parsed_injuries=None,
        guided_injury=None,
        restrictions=None,
    )

    assert "cannot_bear_weight" in features.red_flags
    assert "deformity" in features.red_flags
    assert "cannot_bear_weight" in features.function_loss_signals


def test_can_still_walk_and_no_visible_deformity_do_not_trigger_medical_hold():
    payload = _payload_with_injury("Rolled left ankle. I can still walk. No visible deformity.")
    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode != MEDICAL_HOLD
    assert "cannot_bear_weight" not in triage.red_flags
    assert "deformity" not in triage.red_flags


def test_guided_notes_negated_deformity_and_can_bear_weight_do_not_trigger_red_flags():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "left ankle sprain",
        "severity": "moderate",
        "trend": "stable",
        "notes": "No fracture confirmed. No deformity. Can bear weight.",
    }
    triage = triage_injuries(PlanInput.from_payload(payload))

    assert "cannot_bear_weight" not in triage.red_flags
    assert "deformity" not in triage.red_flags


def test_guided_notes_unable_to_bear_weight_and_obvious_deformity_trigger_medical_hold():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "left ankle injury",
        "severity": "moderate",
        "trend": "stable",
        "notes": "Unable to bear weight. Obvious deformity.",
    }
    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode == MEDICAL_HOLD
    assert "cannot_bear_weight" in triage.red_flags
    assert "deformity" in triage.red_flags


def test_triage_surface_safety_red_flags_still_apply_when_parsed_injury_exists():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "right cheek cut",
        "injury_type": "surface_injury",
        "surface_type": "cut",
        "open_wound": "yes",
        "bleeding_status": "uncontrolled",
        "sensitive_area": "yes",
        "severity": "moderate",
        "trend": "stable",
    }
    parsed = replace(
        PlanInput.from_payload(payload),
        parsed_injuries=[{"injury_type": "cut", "canonical_location": "face"}],
    )

    triage = triage_injuries(parsed)

    assert "fracture" not in triage.matched_high_risk_categories
    assert "uncontrolled_bleeding" in triage.red_flags
    assert triage.mode == MEDICAL_HOLD


def test_triage_head_impact_tags_apply_without_head_impact_diagnosis_override():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "head pain",
        "injury_type": "head_impact",
        "notes": "[red_flags:vomiting]",
        "severity": "moderate",
        "trend": "stable",
    }
    parsed = replace(
        PlanInput.from_payload(payload),
        parsed_injuries=[{"injury_type": "pain", "canonical_location": "head"}],
    )

    triage = triage_injuries(parsed)

    assert "concussion" not in triage.matched_high_risk_categories
    assert "vomiting_after_head_impact" in triage.red_flags


def test_triage_blank_guided_injury_type_still_applies_red_flag_tags():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "head pain",
        "injury_type": "",
        "notes": "[red_flags:vomiting]",
        "severity": "moderate",
        "trend": "stable",
    }
    parsed = replace(
        PlanInput.from_payload(payload),
        parsed_injuries=[{"injury_type": "pain", "canonical_location": "head"}],
    )

    triage = triage_injuries(parsed)

    assert "vomiting_after_head_impact" in triage.red_flags


def test_triage_nerve_tags_apply_without_nerve_diagnosis_override():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "arm pain",
        "injury_type": "nerve_symptoms",
        "notes": "[nerve_symptoms:type_weakness]",
        "severity": "moderate",
        "trend": "stable",
    }
    parsed = replace(
        PlanInput.from_payload(payload),
        parsed_injuries=[{"injury_type": "pain", "canonical_location": "arm"}],
    )

    triage = triage_injuries(parsed)

    assert "weakness" in triage.red_flags
    assert "structured:nerve_symptoms" not in triage.routing_reasons


def test_triage_no_default_nerve_red_flags_when_parsed_injury_exists():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "arm pain",
        "injury_type": "nerve_symptoms",
        "notes": "",
        "severity": "moderate",
        "trend": "stable",
    }
    parsed = replace(
        PlanInput.from_payload(payload),
        parsed_injuries=[{"injury_type": "pain", "canonical_location": "arm"}],
    )

    triage = triage_injuries(parsed)

    assert "numbness" not in triage.red_flags


def test_triage_no_default_chest_red_flags_when_parsed_injury_exists():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "chest pain",
        "injury_type": "chest_breathing",
        "notes": "",
        "severity": "moderate",
        "trend": "stable",
    }
    parsed = replace(
        PlanInput.from_payload(payload),
        parsed_injuries=[{"injury_type": "pain", "canonical_location": "chest"}],
    )

    triage = triage_injuries(parsed)

    assert "breathing_pain" not in triage.red_flags
    assert "chest_pain" not in triage.red_flags


def test_triage_default_nerve_red_flag_still_applies_without_parsed_injuries():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "arm pain",
        "injury_type": "nerve_symptoms",
        "notes": "",
        "severity": "moderate",
        "trend": "stable",
    }
    parsed = replace(PlanInput.from_payload(payload), parsed_injuries=[])

    triage = triage_injuries(parsed)

    assert "numbness" in triage.red_flags


def test_triage_default_chest_red_flags_still_apply_without_parsed_injuries():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "chest pain",
        "injury_type": "chest_breathing",
        "notes": "",
        "severity": "moderate",
        "trend": "stable",
    }
    parsed = replace(PlanInput.from_payload(payload), parsed_injuries=[])

    triage = triage_injuries(parsed)

    assert "breathing_pain" in triage.red_flags
    assert "chest_pain" in triage.red_flags


def test_blocked_modes_do_not_reach_stage2_or_normal_pipeline(monkeypatch):
    payload = _payload_with_injury("open fracture with deformity")

    def _boom(*args, **kwargs):
        raise AssertionError("normal pipeline / Stage 2 should not run for blocked triage modes")

    monkeypatch.setattr("fightcamp.main.build_runtime_context", _boom)
    monkeypatch.setattr("fightcamp.main.build_stage2_outputs", _boom)

    result = generate_plan_sync(payload)

    assert result["status"] == "triage_blocked"
    assert result["stage2_payload"] is None
    assert result["stage2_status"] == "triage_blocked"
    assert result["injury_triage"]["mode"] == MEDICAL_HOLD
    blocked = result["blocked_output"]
    assert blocked["title"] == "Injury triage blocked normal plan generation"
    assert blocked["mode"] == MEDICAL_HOLD
    assert blocked["stage2_blocked"] is True
    assert blocked["clinician_clearance_required"] is True
    assert blocked["severity_summary"]
    assert any(item["severity_source"] for item in blocked["severity_summary"])
    assert blocked["red_flags"]
    assert blocked["routing_reasons"]


@pytest.mark.parametrize(
    ("mode", "expected_reason", "expected_next_step"),
    [
        (
            MEDICAL_HOLD,
            "Training guidance is blocked because urgent medical-risk signals were detected.",
            "Stop automatic training guidance and seek appropriate medical/clinical review.",
        ),
        (
            RESTRICTED_REHAB_ONLY,
            "Normal fight-camp loading is blocked. Only restricted rehab/support guidance is allowed.",
            "Generate only restricted rehab/support guidance until cleared.",
        ),
        (
            NEEDS_REVIEW,
            "Automatic planning is blocked until a coach/admin reviews the injury context.",
            "Hold normal plan generation until coach/admin review.",
        ),
    ],
)
def test_blocked_output_uses_mode_specific_explanation_and_next_step(mode, expected_reason, expected_next_step):
    result = blocked_mode_output(triage=InjuryTriageResult(mode=mode, should_block_stage2=True))
    blocked = result["blocked_output"]

    assert blocked["why_plan_blocked"] == expected_reason
    assert blocked["next_step"] == expected_next_step


def test_blocked_output_severity_summary_prefers_canonical_location_and_keeps_original_phrase():
    triage = InjuryTriageResult(mode=MEDICAL_HOLD, should_block_stage2=True)
    parsed_injuries = [
        {
            "canonical_location": "ankle",
            "injury_type": "swelling",
            "severity": "high",
            "severity_source": "text_escalation",
            "severity_evidence": ["cannot bear weight"],
            "original_phrase": "rapid ankle swelling after tackle and cannot bear weight",
        }
    ]

    result = blocked_mode_output(triage=triage, parsed_injuries=parsed_injuries)
    summary_item = result["blocked_output"]["severity_summary"][0]

    assert summary_item["area"] == "ankle"
    assert summary_item["original_phrase"] == "rapid ankle swelling after tackle and cannot bear weight"


def test_full_plan_response_does_not_include_blocked_output(monkeypatch):
    payload = _payload_with_injury("mild calf soreness after sprints")
    _stub_normal_pipeline(monkeypatch)

    result = generate_plan_sync(payload)

    # A successful (non-blocked) plan omits the "status" key entirely.
    assert result.get("status") != "triage_blocked"
    assert "blocked_output" not in result


def _stub_normal_pipeline(monkeypatch):
    monkeypatch.setattr("fightcamp.main.prime_plan_banks", lambda logger: None)
    monkeypatch.setattr("fightcamp.main.build_runtime_context", lambda **kwargs: object())
    monkeypatch.setattr("fightcamp.main.generate_plan_blocks", lambda **kwargs: {})
    monkeypatch.setattr(
        "fightcamp.main.render_plan_bundle",
        lambda **kwargs: SimpleNamespace(
            reason_log={},
            coach_notes="stub",
            fight_plan_text="# Stub Plan",
            html="<html></html>",
        ),
    )
    monkeypatch.setattr(
        "fightcamp.main.build_stage2_outputs",
        lambda **kwargs: ({}, {"summary": "stub"}, "stub handoff"),
    )


def test_needs_review_override_allows_stage2_continuation(monkeypatch):
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "knee",
        "severity": "high",
        "trend": "stable",
        "notes": "pain",
    }
    payload["_triage_resume_override"] = {
        "approved": True,
        "allowed_modes": ["needs_review", "restricted_rehab_only"],
    }
    _stub_normal_pipeline(monkeypatch)

    result = generate_plan_sync(payload)

    assert result.get("status") != "triage_blocked"
    assert result["plan_text"] == "# Stub Plan"
    assert result["why_log"]["injury_triage_resume_override"]["bypassed_blocking"] is True
    assert result["why_log"]["injury_triage_resume_override"]["triage_mode"] == NEEDS_REVIEW
    assert result["why_log"]["injury_triage_resume_override"]["runtime_triage_mode"] == FULL_PLAN
    assert result["why_log"]["injury_triage_original"]["mode"] == NEEDS_REVIEW


def test_restricted_rehab_only_override_allows_stage2_continuation(monkeypatch):
    payload = _payload_with_injury("right knee acl rupture during scramble")
    payload["_triage_resume_override"] = {
        "approved": True,
        "allowed_modes": ["needs_review", "restricted_rehab_only"],
    }
    _stub_normal_pipeline(monkeypatch)

    result = generate_plan_sync(payload)

    assert result.get("status") != "triage_blocked"
    assert result["plan_text"] == "# Stub Plan"
    assert result["why_log"]["injury_triage_resume_override"]["triage_mode"] == RESTRICTED_REHAB_ONLY
    assert result["why_log"]["injury_triage_original"]["mode"] == RESTRICTED_REHAB_ONLY


def test_resume_override_neutralizes_runtime_triage_context(monkeypatch):
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "knee",
        "severity": "high",
        "trend": "stable",
        "notes": "pain",
    }
    payload["_triage_resume_override"] = {
        "approved": True,
        "allowed_modes": ["needs_review", "restricted_rehab_only"],
    }
    expected_input = PlanInput.from_payload(payload)
    _stub_normal_pipeline(monkeypatch)
    captured: dict = {}

    def _capture_runtime_context(**kwargs):
        captured["triage_summary"] = kwargs.get("triage_summary")
        captured["is_approved_triage_resume"] = kwargs.get("is_approved_triage_resume")
        captured["plan_input"] = kwargs.get("plan_input")
        return object()

    monkeypatch.setattr("fightcamp.main.build_runtime_context", _capture_runtime_context)

    result = generate_plan_sync(payload)

    assert result.get("status") != "triage_blocked"
    assert captured["is_approved_triage_resume"] is True
    assert captured["triage_summary"]["mode"] == NEEDS_REVIEW
    assert captured["triage_summary"]["should_block_stage2"] is True
    assert captured["plan_input"].guided_injury == expected_input.guided_injury
    assert captured["plan_input"].restrictions == expected_input.restrictions
    assert captured["plan_input"].injuries == expected_input.injuries
    assert captured["plan_input"].parsed_injuries == expected_input.parsed_injuries
    assert result["why_log"]["injury_triage_original"]["mode"] == NEEDS_REVIEW


def test_non_resume_runtime_context_keeps_guided_injury_and_restrictions(monkeypatch):
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "right shoulder",
        "severity": "low",
        "trend": "stable",
        "avoid": "heavy overhead pressing",
        "notes": "mild pain at lockout",
    }
    expected_input = PlanInput.from_payload(payload)
    _stub_normal_pipeline(monkeypatch)
    captured: dict = {}

    def _capture_runtime_context(**kwargs):
        captured["plan_input"] = kwargs.get("plan_input")
        captured["is_approved_triage_resume"] = kwargs.get("is_approved_triage_resume")
        return object()

    monkeypatch.setattr("fightcamp.main.build_runtime_context", _capture_runtime_context)

    result = generate_plan_sync(payload)

    assert result.get("status") != "triage_blocked"
    assert captured["is_approved_triage_resume"] is False
    assert captured["plan_input"].guided_injury == expected_input.guided_injury
    assert captured["plan_input"].restrictions == expected_input.restrictions


def test_medical_hold_cannot_be_overridden(monkeypatch):
    payload = _payload_with_injury("suspected concussion with headache after sparring")
    payload["_triage_resume_override"] = {
        "approved": True,
        "allowed_modes": ["needs_review", "restricted_rehab_only", "medical_hold"],
    }
    _stub_normal_pipeline(monkeypatch)

    result = generate_plan_sync(payload)

    assert result["status"] == "triage_blocked"
    assert result["injury_triage"]["mode"] == MEDICAL_HOLD


def test_needs_review_without_override_still_blocks():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "knee",
        "severity": "high",
        "trend": "stable",
        "notes": "pain",
    }

    result = generate_plan_sync(payload)

    assert result["status"] == "triage_blocked"
    assert result["injury_triage"]["mode"] == NEEDS_REVIEW


def test_acl_rupture_routes_to_restricted_rehab_only():
    parsed = PlanInput.from_payload(_payload_with_injury("right knee acl rupture during scramble"))
    triage = triage_injuries(parsed)

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert "acl_tear" in triage.matched_high_risk_categories


def test_user_input_sentence_with_torn_variant_routes_restricted():
    parsed = PlanInput.from_payload(_payload_with_injury("right knee feels unstable and acl torn in training"))
    triage = triage_injuries(parsed)

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert "acl_tear" in triage.matched_high_risk_categories


@pytest.mark.parametrize(
    ("injury_text", "expected_category"),
    [
        ("acl", "acl_tear"),
        ("acl tear", "acl_tear"),
        ("acl torn", "acl_tear"),
        ("acl reconstruction", "acl_tear"),
        ("ruptured ligament", "complete_ligament_tear"),
        ("torn ligament", "complete_ligament_tear"),
        ("tendon rupture", "tendon_rupture_or_avulsion"),
        ("torn tendon", "tendon_rupture_or_avulsion"),
        ("dislocating shoulder", "dislocation"),
        ("subluxation", "dislocation"),
        ("partial dislocation", "dislocation"),
        ("grade 3 MCL", "complete_ligament_tear"),
        ("grade 3 ligament tear", "complete_ligament_tear"),
    ],
)
def test_structural_dislocation_phrases_route_restricted_before_rehab_typing(
    injury_text: str,
    expected_category: str,
):
    parsed = PlanInput.from_payload(_payload_with_injury(injury_text))
    triage = triage_injuries(parsed)

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert expected_category in triage.matched_high_risk_categories


def test_muscle_rupture_routes_to_restricted_rehab_only_via_structural_severe_signal():
    parsed = PlanInput.from_payload(_payload_with_injury("muscle rupture"))
    triage = triage_injuries(parsed)

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert "scored_structural_severe_signal" in triage.routing_reasons


@pytest.mark.parametrize(
    "injury_text",
    [
        "old ACL surgery",
        "ACL rehab history",
        "post ACL, now cleared",
    ],
)
def test_acl_history_or_cleared_language_does_not_overfire(injury_text: str):
    parsed = PlanInput.from_payload(_payload_with_injury(injury_text))
    triage = triage_injuries(parsed)

    assert triage.mode == FULL_PLAN
    assert "acl_tear" not in triage.matched_high_risk_categories


@pytest.mark.parametrize(
    "injury_text",
    [
        "old tendon rupture, now healed",
        "history of shoulder dislocation, now cleared",
        "prior grade 3 ligament tear years ago, fully recovered",
    ],
)
def test_history_only_structural_language_does_not_overfire(injury_text: str):
    parsed = PlanInput.from_payload(_payload_with_injury(injury_text))
    triage = triage_injuries(parsed)

    assert triage.mode == FULL_PLAN
    assert not {
        "tendon_rupture_or_avulsion",
        "dislocation",
        "complete_ligament_tear",
    }.intersection(set(triage.matched_high_risk_categories))


def test_history_word_boundary_prevents_false_positive_history_detection():
    parsed = PlanInput.from_payload(_payload_with_injury("told about shoulder dislocation but pain today"))
    triage = triage_injuries(parsed)

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert "dislocation" in triage.matched_high_risk_categories


def test_current_concern_overrides_resolution_markers_in_same_chunk():
    parsed = PlanInput.from_payload(_payload_with_injury("old tendon rupture healed but pain today"))
    triage = triage_injuries(parsed)

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert "tendon_rupture_or_avulsion" in triage.matched_high_risk_categories


def test_history_of_acl_tear_without_current_symptoms_stays_full_plan():
    parsed = PlanInput.from_payload(_payload_with_injury("history of ACL tear"))
    triage = triage_injuries(parsed)

    assert triage.mode == FULL_PLAN
    assert "acl_tear" not in triage.matched_high_risk_categories


def test_resolved_history_does_not_suppress_new_serious_rupture_in_same_payload():
    # A resolution marker on an old injury must not down-gate a separate current
    # serious injury named in the same input.
    parsed = PlanInput.from_payload(
        _payload_with_injury("old ankle fracture fully healed, new Achilles rupture today")
    )
    triage = triage_injuries(parsed)

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert triage.should_block_stage2 is True


def test_cleared_history_does_not_suppress_new_hamstring_rupture():
    parsed = PlanInput.from_payload(
        _payload_with_injury("history of shoulder dislocation cleared, hamstring rupture yesterday")
    )
    triage = triage_injuries(parsed)

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert triage.should_block_stage2 is True


def test_recovered_rupture_with_current_swelling_and_pain_does_not_full_plan():
    parsed = PlanInput.from_payload(
        _payload_with_injury("old tendon rupture fully recovered, current swelling and pain")
    )
    triage = triage_injuries(parsed)

    assert triage.mode != FULL_PLAN
    assert triage.should_block_stage2 is True


def test_resolved_structural_card_with_separate_active_high_severity_card_blocks():
    # A first guided card that is old-and-cleared must not down-gate a SECOND,
    # active high-severity/worsening guided injury in the same payload.
    payload = _payload_with_injury("")
    payload["guided_injuries"] = [
        {
            "area": "old shin",
            "injury_type": "fracture",
            "timeframe": "old_cleared",
            "cleared": "yes",
            "severity": "low",
            "trend": "stable",
        },
        {"area": "left knee", "severity": "high", "trend": "worsening", "notes": "pain"},
    ]
    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode != FULL_PLAN
    assert triage.should_block_stage2 is True


def test_resolved_free_text_with_active_high_severity_guided_card_blocks():
    payload = _payload_with_injury("old ACL tear fully healed")
    payload["guided_injury"] = {
        "area": "left knee",
        "severity": "high",
        "trend": "worsening",
        "notes": "pain",
    }
    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode != FULL_PLAN
    assert triage.should_block_stage2 is True


def test_achilles_rupture_routes_to_restricted_rehab_only():
    parsed = PlanInput.from_payload(_payload_with_injury("felt pop then achilles rupture while sprinting"))
    triage = triage_injuries(parsed)

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert "achilles_rupture" in triage.matched_high_risk_categories


def test_full_thickness_rotator_cuff_tear_routes_to_restricted_rehab_only():
    parsed = PlanInput.from_payload(_payload_with_injury("MRI showed full-thickness rotator cuff tear"))
    triage = triage_injuries(parsed)

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert "full_thickness_rotator_cuff_tear" in triage.matched_high_risk_categories


def test_negated_severe_phrases_do_not_trigger_blocking_by_themselves():
    parsed = PlanInput.from_payload(
        _payload_with_injury("no fracture, ACL intact, not a concussion, ruled out dislocation")
    )
    triage = triage_injuries(parsed)

    assert triage.mode == FULL_PLAN
    assert triage.should_block_stage2 is False


def test_guided_structural_note_is_retained_and_used_for_triage():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "left ankle",
        "severity": "high",
        "trend": "stable",
        "notes": "suspected tendon rupture post-op follow up",
    }

    parsed = PlanInput.from_payload(payload)
    assert "tendon rupture" in (parsed.parsed_injuries[0].get("original_phrase") or "").lower()

    triage = triage_injuries(parsed)
    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert "tendon_rupture_or_avulsion" in triage.matched_high_risk_categories


def test_not_a_concussion_does_not_route_to_medical_hold():
    parsed = PlanInput.from_payload(_payload_with_injury("not a concussion, mild soreness only"))
    triage = triage_injuries(parsed)

    assert triage.mode == FULL_PLAN


def test_pcl_tear_routes_to_restricted_rehab_only():
    parsed = PlanInput.from_payload(_payload_with_injury("MRI confirms PCL tear after knee trauma"))
    triage = triage_injuries(parsed)

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert "pcl_tear" in triage.matched_high_risk_categories


def test_patellar_tendon_rupture_routes_to_restricted_rehab_only():
    parsed = PlanInput.from_payload(_payload_with_injury("acute patellar tendon rupture while jumping"))
    triage = triage_injuries(parsed)

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert "patellar_tendon_rupture" in triage.matched_high_risk_categories


def test_pneumothorax_routes_to_medical_hold():
    parsed = PlanInput.from_payload(_payload_with_injury("small pneumothorax after hard body shot"))
    triage = triage_injuries(parsed)

    assert triage.mode == MEDICAL_HOLD
    assert "pneumothorax" in triage.matched_high_risk_categories


def test_vomiting_after_head_impact_routes_to_medical_hold():
    parsed = PlanInput.from_payload(_payload_with_injury("vomiting after head impact in sparring"))
    triage = triage_injuries(parsed)

    assert triage.mode == MEDICAL_HOLD
    assert "vomiting_after_head_impact" in triage.red_flags


def test_non_weight_bearing_and_boot_or_crutches_route_to_restricted_rehab_only():
    parsed = PlanInput.from_payload(
        _payload_with_injury("currently non-weight-bearing, in a walking boot, and on crutches")
    )
    triage = triage_injuries(parsed)

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert "clinician_restriction_signal" in triage.routing_reasons


def test_negated_new_severe_phrases_do_not_trigger_blocking():
    parsed = PlanInput.from_payload(
        _payload_with_injury("no PCL tear, ruled out pneumothorax, not vomiting, ACL intact, no fracture seen")
    )
    triage = triage_injuries(parsed)

    assert triage.mode == FULL_PLAN


def test_high_worsening_vague_guided_injury_routes_to_needs_review():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "knee",
        "severity": "high",
        "trend": "worsening",
        "notes": "pain",
    }

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert triage.should_block_stage2 is True


def test_high_stable_vague_guided_injury_routes_to_needs_review():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "shoulder",
        "severity": "high",
        "trend": "stable",
        "notes": "pain",
    }

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode == NEEDS_REVIEW
    assert triage.should_block_stage2 is True


def test_moderate_worsening_vague_guided_injury_routes_to_needs_review():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "ankle",
        "severity": "moderate",
        "trend": "worsening",
        "notes": "pain",
    }

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode == NEEDS_REVIEW
    assert triage.should_block_stage2 is True


def test_low_worsening_vague_guided_injury_routes_to_needs_review():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "elbow",
        "severity": "low",
        "trend": "worsening",
        "notes": "sore",
    }

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode == NEEDS_REVIEW
    assert triage.should_block_stage2 is True


def test_high_stable_acl_rupture_remains_restricted_rehab_only():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "right knee",
        "severity": "high",
        "trend": "stable",
        "notes": "confirmed acl rupture",
    }

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert triage.should_block_stage2 is True


def test_high_worsening_with_chest_breathing_red_flags_routes_to_medical_hold():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "left chest",
        "severity": "high",
        "trend": "worsening",
        "notes": "chest pain and shortness of breath after impact",
    }

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode == MEDICAL_HOLD
    assert triage.should_block_stage2 is True


def test_moderate_stable_mild_non_structural_case_can_reach_full_plan():
    payload = _payload_with_injury("mild shoulder soreness after mitt work")
    payload["guided_injury"] = {
        "area": "left shoulder",
        "severity": "moderate",
        "trend": "stable",
        "notes": "mild soreness after heavy bag, no restrictions",
    }

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode == FULL_PLAN
    assert triage.should_block_stage2 is False


def test_moderate_improving_guided_injury_does_not_block_planning():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "Right knee",
        "severity": "moderate",
        "trend": "improving",
        "avoid": "",
        "notes": "",
    }

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode == FULL_PLAN
    assert triage.should_block_stage2 is False


def test_second_guided_injury_card_can_trigger_high_worsening_triage_gate():
    payload = _payload_with_injury("")
    payload["guided_injuries"] = [
        {
            "area": "Right wrist",
            "severity": "low",
            "trend": "stable",
            "avoid": "",
            "notes": "",
        },
        {
            "area": "Left knee",
            "severity": "high",
            "trend": "worsening",
            "avoid": "",
            "notes": "",
        },
    ]

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert triage.should_block_stage2 is True
    assert "combo_gate:high_worsening" in triage.routing_reasons


def test_multi_card_high_improving_does_not_shadow_moderate_worsening_gate():
    payload = _payload_with_injury("")
    payload["guided_injuries"] = [
        {
            "area": "Right shoulder",
            "severity": "high",
            "trend": "improving",
            "avoid": "",
            "notes": "",
        },
        {
            "area": "Left knee",
            "severity": "moderate",
            "trend": "worsening",
            "avoid": "",
            "notes": "",
        },
    ]

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode == NEEDS_REVIEW
    assert triage.should_block_stage2 is True
    assert "combo_gate:moderate_worsening" in triage.routing_reasons


def test_multi_card_high_severity_without_trend_routes_to_needs_review():
    payload = _payload_with_injury("")
    payload["guided_injuries"] = [
        {
            "area": "Right wrist",
            "severity": "low",
            "trend": "stable",
            "avoid": "",
            "notes": "",
        },
        {
            "area": "Left knee",
            "severity": "high",
            "trend": "",
            "avoid": "",
            "notes": "",
        },
    ]

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert "guided_injury:high_severity" in triage.routing_reasons
    assert "combo_gate:high_trend_missing" in triage.routing_reasons
    assert triage.mode == NEEDS_REVIEW
    assert triage.should_block_stage2 is True


def test_high_severity_missing_trend_with_function_loss_routes_to_restricted_rehab_only():
    payload = _payload_with_injury("left knee is locked")
    payload["guided_injury"] = {
        "area": "left knee",
        "severity": "high",
        "trend": "",
        "notes": "locked knee",
    }

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert "combo_gate:high_trend_missing" in triage.routing_reasons
    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert triage.should_block_stage2 is True


def test_second_guided_card_notes_feed_breathing_red_flag_logic():
    payload = _payload_with_injury("")
    payload["guided_injuries"] = [
        {
            "area": "Right wrist",
            "severity": "low",
            "trend": "stable",
            "avoid": "",
            "notes": "",
        },
        {
            "area": "Left rib",
            "severity": "moderate",
            "trend": "stable",
            "avoid": "",
            "notes": "pain when breathing deeply after impact",
        },
    ]

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.should_block_stage2 is True
    assert "breathing_pain" in triage.red_flags
    assert "guided_injury:breathing_symptoms" in triage.routing_reasons


def test_second_guided_card_avoid_high_load_signal_is_seen():
    payload = _payload_with_injury("")
    payload["guided_injuries"] = [
        {
            "area": "Right wrist",
            "severity": "low",
            "trend": "stable",
            "avoid": "",
            "notes": "",
        },
        {
            "area": "Left shoulder",
            "severity": "moderate",
            "trend": "stable",
            "avoid": "contact sparring",
            "notes": "",
        },
    ]

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert "guided_injury:avoid_high_load" in triage.routing_reasons


def test_parse_guided_note_tags_handles_multiple_tags_and_spacing():
    tags = parse_guided_note_tags(
        " [red_flags: vomiting , severe_headache ] [chest_symptoms: shortness_of_breath,coughing_blood] "
    )
    assert tags["red_flags"] == {"vomiting", "severe_headache"}
    assert tags["chest_symptoms"] == {"shortness_of_breath", "coughing_blood"}


def test_parse_guided_note_tags_ignores_malformed_or_unknown_shapes():
    assert parse_guided_note_tags("[chest_symptoms] [random:abc]") == {"random": {"abc"}}


def test_head_impact_tagged_red_flags_route_like_natural_language():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {"injury_type": "head_impact", "notes": "[red_flags:vomiting,confusion]"}
    triage = triage_injuries(PlanInput.from_payload(payload))
    assert triage.mode == MEDICAL_HOLD
    assert "vomiting_after_head_impact" in triage.red_flags
    assert "confusion" in triage.red_flags
    assert "tagged_note:red_flags:vomiting" in triage.routing_reasons


def test_chest_breathing_tagged_notes_activate_red_flags_and_hold():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {"injury_type": "chest_breathing", "notes": "[chest_symptoms:shortness_of_breath,coughing_blood]"}
    triage = triage_injuries(PlanInput.from_payload(payload))
    assert "shortness_of_breath" in triage.red_flags
    assert triage.mode == MEDICAL_HOLD
    assert "tagged_note:chest_symptoms:shortness_of_breath" in triage.routing_reasons


def test_nerve_tagged_mixed_and_worsening_does_not_silently_full_plan():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "injury_type": "nerve_symptoms",
        "trend": "worsening",
        "notes": "[nerve_symptoms:type_mixed]",
    }
    triage = triage_injuries(PlanInput.from_payload(payload))
    assert {"numbness", "tingling", "weakness"}.issubset(set(triage.red_flags))
    assert triage.mode != FULL_PLAN


def test_dislocation_recurrent_or_unresolved_tags_do_not_silently_full_plan():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {"injury_type": "dislocation", "notes": "[dislocation:recurrent_yes,relocated_no]"}
    triage = triage_injuries(PlanInput.from_payload(payload))
    assert triage.mode != FULL_PLAN
    assert "tagged_note:dislocation:recurrent_yes" in triage.routing_reasons


def test_dislocation_relocated_yes_recurrent_no_can_be_full_plan_when_cleared():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "injury_type": "dislocation",
        "timeframe": "old_cleared",
        "cleared": "yes",
        "notes": "[dislocation:relocated_yes,recurrent_no]",
    }
    triage = triage_injuries(PlanInput.from_payload(payload))
    assert triage.mode == FULL_PLAN


def test_old_cleared_fracture_card_does_not_suppress_current_fracture_from_other_card():
    payload = _payload_with_injury("")
    payload["guided_injuries"] = [
        {
            "area": "old cleared ankle fracture",
            "injury_type": "fracture",
            "timeframe": "old_cleared",
            "cleared": "yes",
            "notes": "Old fracture, fully cleared.",
        },
        {
            "area": "broken right wrist",
            "injury_type": "fracture",
            "severity": "high",
            "trend": "stable",
            "notes": "Current injury.",
        },
    ]

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode != FULL_PLAN
    assert "fracture" in triage.matched_high_risk_categories


def test_single_old_cleared_fracture_only_does_not_force_restricted_rehab():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "old cleared ankle fracture",
        "injury_type": "fracture",
        "timeframe": "old_cleared",
        "cleared": "yes",
        "notes": "Old fracture, fully cleared.",
    }

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode == FULL_PLAN
    assert "fracture" not in triage.matched_high_risk_categories


def test_collect_guided_card_evidence_uses_parsed_entries_without_duplicating_first_card():
    payload = _payload_with_injury("")
    payload["guided_injuries"] = [
        {
            "area": "Right wrist",
            "severity": "low",
            "trend": "stable",
            "avoid": "",
            "notes": "first",
        },
        {
            "area": "Left knee",
            "severity": "moderate",
            "trend": "stable",
            "avoid": "contact",
            "notes": "second",
        },
    ]

    parsed = PlanInput.from_payload(payload)
    cards = _collect_guided_card_evidence(parsed)

    assert len(cards) == 2

    assert cards[0].severity == "low"
    assert cards[0].trend == "stable"
    assert cards[0].avoid == ""
    assert cards[0].notes == "first"

    assert cards[1].severity == "moderate"
    assert cards[1].trend == "stable"
    assert cards[1].avoid == "contact"
    assert cards[1].notes == "second"


def test_low_stable_recent_structural_history_routes_to_needs_review():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "right shin",
        "severity": "low",
        "trend": "stable",
        "notes": "broke it last month",
    }

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert triage.should_block_stage2 is True
    assert "guided_injury:card_area_context_broke_signal" in triage.routing_reasons


def test_guided_recent_negated_fracture_history_does_not_trigger_needs_review():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "right shin",
        "severity": "low",
        "trend": "stable",
        "notes": "no fracture in the last month, mild soreness only",
    }

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode == FULL_PLAN
    assert triage.should_block_stage2 is False
    assert "fracture" not in triage.matched_high_risk_categories
    assert "guided_injury:recent_structural_history_signal" not in triage.routing_reasons


def test_uncertainty_note_word_count_uses_per_card_words_not_separator_tokens():
    payload = _payload_with_injury("")
    payload["guided_injuries"] = [
        {
            "area": "Left shoulder",
            "severity": "moderate",
            "trend": "stable",
            "avoid": "",
            "notes": "ok",
        },
        {
            "area": "Right wrist",
            "severity": "low",
            "trend": "stable",
            "avoid": "",
            "notes": "fine",
        },
    ]

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode == NEEDS_REVIEW
    assert "combo_gate:moderate_stable_blocked" in triage.routing_reasons


def test_second_guided_card_structural_notes_are_used_for_triage_even_if_not_primary_card():
    payload = _payload_with_injury("")
    payload["guided_injuries"] = [
        {
            "area": "left shoulder",
            "severity": "low",
            "trend": "stable",
            "notes": "tight after pads",
        },
        {
            "area": "right ankle",
            "severity": "moderate",
            "trend": "stable",
            "notes": "broke it last week",
        },
    ]

    parsed = PlanInput.from_payload(payload)
    triage = triage_injuries(parsed)

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert triage.should_block_stage2 is True
    assert "fracture" in triage.matched_high_risk_categories


def test_guided_card_broke_it_uses_its_own_location_context_not_zip_alignment():
    payload = _payload_with_injury("")
    payload["guided_injuries"] = [
        {
            "area": "Right wrist",
            "severity": "low",
            "trend": "stable",
            "avoid": "",
            "notes": "tight only",
        },
        {
            "area": "Left ankle",
            "severity": "moderate",
            "trend": "stable",
            "avoid": "",
            "notes": "broke it last week",
        },
    ]

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert triage.should_block_stage2 is True
    assert "fracture" in triage.matched_high_risk_categories
    assert "guided_injury:card_area_context_broke_signal" in triage.routing_reasons


def test_guided_injury_note_with_broke_routes_to_restricted_rehab():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {
        "area": "right ankle",
        "severity": "moderate",
        "trend": "stable",
        "notes": "broke it last week",
    }

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert triage.should_block_stage2 is True

def test_negated_concussion_red_flags_do_not_trigger_medical_hold():
    parsed = PlanInput.from_payload(
        _payload_with_injury(
            "head impact in sparring, no memory loss, no blurred vision, no loss of consciousness, denies vomiting"
        )
    )
    triage = triage_injuries(parsed)

    assert "amnesia_or_memory_loss" not in triage.red_flags
    assert "blurred_or_double_vision" not in triage.red_flags
    assert "loss_of_consciousness" not in triage.red_flags
    assert "vomiting_after_head_impact" not in triage.red_flags
    assert triage.mode != MEDICAL_HOLD


def test_absent_neurologic_concussion_phrases_do_not_trigger_red_flags():
    parsed = PlanInput.from_payload(
        _payload_with_injury(
            "after a clean spar stayed awake the whole time, vision is normal, recall is normal, without severe headache"
        )
    )
    triage = triage_injuries(parsed)

    assert "loss_of_consciousness" not in triage.red_flags
    assert "blurred_or_double_vision" not in triage.red_flags
    assert "amnesia_or_memory_loss" not in triage.red_flags
    assert "severe_headache_after_head_impact" not in triage.red_flags


def test_negation_is_local_for_mixed_body_parts_numbness():
    parsed = PlanInput.from_payload(_payload_with_injury("No numbness in my left arm, but numbness in my right hand."))
    triage = triage_injuries(parsed)
    assert "numbness" in triage.red_flags


def test_negation_is_local_for_time_contrast_chest_pain():
    parsed = PlanInput.from_payload(_payload_with_injury("No chest pain yesterday, but chest pain today."))
    triage = triage_injuries(parsed)
    assert "chest_pain" in triage.red_flags


def test_negation_is_local_for_mixed_bear_weight_by_side():
    parsed = PlanInput.from_payload(
        _payload_with_injury("Can bear weight on the left ankle, cannot bear weight on the right ankle.")
    )
    triage = triage_injuries(parsed)
    assert "cannot_bear_weight" in triage.red_flags


def test_negation_is_local_for_time_contrast_weakness():
    parsed = PlanInput.from_payload(_payload_with_injury("No weakness before training, weakness after sparring."))
    triage = triage_injuries(parsed)
    assert "weakness" in triage.red_flags


def test_negated_head_impact_flags_remain_suppressed_without_positive_contrast():
    parsed = PlanInput.from_payload(
        _payload_with_injury("No vomiting, no confusion, no severe headache after head impact.")
    )
    triage = triage_injuries(parsed)
    assert "vomiting_after_head_impact" not in triage.red_flags
    assert "confusion" not in triage.red_flags
    assert "severe_headache_after_head_impact" not in triage.red_flags


def test_head_impact_vomiting_detected_after_contrast_clause():
    parsed = PlanInput.from_payload(_payload_with_injury("No vomiting at first, but vomited later after head impact."))
    triage = triage_injuries(parsed)
    assert "vomiting_after_head_impact" in triage.red_flags
