from __future__ import annotations

from typing import Any

from fightcamp.main import generate_plan_sync

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
        "stage1_conditioning_block_started",
        "stage1_conditioning_block_finished",
        "strength_scored",
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
    assert "stage1_blocks_generation_finished" in codes
    assert "plan_drafted" in codes
    assert "stage1_planner_timeout" not in codes


def test_stage1_module_start_visible_when_module_hangs(monkeypatch):
    from fightcamp import plan_pipeline_blocks as blocks_module

    def _hang_conditioning(_context):
        raise TimeoutError("simulated conditioning hang for diagnostics")

    monkeypatch.setattr(blocks_module, "_generate_conditioning_blocks", _hang_conditioning)
    captured: list[str] = []

    def _callback(code: str, _label: str, _detail: str, _meta: dict[str, Any]) -> None:
        captured.append(code)

    result = generate_plan_sync(_payload(), progress_callback=_callback)
    assert result.get("status") == "invalid_input"
    assert "stage1_conditioning_block_started" in captured
    assert "stage1_conditioning_block_finished" not in captured
