"""Within-day execution order is a deterministic planner decision.

Same-day work used to keep whatever order it entered ``session_roles`` in, and
server-owned cards were appended after conversion, so a calming Breathing Reset
could be served before the Technical Shadow Rhythm it exists to wind down from.
fightcamp.session_sequencing orders by intent, never changes membership or day.
"""

from __future__ import annotations

import pytest

import api.structured_plan_deterministic_fallback as fallback_module
from api.structured_plan_models import Session
from fightcamp.session_sequencing import (
    ROLE_SEQUENCE,
    SequenceIntent,
    in_stamped_execution_order,
    parse_sequence_override,
    role_sequence_slot,
    sequence_day_roles,
    sequence_session_blocks,
    sequence_structured_plan,
    session_sequence_slot,
    stamp_role_execution_order,
)
from fightcamp.gap_fill_inserts import _INSERT_META
from fightcamp.role_labels import ROLE_LABELS


def _keys(roles):
    return [role["role_key"] for role in roles]


# ---------------------------------------------------------------------------
# Intent resolution
# ---------------------------------------------------------------------------


def test_every_known_role_and_insert_has_an_intent():
    """A new role key must be placed deliberately, not left to input order."""
    missing = sorted(
        key
        for key in {*ROLE_LABELS, *_INSERT_META}
        if key not in ROLE_SEQUENCE
    )
    assert missing == []


@pytest.mark.parametrize(
    ("role_key", "intent"),
    [
        ("joint_prep", SequenceIntent.PREPARE),
        ("mobility_rehab", SequenceIntent.PREPARE),
        ("neural_visualization", SequenceIntent.PRIME),
        ("technical_shadow_rhythm", SequenceIntent.LEARN),
        ("tactical_watch", SequenceIntent.LEARN),
        ("hard_sparring_day", SequenceIntent.PERFORM),
        ("primary_strength_day", SequenceIntent.DEVELOP),
        ("aerobic_base_day", SequenceIntent.FATIGUE),
        ("breathing_reset", SequenceIntent.RESTORE),
        ("recovery_reset", SequenceIntent.RESTORE),
        ("self_review", SequenceIntent.REFLECT),
    ],
)
def test_role_intents(role_key, intent):
    assert role_sequence_slot({"role_key": role_key}).intent is intent


def test_unregistered_support_insert_resolves_through_its_planner_semantics():
    slot = role_sequence_slot(
        {"role_key": "new_insert", "category": "support_insert", "support_insert_category": "recovery"}
    )
    assert slot.intent is SequenceIntent.RESTORE


def test_unregistered_role_resolves_through_its_category():
    assert role_sequence_slot({"role_key": "x", "category": "strength"}).intent is SequenceIntent.DEVELOP
    assert role_sequence_slot({"role_key": "x", "category": "mystery"}) is None


# ---------------------------------------------------------------------------
# Day ordering
# ---------------------------------------------------------------------------


def test_breathing_reset_follows_technical_shadow_rhythm():
    roles = [{"role_key": "breathing_reset"}, {"role_key": "technical_shadow_rhythm"}]
    assert _keys(sequence_day_roles(roles)) == ["technical_shadow_rhythm", "breathing_reset"]


def test_full_day_follows_the_coach_dependency_chain():
    roles = [
        {"role_key": "self_review"},
        {"role_key": "breathing_reset"},
        {"role_key": "aerobic_base_day"},
        {"role_key": "primary_strength_day"},
        {"role_key": "technical_shadow_rhythm"},
        {"role_key": "neural_visualization"},
        {"role_key": "joint_prep"},
    ]
    assert _keys(sequence_day_roles(roles)) == [
        "joint_prep",
        "neural_visualization",
        "technical_shadow_rhythm",
        "primary_strength_day",
        "aerobic_base_day",
        "breathing_reset",
        "self_review",
    ]


def test_hard_conditioning_precedes_easy_flush_precedes_breathing():
    roles = [
        {"role_key": "breathing_reset"},
        {"role_key": "walk_flush"},
        {"role_key": "fight_pace_repeatability_day"},
    ]
    assert _keys(sequence_day_roles(roles)) == [
        "fight_pace_repeatability_day",
        "walk_flush",
        "breathing_reset",
    ]


def test_sleep_downshift_is_last_even_after_review():
    roles = [{"role_key": "sleep_downshift"}, {"role_key": "self_review"}]
    assert _keys(sequence_day_roles(roles)) == ["self_review", "sleep_downshift"]


def test_equal_intent_keeps_input_order():
    roles = [{"role_key": "footwork_walkthrough"}, {"role_key": "technical_shadow_rhythm"}]
    assert _keys(sequence_day_roles(roles)) == ["footwork_walkthrough", "technical_shadow_rhythm"]
    assert _keys(sequence_day_roles(list(reversed(roles)))) == [
        "technical_shadow_rhythm",
        "footwork_walkthrough",
    ]


