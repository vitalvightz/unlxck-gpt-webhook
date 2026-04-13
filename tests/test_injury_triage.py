import json
from pathlib import Path

import pytest

from fightcamp.injury_triage import (
    FULL_PLAN,
    MEDICAL_HOLD,
    NEEDS_REVIEW,
    RESTRICTED_REHAB_ONLY,
    triage_injuries,
)
from fightcamp.input_parsing import PlanInput
from fightcamp.main import generate_plan_sync


def _base_payload() -> dict:
    return json.loads((Path(__file__).resolve().parents[1] / "test_data.json").read_text(encoding="utf-8"))


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


def test_fracture_routes_to_restricted_rehab_only_and_matches_existing_signals():
    parsed = PlanInput.from_payload(
        _payload_with_injury("right ankle fracture with worsening swelling and cannot bear weight")
    )
    triage = triage_injuries(parsed)

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert triage.should_block_stage2 is True
    assert "urgent_fracture" in triage.urgent_flags
    assert triage.sparring_risk_band in {"red", "black"}


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


def test_acl_rupture_routes_to_restricted_rehab_only():
    parsed = PlanInput.from_payload(_payload_with_injury("right knee acl rupture during scramble"))
    triage = triage_injuries(parsed)

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert "acl_tear" in triage.matched_high_risk_categories


@pytest.mark.parametrize(
    ("injury_text", "expected_category"),
    [
        ("acl", "acl_tear"),
        ("acl tear", "acl_tear"),
        ("acl reconstruction", "acl_tear"),
        ("ruptured ligament", "complete_ligament_tear"),
        ("tendon rupture", "tendon_rupture_or_avulsion"),
        ("dislocating shoulder", "dislocation"),
        ("subluxation", "dislocation"),
        ("partial dislocation", "dislocation"),
        ("grade 3 MCL", "complete_ligament_tear"),
        ("grade 3 ligament tear", "complete_ligament_tear"),
    ],
)
def test_structural_dislocation_phrases_route_restricted_before_rehab_typing(
    injury_text: str, expected_category: str
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
    payload["guided_injury"] = {"area": "knee", "severity": "high", "trend": "worsening", "notes": "pain"}

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode == NEEDS_REVIEW
    assert triage.should_block_stage2 is True


def test_high_stable_vague_guided_injury_routes_to_needs_review():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {"area": "shoulder", "severity": "high", "trend": "stable", "notes": "pain"}

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode == NEEDS_REVIEW
    assert triage.should_block_stage2 is True


def test_moderate_worsening_vague_guided_injury_routes_to_needs_review():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {"area": "ankle", "severity": "moderate", "trend": "worsening", "notes": "pain"}

    triage = triage_injuries(PlanInput.from_payload(payload))

    assert triage.mode == NEEDS_REVIEW
    assert triage.should_block_stage2 is True


def test_low_worsening_vague_guided_injury_routes_to_needs_review():
    payload = _payload_with_injury("")
    payload["guided_injury"] = {"area": "elbow", "severity": "low", "trend": "worsening", "notes": "sore"}

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
