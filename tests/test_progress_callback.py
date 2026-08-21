from __future__ import annotations

from typing import Any
import pytest

from fightcamp.main import generate_plan_sync

pytest.importorskip("fastapi")
from support import _build_request


def _payload() -> dict:
    return _build_request().to_payload()


def _collect_codes(payload: dict | None = None) -> list[str]:
    payload = payload or _payload()
    captured: list[tuple[str, str, str, dict[str, Any]]] = []

    def _callback(code: str, label: str, detail: str, meta: dict[str, Any]) -> None:
        captured.append((code, label, detail, meta))

    result = generate_plan_sync(payload, progress_callback=_callback)
    assert result.get("status") != "invalid_input", result
    return [code for code, _label, _detail, _meta in captured]


def test_progress_callback_emits_full_pipeline_milestones():
    codes = _collect_codes()

    expected_in_order = [
        "intake_received",
        "intake_parsed",
        "injury_triage_done",
        "banks_primed",
        "camp_brief_built",
        "stage1_blocks_generation_started",
        "stage1_strength_block_started",
        "stage1_strength_block_finished",
        "strength_scored",
        "stage1_conditioning_block_started",
        "stage1_conditioning_block_finished",
        "conditioning_scored",
        "rehab_support_built",
        "coach_review_done",
        "stage1_blocks_generation_finished",
        "plan_drafted",
        "stage2_handoff_ready",
    ]

    for code in expected_in_order:
        assert code in codes, f"missing milestone {code} in {codes}"

    positions = {code: codes.index(code) for code in expected_in_order}
    sorted_positions = sorted(positions.values())
    assert list(positions.values()) == sorted_positions, (
        f"milestones out of order: {codes}"
    )


