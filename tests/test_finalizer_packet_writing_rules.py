"""Guards for the writing-rule dedupe between the prompt and the finalizer packet.

``STAGE2_FINALIZER_PROMPT`` states a block of writing rules in prose, and the
deterministic payload's ``rewrite_guidance["writing_rules"]`` restated the same
rules in JSON. Both were shipped to the model. The packet builder now filters the
overlap out, so these tests pin the two halves of that contract: the covered set
must stay in sync with the live rules, and the state-dependent rules must survive.
"""

from fightcamp.stage2_finalizer_packet_impl import (
    FINALIZER_PROMPT_COVERED_WRITING_RULES,
    build_stage2_finalizer_packet,
)
from fightcamp.stage2_payload import build_stage2_payload
from fightcamp.training_context import TrainingContext

_PHASE_WEEKS = {"GPP": 2, "SPP": 2, "TAPER": 1, "days": {"GPP": 0, "SPP": 0, "TAPER": 0}}


def _payload() -> dict:
    training_context = TrainingContext(
        fatigue="moderate",
        training_frequency=4,
        days_available=4,
        training_days=["Mon", "Tue", "Thu", "Sat"],
        injuries=["left knee instability"],
        style_technical=["boxing"],
        style_tactical=["pressure_fighter"],
        weaknesses=["gas_tank"],
        equipment=["heavy_bag"],
        weight_cut_risk=False,
        weight_cut_pct=0.0,
        fight_format="boxing",
        status="amateur",
        key_goals=["conditioning"],
        training_preference="balanced",
        mental_block=[],
        age=25,
        weight=70.0,
        prev_exercises=[],
        recent_exercises=[],
        phase_weeks=_PHASE_WEEKS,
        days_until_fight=30,
        injury_restrictions=[{"restriction": "single_leg_loading", "region": "knee"}],
        triage_summary={"mode": "restricted_rehab_only", "triage_resume_approved": True},
    )
    return build_stage2_payload(
        training_context=training_context,
        mapped_format="boxing",
        record="3-0",
        rounds_format="3x3",
        camp_len=5,
        short_notice=False,
        restrictions=[{"restriction": "single_leg_loading", "region": "knee"}],
        phase_weeks=_PHASE_WEEKS,
        strength_blocks={},
        conditioning_blocks={},
        rehab_blocks={},
    )


def test_every_covered_rule_still_matches_a_live_writing_rule():
    """If a rule is reworded in the payload, the covered set must be updated too.

    Otherwise the entry silently stops matching and the duplicate quietly returns
    to the prompt.
    """
    live = set(_payload()["rewrite_guidance"]["writing_rules"])
    stale = sorted(rule for rule in FINALIZER_PROMPT_COVERED_WRITING_RULES if rule not in live)
    assert not stale, (
        "These entries no longer match any rule in rewrite_guidance['writing_rules']. "
        "Re-sync FINALIZER_PROMPT_COVERED_WRITING_RULES with the payload:\n"
        + "\n".join(f"- {rule[:120]}" for rule in stale)
    )


def test_packet_drops_prompt_covered_rules():
    packet = build_stage2_finalizer_packet(stage2_payload=_payload())
    shipped = set(packet["writing_rules"])

    assert not (shipped & FINALIZER_PROMPT_COVERED_WRITING_RULES)


def test_packet_keeps_state_dependent_rules():
    """Render-guard rules are computed from athlete state, so the prose prompt
    cannot carry them. They must still reach the model."""
    packet = build_stage2_finalizer_packet(stage2_payload=_payload())
    shipped = packet["writing_rules"]

    assert shipped, "packet writing_rules must not be emptied by the filter"
    assert any("render_guards" in rule for rule in shipped)


def test_filter_removes_the_duplicated_hard_sparring_paragraph():
    """The ~1.6k-char hard-sparring rule was the single biggest duplicate: RULE 11
    states it in prose and the packet restated it with 'does not' for 'must not'."""
    packet = build_stage2_finalizer_packet(stage2_payload=_payload())

    assert not any(
        "own combat locks" in rule for rule in packet["writing_rules"]
    )
