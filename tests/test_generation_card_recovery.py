"""Rejected AI cards must not leave a successfully published plan without an enhanced card."""
import asyncio
import json

from api.generation.stage2_runner import retry_structured_card_before_release
from api.structured_plan_generation import StructuredPlanOutcome


class Automator:
    # Conversion must never be repeated when the model already omitted work.
    async def _attempt_structured_plan(self, **_kwargs):
        raise AssertionError("Do not reroll a rejected model card")


def _result():
    return {
        "status": "publishable_with_flags",
        "final_plan_text": "### D-17 (Tuesday) — Strength\n- Heavy RDL → Broad Jump — 3x2",
        "planning_brief": json.dumps({"weekly_role_map": {"weeks": [{"session_roles": []}]}}),
        "stage2_validator_report": {
            "errors": [],
            "structured_plan": {
                "status": "invalid_fallback_used",
                "errors": ["planner_coverage: D-17 Heavy RDL → Broad Jump missing"],
            },
        },
    }


def test_audited_planner_card_recovers_rejected_model_membership(monkeypatch):
    import api.structured_plan_deterministic_fallback as builder
    import api.structured_plan_generation as generation

    expected = {"weeks": [{"days": [{"sessions": [{"blocks": [
        {"display_name": "Heavy RDL → Broad Jump"},
    ]}]}]}]}
    monkeypatch.setattr(builder, "build_deterministic_structured_plan",
                        lambda brief, plan_text=None: expected)
    def audit(card, **kwargs):
        assert card is expected
        assert kwargs["raw_markdown"] == _result()["final_plan_text"]
        return StructuredPlanOutcome(status="valid", structured_plan=expected, schema_version="1.0")
    monkeypatch.setattr(generation, "build_structured_plan_outcome", audit)

    milestones = []
    recovered = asyncio.run(retry_structured_card_before_release(
        stage2=Automator(), final_result=_result(),
        emit_milestone=lambda *a, **kwargs: milestones.append(a),
    ))
    assert recovered["structured_plan"] == expected
    report = recovered["stage2_validator_report"]["structured_plan"]
    assert report["status"] == "valid"
    assert "deterministic_recovery:" in report["warnings"][0]
    assert milestones and milestones[0][0] == "structured_card_retry_finished"


def test_invalid_deterministic_recovery_never_persists_an_unverified_card(monkeypatch):
    import api.structured_plan_deterministic_fallback as builder
    import api.structured_plan_generation as generation

    monkeypatch.setattr(builder, "build_deterministic_structured_plan",
                        lambda brief, plan_text=None: {"weeks": []})
    monkeypatch.setattr(generation, "build_structured_plan_outcome",
                        lambda card, **kwargs: StructuredPlanOutcome(
                            status="invalid_fallback_used", errors=["planner_coverage: missing work"]))
    original = _result()
    recovered = asyncio.run(retry_structured_card_before_release(
        stage2=Automator(), final_result=original, emit_milestone=lambda *a, **k: None,
    ))
    assert recovered is original
    assert recovered["stage2_validator_report"]["structured_plan"]["status"] == "invalid_fallback_used"
    assert "structured_plan" not in recovered
