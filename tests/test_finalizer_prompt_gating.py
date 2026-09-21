"""Gating contract for the finalizer prompt.

Three blocks state a precondition the deterministic build resolves before the
prompt is written, so they are omitted when that precondition is known false.
These tests pin both halves: the split must stay lossless, and the gates must
fail OPEN - an unknown flag keeps the rule.
"""

import pytest

from fightcamp.stage2_payload import (
    STAGE2_FINALIZER_PROMPT,
    _FINALIZER_SEGMENT_A,
    _FINALIZER_SEGMENT_B,
    _RULE_9B_TAPER_MICRO_SUPPORT,
    _RULE_12_SURGICAL_REHAB,
    _RULE_13_COUNTDOWN_SCAFFOLDING,
    _RULE_13_HEADER,
    _RULE_13_LABEL_RULES,
    build_finalizer_prompt,
)

RULE_9B = "RULE 9B — TAPER MICRO-SUPPORT"
RULE_12 = "RULE 12 — SURGICAL REHAB"
RULE_13_SCAFFOLD = "Applies when render_guards.suppress_phase_toolbox_sections"
RULE_13_LABELS = "Do not expose internal role keys"


def test_segments_reassemble_into_the_original_prompt():
    assert (
        _FINALIZER_SEGMENT_A
        + _RULE_9B_TAPER_MICRO_SUPPORT
        + _FINALIZER_SEGMENT_B
        + _RULE_12_SURGICAL_REHAB
        + _RULE_13_HEADER
        + _RULE_13_COUNTDOWN_SCAFFOLDING
        + _RULE_13_LABEL_RULES
    ) == STAGE2_FINALIZER_PROMPT


def test_ungated_build_is_the_whole_prompt():
    assert build_finalizer_prompt() == STAGE2_FINALIZER_PROMPT


@pytest.mark.parametrize(
    "render_guards,selected_plan",
    [
        (None, None),
        ({}, None),
        ("not a dict", "not a dict"),
        ({"has_active_injury": None}, {"late_fight_plan_spec": None}),
        ({"has_active_injury": "unknown"}, {"late_fight_plan_spec": "unknown"}),
    ],
)
def test_gates_fail_open_on_missing_or_malformed_flags(render_guards, selected_plan):
    """An unreadable flag must never drop a rule.

    Before gating, an absent flag cost nothing because every rule shipped anyway.
    Reading "I could not find it" as "it does not apply" would silently lose a
    safety rule, so anything other than an explicit False keeps the block.
    """
    prompt = build_finalizer_prompt(render_guards=render_guards, selected_plan=selected_plan)

    assert RULE_9B in prompt
    assert RULE_12 in prompt
    assert RULE_13_SCAFFOLD in prompt


def test_rule_12_dropped_only_when_there_is_no_active_injury():
    without = build_finalizer_prompt(render_guards={"has_active_injury": False})
    with_injury = build_finalizer_prompt(render_guards={"has_active_injury": True})

    assert RULE_12 not in without
    assert RULE_12 in with_injury


def test_rule_13_labels_survive_when_its_scaffolding_is_gated():
    """RULE 13 says its label rules "apply regardless of mode", so gating the
    countdown paragraph must not take them with it."""
    prompt = build_finalizer_prompt(
        render_guards={"suppress_phase_toolbox_sections": False}
    )

    assert RULE_13_SCAFFOLD not in prompt
    assert RULE_13_LABELS in prompt
    assert "RULE 13 — LATE-FIGHT LABEL DISCIPLINE" in prompt


def test_rule_13_scaffolding_kept_in_late_fight_mode():
    prompt = build_finalizer_prompt(
        render_guards={"suppress_phase_toolbox_sections": True}
    )

    assert RULE_13_SCAFFOLD in prompt