def test_unclassified_work_travels_with_its_neighbour():
    roles = [
        {"role_key": "breathing_reset"},
        {"role_key": "mystery_item"},
        {"role_key": "joint_prep"},
    ]
    # The mystery item was written after the breathing reset and stays with it.
    assert _keys(sequence_day_roles(roles)) == ["joint_prep", "breathing_reset", "mystery_item"]


def test_leading_unclassified_work_anchors_to_what_follows_it():
    roles = [{"role_key": "mystery_item"}, {"role_key": "breathing_reset"}, {"role_key": "joint_prep"}]
    assert _keys(sequence_day_roles(roles)) == ["joint_prep", "mystery_item", "breathing_reset"]


def test_nothing_resolvable_is_left_untouched():
    roles = [{"role_key": "a"}, {"role_key": "b"}]
    assert _keys(sequence_day_roles(roles)) == ["a", "b"]


# ---------------------------------------------------------------------------
# Explicit exceptions
# ---------------------------------------------------------------------------


def test_sequence_override_makes_unusual_order_intentional():
    roles = [
        {"role_key": "technical_shadow_rhythm", "sequence_override": "after_conditioning"},
        {"role_key": "fight_pace_repeatability_day"},
        {"role_key": "breathing_reset"},
    ]
    assert _keys(sequence_day_roles(roles)) == [
        "fight_pace_repeatability_day",
        "technical_shadow_rhythm",
        "breathing_reset",
    ]


def test_before_override_and_explicit_intent():
    roles = [
        {"role_key": "joint_prep"},
        {"role_key": "primary_strength_day"},
        {"role_key": "breathing_reset", "sequence_override": "before_strength"},
        {"role_key": "self_review", "sequence_intent": "prepare"},
    ]
    assert _keys(sequence_day_roles(roles)) == [
        "joint_prep",
        "self_review",
        "breathing_reset",
        "primary_strength_day",
    ]


def test_first_and_last_overrides():
    roles = [
        {"role_key": "joint_prep"},
        {"role_key": "self_review", "sequence_override": "first"},
        {"role_key": "neural_visualization", "sequence_override": "last"},
        {"role_key": "breathing_reset"},
    ]
    assert _keys(sequence_day_roles(roles)) == [
        "self_review",
        "joint_prep",
        "breathing_reset",
        "neural_visualization",
    ]


def test_unknown_override_is_ignored_not_guessed():
    assert parse_sequence_override("sometime_later") is None
    assert parse_sequence_override("after_nonsense") is None


# ---------------------------------------------------------------------------
# Inside a session
# ---------------------------------------------------------------------------


def test_blocks_follow_a_coach_session_structure():
    blocks = [
        {"block_type": "cooldown_recovery", "display_name": "Cooldown"},
        {"block_type": "conditioning", "display_name": "Intervals"},
        {"block_type": "accessory", "display_name": "Row"},
        {"block_type": "strength", "display_name": "Squat"},
        {"block_type": "plyometric_power", "display_name": "Box jump"},
        {"block_type": "preparation", "display_name": "Warm-up"},
    ]
    assert [b["display_name"] for b in sequence_session_blocks(blocks)] == [
        "Warm-up",
        "Box jump",
        "Squat",
        "Row",
        "Intervals",
        "Cooldown",
    ]


def test_rehab_block_moves_only_when_its_purpose_says_where():
    unlabelled = [
        {"block_type": "strength", "display_name": "Squat"},
        {"block_type": "rehab", "display_name": "Ankle drill"},
    ]
    assert [b["display_name"] for b in sequence_session_blocks(unlabelled)] == ["Squat", "Ankle drill"]
    activation = [
        {"block_type": "strength", "display_name": "Squat"},
        {"block_type": "rehab", "display_name": "Calf isometric", "purpose": "Tendon activation"},
    ]
    assert [b["display_name"] for b in sequence_session_blocks(activation)] == [
        "Calf isometric",
        "Squat",
    ]


def test_mixed_session_position_comes_from_its_main_work():
    session = {
        "session_type": "mixed",
        "title": "Session",
        "blocks": [
            {"block_type": "preparation"},
            {"block_type": "strength"},
            {"block_type": "conditioning"},
            {"block_type": "cooldown_recovery"},
        ],
    }
    assert session_sequence_slot(session).intent is SequenceIntent.FATIGUE


# ---------------------------------------------------------------------------
# Structured card
# ---------------------------------------------------------------------------


def _card(sessions: list[dict]) -> dict:
    return {
        "weeks": [
            {
                "days": [
                    {"countdown_label": "D-10", "sessions": sessions},
                ]
            }
        ]
    }


