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


# ---------------------------------------------------------------------------
# weekly_role_map projection
# ---------------------------------------------------------------------------


def _roles(packet: dict) -> list[dict]:
    return [
        role
        for week in packet["selected_plan"]["weekly_role_map"]["weeks"]
        for role in week.get("session_roles") or []
    ]


def test_selection_hints_are_gone_but_closed_membership_is_not(packet):
    """Membership is closed, so the pool/system hints are stale noise.

    preferred_tags is deliberately kept: the tactical-identity boundary
    sanitizes it before the handoff, so it is delivered on purpose.
    """
    for role in _roles(packet):
        for dropped in ("preferred_pool", "preferred_system"):
            assert dropped not in role
    assert any(role.get("selected_exercise_assignments") for role in _roles(packet))


def test_assignment_provenance_is_gone_but_identity_and_dose_are_not(packet):
    seen = 0
    for role in _roles(packet):
        for item in role.get("selected_exercise_assignments") or []:
            seen += 1
            for dropped in ("slot_group", "source_phase", "source_session_index", "dose_authority"):
                assert dropped not in item
            assert item.get("name"), "exercise identity must survive"
    assert seen, "fixture must carry selected assignments"


def test_every_selected_exercise_and_effective_dose_survives(generated, packet):
    """Parity: identity and authoritative dose, exercise by exercise."""
    source: dict[str, str] = {}
    for week in (generated["planning_brief"].get("weekly_role_map") or {}).get("weeks") or []:
        for role in week.get("session_roles") or []:
            for item in role.get("effective_strength_prescriptions") or []:
                if isinstance(item, dict) and item.get("name"):
                    source[str(item["name"])] = str(item.get("effective_prescription") or "")

    delivered: dict[str, str] = {}
    for role in _roles(packet):
        for item in role.get("effective_strength_prescriptions") or []:
            if isinstance(item, dict) and item.get("name"):
                delivered[str(item["name"])] = str(item.get("effective_prescription") or "")

    assert source, "fixture must resolve prescriptions"
    for name, prescription in source.items():
        assert name in delivered, f"{name!r} lost its prescription entry"
        assert delivered[name] == prescription, f"{name!r} dose drifted"


def test_a_capped_dose_keeps_both_prescriptions():
    """base_prescription is dropped ONLY when it repeats the effective dose."""
    from fightcamp.stage2_finalizer_packet_impl import _compact_prescribed_items

    items = [
        {"slot_id": "a", "name": "Same", "base_prescription": "3x5", "effective_prescription": "3x5"},
        {"slot_id": "b", "name": "Capped", "base_prescription": "5x5 @ RPE 9", "effective_prescription": "2x3 @ RPE 6"},
    ]
    compact = _compact_prescribed_items(items, effective_by_slot={"a": "3x5", "b": "2x3 @ RPE 6"})

    assert "base_prescription" not in compact[0]
    assert compact[0]["effective_prescription"] == "3x5"
    # The capped exercise keeps both, so the raw bank dose can never be mistaken
    # for the authorised one.
    assert compact[1]["base_prescription"] == "5x5 @ RPE 9"
    assert compact[1]["effective_prescription"] == "2x3 @ RPE 6"


def test_calendar_identity_and_same_day_multi_role_survive(generated, packet):
    """Distinct roles sharing a D-day are never collapsed."""
    def by_day(weeks):
        days: dict[str, set] = {}
        for week in weeks:
            for role in week.get("session_roles") or []:
                label = str(
                    role.get("scheduled_countdown_label") or role.get("countdown_label") or ""
                )
                if label:
                    days.setdefault(label, set()).add(str(role.get("role_key") or ""))
        return days

    source = by_day((generated["planning_brief"].get("weekly_role_map") or {}).get("weeks") or [])
    delivered = by_day(packet["selected_plan"]["weekly_role_map"]["weeks"])

    multi = {day: keys for day, keys in source.items() if len(keys) > 1}
    assert multi, "fixture must contain at least one multi-role day"
    for day, keys in source.items():
        assert day in delivered, f"{day} disappeared from the calendar"
        assert keys <= delivered[day], f"{day} lost role(s) {keys - delivered[day]}"


