"""The compact Stage 2 handoff must lose duplication, never meaning.

Size is not the success criterion. Each test below pins one fact that has to
survive the compaction, and the parity test proves the removed material was
byte-identical to a copy the packet still carries.
"""

from __future__ import annotations

import datetime
import json

import pytest

from fightcamp.stage2_finalizer_packet import build_stage2_finalizer_packet
from fightcamp.stage2_payload import build_stage2_llm_planning_brief
from support import _build_request


@pytest.fixture(scope="module")
def generated() -> dict:
    generate_plan_sync = pytest.importorskip("fightcamp.main").generate_plan_sync
    fight_date = (datetime.date.today() + datetime.timedelta(days=56)).isoformat()
    request = _build_request(
        {
            "fight_date": fight_date,
            "hard_sparring_days": ["Tuesday", "Thursday"],
            "support_work_days": ["Wednesday"],
            "training_availability": [
                "Monday", "Tuesday", "Wednesday", "Thursday", "Saturday",
            ],
            "weekly_training_frequency": 5,
        }
    ).to_payload()
    request["random_seed"] = 3
    return generate_plan_sync(request)


@pytest.fixture(scope="module")
def packet(generated) -> dict:
    brief = build_stage2_llm_planning_brief(generated["planning_brief"])
    return build_stage2_finalizer_packet(
        stage2_payload=generated["stage2_payload"], planning_brief=brief
    )


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def test_progression_keeps_its_unique_week_intent(packet):
    """Only the duplicated calendar fields go; the intent fields all stay."""
    weeks = packet["selected_plan"]["week_by_week_progression"]["weeks"]
    assert weeks
    for week in weeks:
        assert "calendar_days" not in week
        assert "intentional_compression" not in week
    first = weeks[0]
    for required in (
        "phase",
        "stage_objective",
        "load_bias",
        "build",
        "protect",
        "deprioritize",
        "must_keep",
        "drop_order_if_thin",
        "conditioning_sequence",
        "resolved_rule_state",
        "session_counts",
    ):
        assert required in first, f"progression lost unique field {required!r}"


def test_removed_progression_fields_are_still_present_via_the_role_map(generated, packet):
    """Parity: what was dropped is byte-identical to what the packet still carries."""
    raw = generated["planning_brief"].get("week_by_week_progression") or {}
    role_map_weeks = {
        week.get("week_index"): week
        for week in packet["selected_plan"]["weekly_role_map"]["weeks"]
    }
    checked = 0
    for week in raw.get("weeks") or []:
        surviving = role_map_weeks.get(week.get("week_index"))
        if surviving is None:
            continue
        for field in ("calendar_days", "intentional_compression"):
            if field not in week:
                continue
            assert _canonical(week[field]) == _canonical(surviving.get(field)), (
                f"week {week.get('week_index')} {field} was NOT a duplicate"
            )
            checked += 1
    assert checked, "parity test proved nothing — no duplicated fields were compared"


def test_per_week_sparring_plan_is_not_dropped(packet):
    """hard_sparring_plan differs between the two objects in some weeks, so it stays."""
    weeks = packet["selected_plan"]["week_by_week_progression"]["weeks"]
    assert any("hard_sparring_plan" in week for week in weeks)


def test_late_fight_shared_contract_is_stated_once(packet):
    tail = packet["selected_plan"].get("late_fight_tail_handoff") or {}
    segments = tail.get("segments") or []
    if len(segments) < 2:
        pytest.skip("camp has no multi-segment late-fight tail")

    shared = tail.get("shared_render_contract") or ""
    assert shared.strip(), "multi-segment tail must hoist its common contract"
    shared_lines = {line for line in shared.splitlines() if line.strip()}
    for segment in segments:
        contract_lines = {
            line for line in str(segment.get("render_contract") or "").splitlines()
        }
        assert not (shared_lines & contract_lines), (
            f"{segment.get('stage_key')} still repeats the shared contract"
        )


def test_every_late_fight_rule_survives_the_hoist(generated, packet):
    """Parity: shared + per-segment lines reconstruct each original contract."""
    from fightcamp.stage2_payload_late_fight import _handoff_mode_instructions

    tail = packet["selected_plan"].get("late_fight_tail_handoff") or {}
    segments = tail.get("segments") or []
    if len(segments) < 2:
        pytest.skip("camp has no multi-segment late-fight tail")
    shared_lines = {
        line for line in (tail.get("shared_render_contract") or "").splitlines()
    }
    for segment in segments:
        original = _handoff_mode_instructions(str(segment.get("payload_mode") or ""))
        original_lines = {line for line in original.splitlines() if line.strip()}
        delivered = shared_lines | {
            line
            for line in str(segment.get("render_contract") or "").splitlines()
            if line.strip()
        }
        missing = original_lines - delivered
        assert not missing, (
            f"{segment.get('stage_key')} lost {len(missing)} contract line(s)"
        )


def test_the_model_is_told_the_shared_contract_applies_everywhere(packet):
    tail = packet["selected_plan"].get("late_fight_tail_handoff") or {}
    if not (tail.get("shared_render_contract") or "").strip():
        pytest.skip("no shared contract for this camp")
    rules = " ".join(str(rule) for rule in packet.get("hard_rules") or [])
    assert "shared_render_contract" in rules


def test_selected_work_and_doses_are_untouched(generated, packet):
    """Compaction touched serialization only: every assignment still reaches Stage 2."""
    source_names = {
        str(item.get("name"))
        for week in (generated["planning_brief"].get("weekly_role_map") or {}).get("weeks") or []
        for role in week.get("session_roles") or []
        for item in role.get("selected_exercise_assignments") or []
        if isinstance(item, dict) and item.get("name")
    }
    packet_names = {
        str(item.get("name"))
        for week in packet["selected_plan"]["weekly_role_map"]["weeks"]
        for role in week.get("session_roles") or []
        for item in role.get("selected_exercise_assignments") or []
        if isinstance(item, dict) and item.get("name")
    }
    assert source_names, "fixture must select exercises"
    assert source_names <= packet_names


def test_goal_preservation_and_priority_focus_survive(packet):
    selected = packet["selected_plan"]
    assert selected.get("goal_preservation")
    assert selected.get("priority_focus")