def test_converter_card_is_sequenced_by_identity_and_type():
    plan = _card(
        [
            {"session_id": "ses-1", "session_type": "recovery", "title": "Breathing Reset", "blocks": []},
            {"session_id": "ses-2", "session_type": "skill", "title": "Technical Shadow Rhythm", "blocks": []},
            # The locked merge appends server-owned cards after conversion.
            {"session_id": "locked-d-10-tactical-watch", "session_type": "skill", "title": "Tactical Focus", "blocks": []},
            {"session_id": "ses-3", "session_type": "strength_power", "title": "Strength", "blocks": [
                {"block_type": "accessory", "display_name": "Row", "order_index": 0},
                {"block_type": "strength", "display_name": "Squat", "order_index": 1},
            ]},
        ]
    )
    sequence_structured_plan(plan)
    sessions = plan["weeks"][0]["days"][0]["sessions"]
    assert [s["title"] for s in sessions] == [
        "Tactical Focus",
        "Technical Shadow Rhythm",
        "Strength",
        "Breathing Reset",
    ]
    assert [s["execution_order"] for s in sessions] == [1, 2, 3, 4]
    strength = sessions[2]
    assert [(b["display_name"], b["order_index"]) for b in strength["blocks"]] == [
        ("Squat", 0),
        ("Row", 1),
    ]


def test_structured_sequencing_never_changes_membership():
    sessions = [
        {"session_id": f"ses-{i}", "session_type": kind, "title": kind, "blocks": []}
        for i, kind in enumerate(["recovery", "mixed", "conditioning", "skill", "rehab"])
    ]
    plan = _card(list(sessions))
    sequence_structured_plan(plan)
    after = plan["weeks"][0]["days"][0]["sessions"]
    assert sorted(s["session_id"] for s in after) == sorted(s["session_id"] for s in sessions)


def test_brief_role_override_reaches_the_card():
    brief = {
        "weekly_role_map": {
            "weeks": [
                {
                    "session_roles": [
                        {
                            "role_key": "technical_shadow_rhythm",
                            "scheduled_countdown_label": "D-10",
                            "session_index": 2,
                            "sequence_override": "after_conditioning",
                        },
                        {"role_key": "fight_pace_repeatability_day", "scheduled_countdown_label": "D-10"},
                    ]
                }
            ]
        }
    }
    plan = _card(
        [
            {"session_id": "deterministic-10-technical_shadow_rhythm-2", "session_type": "skill", "title": "Technical Shadow Rhythm"},
            {"session_id": "deterministic-10-fight_pace_repeatability_day-0", "session_type": "conditioning", "title": "Fight-pace conditioning"},
        ]
    )
    sequence_structured_plan(plan, brief)
    assert [s["title"] for s in plan["weeks"][0]["days"][0]["sessions"]] == [
        "Fight-pace conditioning",
        "Technical Shadow Rhythm",
    ]


def test_execution_order_survives_schema_validation():
    plan = _card(
        [
            {
                "session_id": "ses-1",
                "session_type": "recovery",
                "title": "Breathing Reset",
                "objective": "Downshift.",
                "mindset_anchor": {"intent": "", "focus_cue": "", "reset_cue": ""},
                "blocks": [],
            }
        ]
    )
    sequence_structured_plan(plan)
    assert Session.model_validate(plan["weeks"][0]["days"][0]["sessions"][0]).execution_order == 1


# ---------------------------------------------------------------------------
# Deterministic fallback, end to end
# ---------------------------------------------------------------------------


def _support_role(role_key: str, d_day: int, session_index: int) -> dict:
    meta = _INSERT_META[role_key]
    return {
        "role_key": role_key,
        "category": "support_insert",
        "athlete_facing_label": meta["label"],
        "display_text": meta["display_text"],
        "support_insert_category": meta["insert_category"],
        "scheduled_countdown_label": f"D-{d_day}",
        "countdown_label": f"D-{d_day}",
        "session_index": session_index,
        "selected_exercise_assignments": [],
    }