@pytest.mark.parametrize(
    "selected_plan",
    [
        None, "junk", [], {}, {"unrelated": True},
        *[{"late_fight_plan_spec": value} for value in (None, "junk", [], False, 0, {})],
        *[{"late_fight_plan_spec": {"taper_micro_support_policy": value}}
          for value in (None, "junk", [], False, 0, {})],
        *[{"late_fight_plan_spec": {"taper_micro_support_policy": {"active": value}}}
          for value in (None, "junk", "false", 0, 1, [], {}, True)],
    ],
)
def test_rule_9b_kept_unless_policy_is_explicitly_inactive(selected_plan):
    assert RULE_9B in build_finalizer_prompt(selected_plan=selected_plan)


def test_rule_9b_dropped_for_explicit_false():
    selected_plan = {"late_fight_plan_spec": {"taper_micro_support_policy": {"active": False}}}
    assert RULE_9B not in build_finalizer_prompt(selected_plan=selected_plan)


def test_no_gated_rule_is_referenced_by_number_from_an_ungated_one():
    """A cross-reference like "see RULE 12" would dangle once RULE 12 is gated
    out, so the always-sent text must not point at a gateable rule."""
    always_sent = (
        _FINALIZER_SEGMENT_A + _FINALIZER_SEGMENT_B + _RULE_13_HEADER + _RULE_13_LABEL_RULES
    )

    for gated in ("RULE 9B", "RULE 12"):
        assert gated not in always_sent


@pytest.mark.parametrize("source", ["payload", "brief"])
def test_normal_camp_handoff_omits_rule_without_adding_late_fight_state(source):
    from fightcamp.stage2_payload import (
        build_planning_brief, build_stage2_payload, build_stage2_handoff_text,
    )
    from fightcamp.training_context import TrainingContext

    if source == "payload":
        payload = build_stage2_payload(
            training_context=TrainingContext(
                days_until_fight=30, fatigue="low", training_frequency=4,
                days_available=4, training_days=["Mon", "Tue", "Thu", "Sat"],
                injuries=[], style_technical=["boxing"], style_tactical=[],
                weaknesses=[], equipment=["heavy_bag"], weight_cut_risk=False,
                weight_cut_pct=0.0, fight_format="boxing", status="amateur",
                key_goals=["conditioning"], training_preference="balanced",
                mental_block=[], age=25, weight=70.0, prev_exercises=[],
                recent_exercises=[], phase_weeks={"GPP": 2, "SPP": 2, "TAPER": 1},
            ),
            mapped_format="boxing", record="3-0", rounds_format="3x3",
            camp_len=5, short_notice=False, restrictions=[],
            phase_weeks={"GPP": 2, "SPP": 2, "TAPER": 1},
            strength_blocks={}, conditioning_blocks={}, rehab_blocks={},
        )
        brief = {}
    else:
        brief = build_planning_brief(
            athlete_model={"days_until_fight": 30, "sport": "boxing"},
            restrictions=[], phase_briefs={}, candidate_pools={},
            omission_ledger={}, rewrite_guidance={},
        )
        payload = {}

    assert "late_fight_plan_spec" not in payload
    assert "late_fight_plan_spec" not in brief
    prompt = build_stage2_handoff_text(
        stage2_payload=payload, planning_brief=brief, plan_text="",
    )
    assert RULE_9B not in prompt


@pytest.mark.parametrize("mode", [None, "unknown", "deterministic_late_fight_planner_plus_ai_finalizer"])
def test_handoff_keeps_rule_when_architecture_is_not_known_normal(mode):
    from fightcamp.stage2_payload import build_stage2_handoff_text

    prompt = build_stage2_handoff_text(stage2_payload={"generator_mode": mode}, plan_text="")
    assert RULE_9B in prompt


@pytest.mark.parametrize("marker", ["payload_variant", "days_out_payload", "late_fight_plan_spec"])
@pytest.mark.parametrize("value", [None, {}, "junk"])
def test_handoff_keeps_rule_when_normal_mode_has_late_fight_markers(marker, value):
    from fightcamp.stage2_payload import build_stage2_handoff_text

    prompt = build_stage2_handoff_text(
        stage2_payload={"generator_mode": "restriction_aware_candidate_generator", marker: value},
        plan_text="",
    )
    assert RULE_9B in prompt
