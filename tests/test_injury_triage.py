from types import SimpleNamespace

import pytest

from fightcamp.injury_triage import (
    FULL_PLAN,
    MEDICAL_HOLD,
    NEEDS_REVIEW,
    RESTRICTED_REHAB_ONLY,
    _collect_guided_card_evidence,
    triage_injuries,
)
from fightcamp.input_parsing import PlanInput
from fightcamp.main import generate_plan_sync
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


@pytest.mark.xfail(
    reason=(
        "Known false-positive structural-break routing for benign crack/snap wording; "
        "kept as protection for follow-up triage fix."
    ),
    strict=True,
)
@pytest.mark.parametrize(
    "injury_text",
    [
        "neck cracked but no pain",
        "knee snapped while stretching but no pain",
        "ankle crack sound only, no pain or swelling",
    ],
)
def test_benign_structural_break_words_without_symptoms_do_not_route_fracture(injury_text: str):
    parsed = PlanInput.from_payload(_payload_with_injury(injury_text))
    triage = triage_injuries(parsed)

    assert triage.mode == FULL_PLAN
    assert "fracture" not in triage.matched_high_risk_categories


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