def test_fallback_serves_breathing_reset_after_technical_shadow_rhythm(monkeypatch):
    d_day = 10
    brief = {
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": "SPP",
                    "session_roles": [
                        _support_role("breathing_reset", d_day, 1),
                        _support_role("technical_shadow_rhythm", d_day, 2),
                        _support_role("joint_prep", d_day, 3),
                    ],
                }
            ]
        }
    }
    monkeypatch.setattr(
        fallback_module,
        "reconcile_calendar_spine",
        lambda _plan, _brief: {
            "weeks": [
                {
                    "week_index": 1,
                    "phase_label": "SPP",
                    "days": [
                        {
                            "date": "2026-10-01",
                            "countdown_label": f"D-{d_day}",
                            "day_type": "low",
                            "phase_label": "SPP",
                            "today_card": {
                                "headline": "Training Day",
                                "readiness_status": "train_as_planned",
                                "mindset_anchor": {"intent": "", "focus_cue": "", "reset_cue": ""},
                            },
                            "sessions": [],
                        }
                    ],
                }
            ]
        },
    )

    plan = fallback_module.build_deterministic_structured_plan(brief)

    assert plan is not None
    sessions = plan["weeks"][0]["days"][0]["sessions"]
    assert [s["title"] for s in sessions] == [
        "Joint Prep",
        "Technical Shadow Rhythm",
        "Breathing Reset",
    ]
    assert [s["execution_order"] for s in sessions] == [1, 2, 3]
    # session_index identity is untouched by execution order.
    assert [s["session_id"] for s in sessions] == [
        f"deterministic-{d_day}-joint_prep-3",
        f"deterministic-{d_day}-technical_shadow_rhythm-2",
        f"deterministic-{d_day}-breathing_reset-1",
    ]
    for session in sessions:
        assert Session.model_validate(session).execution_order == session["execution_order"]


# ---------------------------------------------------------------------------
# Stage 1 stamp
# ---------------------------------------------------------------------------


def test_stage1_stamps_execution_order_without_reordering_roles():
    roles = [
        {"role_key": "breathing_reset", "scheduled_countdown_label": "D-10", "session_index": 1},
        {"role_key": "primary_strength_day", "scheduled_countdown_label": "D-12", "session_index": 2},
        {"role_key": "technical_shadow_rhythm", "scheduled_countdown_label": "D-10", "session_index": 3},
    ]
    brief = {"weekly_role_map": {"weeks": [{"session_roles": roles}]}}

    stamp_role_execution_order(brief)

    stamped = brief["weekly_role_map"]["weeks"][0]["session_roles"]
    assert _keys(stamped) == ["breathing_reset", "primary_strength_day", "technical_shadow_rhythm"]
    assert [r["session_index"] for r in stamped] == [1, 2, 3]
    assert {r["role_key"]: r["execution_order"] for r in stamped} == {
        "technical_shadow_rhythm": 1,
        "breathing_reset": 2,
        "primary_strength_day": 1,
    }


def test_stage1_stamps_the_late_fight_sequence():
    brief = {
        "late_fight_session_sequence": [
            {"role_key": "breathing_reset", "scheduled_countdown_label": "D-5"},
            {"role_key": "neural_primer_day", "scheduled_countdown_label": "D-5"},
        ]
    }
    stamp_role_execution_order(brief)
    by_key = {r["role_key"]: r["execution_order"] for r in brief["late_fight_session_sequence"]}
    assert by_key == {"neural_primer_day": 1, "breathing_reset": 2}


def test_renderer_helper_reads_the_stamp_and_keeps_day_order():
    roles = [
        {"role_key": "a", "day": "D-5", "execution_order": 2},
        {"role_key": "b", "day": "D-5", "execution_order": 1},
        {"role_key": "c", "day": "D-4"},
    ]
    assert _keys(in_stamped_execution_order(roles, lambda r: r["day"])) == ["b", "a", "c"]


def test_finalizer_packet_carries_execution_order():
    from fightcamp.stage2_finalizer_packet_impl import _compact_role

    compact = _compact_role({"role_key": "breathing_reset", "session_index": 4, "execution_order": 2})
    assert compact["execution_order"] == 2
    assert compact["session_index"] == 4


# ---------------------------------------------------------------------------
# One-session summaries still pick the day's main work
# ---------------------------------------------------------------------------


def test_today_primary_session_skips_support_that_now_leads_the_day():
    from api.services.today_service import _select_structured_primary_session

    sessions = [
        {"title": "Joint Prep", "session_type": "rehab", "blocks": [{"block_type": "mobility_activation"}]},
        {"title": "Tactical Focus", "session_type": "skill", "blocks": [{"block_type": "mindset"}]},
        {"title": "Strength", "session_type": "strength_power", "blocks": [{"block_type": "strength"}]},
        {"title": "Breathing Reset", "session_type": "recovery", "blocks": [{"block_type": "cooldown_recovery"}]},
    ]
    assert _select_structured_primary_session(sessions)["title"] == "Strength"
    support_only = [sessions[0], sessions[3]]
    assert _select_structured_primary_session(support_only)["title"] == "Joint Prep"


def test_sequencing_never_raises_on_a_malformed_card():
    plan = {"weeks": [{"days": [{"countdown_label": "D-3", "sessions": [None, {"blocks": "bad"}]}]}]}
    assert sequence_structured_plan(plan) is plan