def test_combat_status_and_safety_envelopes_survive(generated, packet):
    source_weeks = (generated["planning_brief"].get("weekly_role_map") or {}).get("weeks") or []
    source_combat = {
        (
            str(role.get("scheduled_countdown_label") or role.get("countdown_label") or ""),
            str(role.get("role_key") or ""),
            str(role.get("hard_sparring_status") or ""),
        )
        for week in source_weeks
        for role in week.get("session_roles") or []
        if str(role.get("role_key") or "") in {"hard_sparring_day", "light_combat_day"}
    }
    delivered_combat = {
        (
            str(role.get("scheduled_countdown_label") or role.get("countdown_label") or ""),
            str(role.get("role_key") or ""),
            str(role.get("hard_sparring_status") or ""),
        )
        for role in _roles(packet)
        if str(role.get("role_key") or "") in {"hard_sparring_day", "light_combat_day"}
    }
    assert source_combat, "fixture must declare combat days"
    assert source_combat <= delivered_combat

    envelopes = [role for role in _roles(packet) if role.get("effective_strength_envelope")]
    assert envelopes, "strength envelopes must still reach Stage 2"


def test_suppressed_roles_still_name_what_cannot_be_restored(packet):
    suppressed = [
        role
        for week in packet["selected_plan"]["weekly_role_map"]["weeks"]
        for role in week.get("suppressed_roles") or []
    ]
    assert suppressed
    assert all(role.get("role_key") for role in suppressed)


# ---------------------------------------------------------------------------
# ownership: context without authorship
# ---------------------------------------------------------------------------


def test_locked_drill_body_is_not_shipped_but_its_identity_is(packet):
    """Stage 2 must know the Watch is there; it must not be handed the script."""
    locked = [
        role
        for role in _roles(packet)
        if (role.get("governance") or {}).get("selected_drill_locked") is True
    ]
    assert locked, "fixture must produce deterministic locked drills"
    for role in locked:
        assert "display_text" not in role, "the server writes this body, not Stage 2"
        governance = role.get("governance") or {}
        # Identity and calendar position survive, so surrounding work is planned
        # around a day the finalizer can still see.
        assert governance.get("selected_drill_name") or role.get("preferred_exercise_names")
        assert role.get("scheduled_countdown_label") or role.get("countdown_label")


def test_adaptive_roles_keep_their_display_text(packet):
    """Only server-owned bodies go: Stage 2-owned roles are untouched."""
    adaptive = [
        role
        for role in _roles(packet)
        if role.get("display_text")
        and not (role.get("governance") or {}).get("selected_drill_locked")
    ]
    assert adaptive, "adaptive roles must keep the text Stage 2 renders"


def test_the_locked_rule_asks_for_the_day_not_the_content(packet):
    rules = [str(rule) for rule in packet.get("hard_rules") or []]
    locked_rules = [rule for rule in rules if "selected_drill_locked" in rule]
    # One context rule replaced three authorship rules.
    assert len(locked_rules) == 1
    rule = locked_rules[0]
    assert "do not author" in rule.lower()
    assert "suppressed_roles" in rule
    assert "display_text" not in rule


def test_faithfulness_still_reads_the_body_from_the_planning_brief(generated):
    """The gate's authority is the brief, so packet slimming cannot blind it."""
    from api.structured_plan_faithfulness import _locked_roles

    roles = _locked_roles(generated["planning_brief"])
    assert roles
    assert all(isinstance(role.get("display_text"), str) and role["display_text"] for role in roles)


def test_tactical_watch_reaches_the_card_even_if_stage2_omits_the_whole_day(generated):
    """Context survives without authorship: the server still places the Watch."""
    from api.structured_plan_calendar_spine import reconcile_calendar_spine
    from api.structured_plan_faithfulness import _authoritative_locked_day, _locked_roles
    from api.structured_plan_locked_merge import merge_locked_structured_content

    brief = generated["planning_brief"]
    watch_days = {
        day
        for role in _locked_roles(brief)
        if (day := _authoritative_locked_day(role)) is not None
    }
    assert watch_days

    # Stage 2 renders S&C days only and never mentions a Watch day at all.
    plan = {
        "weeks": [
            {
                "week_index": 1,
                "days": [
                    {
                        "countdown_label": f"D-{dday}",
                        "date": "",
                        "sessions": [
                            {
                                "session_id": f"s{dday}",
                                "session_type": "strength",
                                "title": "Strength",
                                "objective": "Build force",
                                "blocks": [
                                    {
                                        "block_id": f"b{dday}",
                                        "block_type": "exercise",
                                        "display_name": "Squat",
                                        "duration": {"value": 30, "unit": "minutes"},
                                    }
                                ],
                            }
                        ],
                    }
                    for dday in range(56, -1, -1)
                    if dday not in watch_days
                ],
            }
        ]
    }
    merged = merge_locked_structured_content(reconcile_calendar_spine(plan, brief), brief)
    assert not merged.unresolved
    assert len(merged.applied) == len(_locked_roles(brief))
