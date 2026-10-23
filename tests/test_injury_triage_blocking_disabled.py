import pytest

from api.generation.triage import should_skip_stage2
from fightcamp.injury_triage import MEDICAL_HOLD, injury_triage_blocking_enabled, triage_injuries
from fightcamp.input_parsing import PlanInput
from fightcamp.main import generate_plan_sync
from support import _build_request

pytestmark = pytest.mark.triage_blocking_default

_CONCUSSION = "suspected concussion with headache after sparring"


def _payload_with_injury(injury_text: str) -> dict:
    data = _build_request().to_payload()
    for field in data["data"]["fields"]:
        if field.get("label") == "Any injuries or areas you need to work around?":
            field["value"] = injury_text
            break
    return data


def test_blocking_is_off_by_default():
    assert injury_triage_blocking_enabled() is False


@pytest.mark.parametrize("raw", ["1", "true", "YES", " on "])
def test_blocking_can_be_enabled_for_coaches(monkeypatch, raw: str):
    monkeypatch.setenv("UNLXCK_INJURY_TRIAGE_BLOCKING", raw)
    assert injury_triage_blocking_enabled() is True


def test_medical_hold_injury_still_produces_a_plan():
    payload = _payload_with_injury(_CONCUSSION)
    assert triage_injuries(PlanInput.from_payload(payload)).mode == MEDICAL_HOLD

    result = generate_plan_sync(payload)

    assert result.get("status") not in {"triage_blocked", "medical_hold", "needs_review", "restricted_rehab_only"}
    assert result["stage2_payload"] is not None
    override = result["why_log"]["injury_triage_resume_override"]
    assert override["bypassed_blocking"] is True
    assert override["blocking_disabled"] is True
    assert override["triage_mode"] == MEDICAL_HOLD
    assert result["why_log"]["injury_triage_original"]["mode"] == MEDICAL_HOLD
    assert should_skip_stage2(result) is False


@pytest.mark.parametrize(
    "stage1_result",
    [
        {"status": "triage_blocked"},
        {"injury_triage": {"should_block_stage2": True}},
        {"why_log": {"injury_triage": {"mode": "medical_hold"}}},
    ],
)
def test_stage2_is_never_skipped_for_triage(stage1_result: dict):
    assert should_skip_stage2(stage1_result) is False


def test_stage2_skip_still_applies_when_blocking_enabled(monkeypatch):
    monkeypatch.setenv("UNLXCK_INJURY_TRIAGE_BLOCKING", "1")
    assert should_skip_stage2({"status": "triage_blocked"}) is True