def test_progress_callback_failure_does_not_break_generation():
    payload = _payload()

    def _broken_callback(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("callback failure must not propagate")

    result = generate_plan_sync(payload, progress_callback=_broken_callback)
    assert result.get("status") != "invalid_input"
    assert result.get("plan_text"), "plan_text should still be produced"


def test_progress_callback_optional_keeps_signature_compatible():
    # No callback supplied — should still work and return a plan.
    result = generate_plan_sync(_payload())
    assert result.get("status") != "invalid_input"
    assert result.get("plan_text")


def test_knee_instability_low_stable_emits_stage1_block_and_no_timeout():
    payload = _payload()
    payload["injuries"] = "Right knee is wobbly (low, stable). Type: instability"
    codes = _collect_codes(payload)
    assert "camp_brief_built" in codes
    assert "stage1_blocks_generation_started" in codes
    assert "stage1_strength_block_started" in codes
    assert "stage1_strength_block_finished" in codes
    assert "stage1_strength_phase_gpp_finished" in codes
    assert "stage1_strength_phase_spp_finished" in codes
    assert "stage1_conditioning_block_started" in codes
    assert "stage1_conditioning_phase_gpp_started" in codes
    assert "stage1_conditioning_phase_gpp_finished" in codes
    assert "stage1_conditioning_base_bank_score_started" in codes
    assert "stage1_conditioning_base_bank_score_finished" in codes
    assert "stage1_conditioning_style_bank_score_started" in codes
    assert "stage1_conditioning_style_bank_score_finished" in codes
    assert "stage1_conditioning_system_quota_fill_started" in codes
    assert "stage1_conditioning_system_quota_fill_finished" in codes
    assert "stage1_conditioning_deficit_fill_started" in codes
    assert "stage1_conditioning_deficit_fill_finished" in codes
    assert "stage1_conditioning_gas_tank_machine_bias_started" in codes
    assert "stage1_conditioning_gas_tank_machine_bias_finished" in codes
    assert "stage1_conditioning_style_taper_insertion_started" in codes
    assert "stage1_conditioning_style_taper_insertion_finished" in codes
    assert "stage1_conditioning_taper_plyometric_guarantee_started" in codes
    assert "stage1_conditioning_taper_plyometric_guarantee_finished" in codes
    assert "stage1_conditioning_skill_refinement_guarantee_started" in codes
    assert "stage1_conditioning_skill_refinement_guarantee_finished" in codes
    assert "stage1_conditioning_coordination_insertion_started" in codes
    assert "stage1_conditioning_coordination_insertion_finished" in codes
    assert "stage1_conditioning_pro_neck_guarantee_started" in codes
    assert "stage1_conditioning_pro_neck_guarantee_finished" in codes
    assert "stage1_conditioning_trim_extras_started" in codes
    assert "stage1_conditioning_trim_extras_finished" in codes
    assert "stage1_conditioning_candidate_reservoir_build_started" in codes
    assert "stage1_conditioning_candidate_reservoir_build_finished" in codes
    assert "stage1_conditioning_injury_safe_finalize_started" in codes
    assert "stage1_conditioning_injury_safe_finalize_finished" in codes
    assert "stage1_conditioning_energy_system_fallbacks_started" in codes
    assert "stage1_conditioning_energy_system_fallbacks_finished" in codes
    assert "stage1_conditioning_block_formatting_started" in codes
    assert "stage1_conditioning_block_formatting_finished" in codes
    assert "stage1_conditioning_block_finished" in codes
    assert "stage1_blocks_generation_finished" in codes
    assert "plan_drafted" in codes
    assert "stage1_planner_timeout" not in codes
    assert "stage1_strength_phase_gpp_started" in codes
    assert (
        "stage1_strength_context_started" in codes
        or "stage1_strength_candidate_pool_started" in codes
    )


def test_conditioning_direct_gpp_call_returns_expected_structure():
    from fightcamp import conditioning as conditioning_module

    normal_gpp_flags = {
        "phase": "GPP",
        "sport": "boxing",
        "key_goals": ["conditioning"],
        "weaknesses": ["gas tank"],
        "equipment": ["jump rope", "assault bike"],
        "injuries": [{"region": "knee", "severity": "low", "type": "instability"}],
        "fatigue": "moderate",
        "training_frequency": 3,
        "days_until_fight": 35,
    }
    result = conditioning_module.generate_conditioning_block(normal_gpp_flags)
    assert isinstance(result, tuple)
    assert len(result) == 6
    block_text, selected, why, grouped, missing, reservoir = result
    # The first element is the rendered conditioning block text, not a list.
    assert isinstance(block_text, str)
    assert isinstance(selected, list)
    assert isinstance(why, list)
    assert isinstance(grouped, dict)
    assert isinstance(missing, list)
    assert isinstance(reservoir, dict)


def test_strength_generation_does_not_require_context_progress_callback():
    payload = _payload()
    payload["injuries"] = "Right knee is wobbly (low, stable). Type: instability"
    codes = _collect_codes(payload)
    assert "stage1_strength_block_started" in codes
    assert "stage1_strength_block_finished" in codes
    assert "stage1_conditioning_block_started" in codes


def test_strength_substep_start_visible_when_substep_fails(monkeypatch):
    from fightcamp import strength as strength_module

    def _boom():
        raise RuntimeError("simulated strength candidate pool failure")

    monkeypatch.setattr(strength_module, "get_exercise_bank", _boom)
    captured: list[str] = []

    def _callback(code: str, _label: str, _detail: str, _meta: dict[str, Any]) -> None:
        captured.append(code)

    result = generate_plan_sync(_payload(), progress_callback=_callback)
    assert result.get("status") == "invalid_input"
    assert "stage1_strength_candidate_pool_started" in captured
    assert "stage1_strength_candidate_pool_finished" not in captured


def test_stage1_module_start_visible_when_module_hangs(monkeypatch):
    from fightcamp import plan_pipeline_blocks as blocks_module

    def _hang_conditioning(_context, **_kwargs):
        raise TimeoutError("simulated conditioning hang for diagnostics")

    monkeypatch.setattr(blocks_module, "_generate_conditioning_blocks", _hang_conditioning)
    captured: list[str] = []

    def _callback(code: str, _label: str, _detail: str, _meta: dict[str, Any]) -> None:
        captured.append(code)

    result = generate_plan_sync(_payload(), progress_callback=_callback)
    assert result.get("status") == "invalid_input"
    assert "stage1_conditioning_block_started" in captured
    assert "stage1_conditioning_block_finished" not in captured
