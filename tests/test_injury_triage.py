import json
from pathlib import Path

from fightcamp.injury_triage import FULL_PLAN, MEDICAL_HOLD, RESTRICTED_REHAB_ONLY, triage_injuries
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

    assert triage.mode == RESTRICTED_REHAB_ONLY
    assert "breathing_pain" in triage.red_flags
    assert "guided_injury:worsening" in triage.routing_reasons


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
