"""A support insert that IS one known movement keeps its identity on the card.

Production (plan 6c418f41): Stage 1 stamped ``exercise_key`` on Shadowboxing
Aerobic Flow (``tempo-shadowboxing``) and Light Skipping Flush
(``jump-rope-recovery-pace``), both with live demo videos. The deterministic
session builder (shared by the whole-card fallback and the calendar spine's
restore of a missing insert) ignored that identity and emitted a blockless
session, so the card printed the banked sentence as bare text and no demo ever
resolved: ``exercise_key`` lives on blocks, and there was no block.
"""

from __future__ import annotations

from api.structured_plan_calendar_spine import _restore_missing_scheduled_roles
from api.structured_plan_deterministic_fallback import _session
from api.structured_plan_models import Session

SHADOW_TEXT = (
    "3 x 2 min easy solo movement rounds, 60 sec rest. Use smooth sport-specific "
    "movement at RPE 3. No contact, no power and no impact. Keep the gas tank "
    "ticking over without costing freshness."
)
SKIP_TEXT = (
    "30 sec easy skip / 30 sec rest, RPE 3. Keeps rhythm, calf stiffness, and "
    "breathing control without hard conditioning stress. Skip only while calves "
    "and Achilles are healthy."
)


def _insert(role_key: str, label: str, text: str, exercise_key: str | None) -> dict:
    """Shaped like fightcamp.gap_fill_inserts builds it (production copy)."""
    role = {
        "role_key": role_key,
        "category": "support_insert",
        "athlete_facing_label": label,
        "display_text": text,
        "support_insert_category": "conditioning_maintenance",
        "support_insert_cost_category": "low_cost_aerobic",
        "stress_class": "support",
        "selected_exercise_assignments": [],
        "scheduled_countdown_label": "D-12",
    }
    if exercise_key:
        role["exercise_key"] = exercise_key
    return role


def _shadow(**overrides) -> dict:
    role = _insert("aerobic_shadow_flow", "Shadowboxing Aerobic Flow", SHADOW_TEXT, "tempo-shadowboxing")
    role.update(overrides)
    return role


def test_known_movement_insert_becomes_one_keyed_block():
    session = _session(_shadow(), 12)

    Session.model_validate(session)
    assert session["session_type"] == "conditioning"
    [block] = session["blocks"]
    assert block["display_name"] == "Shadowboxing Aerobic Flow"
    assert block["exercise_key"] == "tempo-shadowboxing"
    assert block["block_type"] == "conditioning"


def test_the_banked_dose_is_kept_verbatim_and_only_exact_quantities_lift():
    [block] = _session(_shadow(), 12)["blocks"]

    # "60 sec rest" is a whole quantity clause -> a stat; nothing is invented.
    assert block["rest"] == {"value": 60, "unit": "seconds"}
    assert "sets" not in block and "rounds" not in block
    # Every other word of the copy is still on the card, in order.
    assert block["coaching_cues"] == [
        "3 x 2 min easy solo movement rounds",
        "Use smooth sport-specific movement at RPE 3. No contact, no power and no "
        "impact. Keep the gas tank ticking over without costing freshness.",
    ]


def test_session_no_longer_prints_the_prescription_as_its_objective():
    session = _session(_shadow(), 12)
    # The renderer hides an objective that repeats the title; the dose now lives
    # on the block (where a demo pins it under the exercise name).
    assert session["objective"] == "Shadowboxing Aerobic Flow"


def test_skip_flush_from_production_copy():
    session = _session(
        _insert("aerobic_skip_flush", "Light Skipping Flush", SKIP_TEXT, "jump-rope-recovery-pace"), 5
    )

    [block] = session["blocks"]
    assert block["exercise_key"] == "jump-rope-recovery-pace"
    assert block["effort"] == {"method": "RPE", "value": 3, "scale": "1-10"}
    assert block["coaching_cues"][0] == "30 sec easy skip / 30 sec rest"


def test_brief_predating_the_planner_stamp_uses_the_same_identity_table():
    role = _shadow()
    del role["exercise_key"]

    [block] = _session(role, 12)["blocks"]

    assert block["exercise_key"] == "tempo-shadowboxing"


def test_insert_without_a_movement_identity_stays_instruction_only():
    # Brisk Walk Flush has no deterministic movement/video: nothing is invented.
    walk = _insert(
        "aerobic_walk_flush",
        "Brisk Walk Flush",
        "Brisk or incline walk at a nose-breathing pace, RPE 3.",
        None,
    )
    session = _session(walk, 17)

    assert session["blocks"] == []
    assert session["objective"].startswith("Brisk or incline walk")


def test_spine_restored_insert_on_a_converted_card_carries_the_identity():
    # The converter dropped the insert; the spine restores it from Stage 1.
    day = {"countdown_label": "D-12", "day_type": "rest", "sessions": []}

    restored = _restore_missing_scheduled_roles(day, [_shadow()], 12)

    [session] = restored["sessions"]
    [block] = session["blocks"]
    assert block["exercise_key"] == "tempo-shadowboxing"
    assert restored["day_type"] == "low"
