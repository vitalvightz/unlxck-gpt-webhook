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


def test_rule_9b_kept_only_when_taper_micro_support_is_active():
    active = build_finalizer_prompt(
        selected_plan={"late_fight_plan_spec": {"taper_micro_support_policy": {"active": True}}}
    )
    inactive = build_finalizer_prompt(
        selected_plan={"late_fight_plan_spec": {"taper_micro_support_policy": {"active": False}}}
    )
    absent = build_finalizer_prompt(selected_plan={})

    assert RULE_9B in active
    assert RULE_9B not in inactive
    assert RULE_9B not in absent


def test_no_gated_rule_is_referenced_by_number_from_an_ungated_one():
    """A cross-reference like "see RULE 12" would dangle once RULE 12 is gated
    out, so the always-sent text must not point at a gateable rule."""
    always_sent = (
        _FINALIZER_SEGMENT_A + _FINALIZER_SEGMENT_B + _RULE_13_HEADER + _RULE_13_LABEL_RULES
    )

    for gated in ("RULE 9B", "RULE 12"):
        assert gated not in always_sent
