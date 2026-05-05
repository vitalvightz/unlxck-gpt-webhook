"""Unit tests for the Stage 2 mental-training integrator."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.mental_training import (
    MENTAL_TRAINING_FINALIZER_GUIDE,
    MENTAL_TRAINING_WRITING_RULES,
    attach_mental_to_weekly_role_map,
    build_mental_candidate_pools,
    derive_phase_mental_briefs,
)
from fightcamp.stage2_finalizer_packet import build_stage2_finalizer_packet
from fightcamp.stage2_payload import build_planning_brief, build_stage2_payload
from fightcamp.training_context import TrainingContext


def _phase_briefs_for_test() -> dict[str, dict]:
    return {
        "GPP": {
            "objective": "build aerobic base and general force capacity",
            "emphasize": ["aerobic repeatability"],
            "deprioritize": ["fight-week intensity"],
            "risk_flags": [],
            "selection_guardrails": {},
            "weeks": 2,
            "days": 0,
        },
        "SPP": {
            "objective": "increase fight-specific repeatability and power transfer",
            "emphasize": ["glycolytic repeatability"],
            "deprioritize": ["non-specific volume"],
            "risk_flags": [],
            "selection_guardrails": {},
            "weeks": 2,
            "days": 0,
        },
        "TAPER": {
            "objective": "maintain sharpness and freshness",
            "emphasize": ["alactic sharpness"],
            "deprioritize": ["new drills"],
            "risk_flags": [],
            "selection_guardrails": {},
            "weeks": 1,
            "days": 0,
        },
    }


def _athlete_model(**overrides) -> dict:
    base = {
        "sport": "boxing",
        "status": "amateur",
        "rounds_format": "3x3",
        "camp_length_weeks": 5,
        "days_until_fight": 35,
        "fatigue": "low",
        "weight_cut_risk": False,
        "weight_cut_pct": 0.0,
        "technical_styles": ["boxing"],
        "tactical_styles": ["pressure_fighter"],
        "weaknesses": [],
        "key_goals": [],
        "mental_blocks": ["pressure", "rushing"],
        "training_days": ["Monday", "Tuesday", "Thursday", "Saturday"],
        "hard_sparring_days": [],
        "support_work_days": [],
        "readiness_flags": ["baseline"],
    }
    base.update(overrides)
    return base


def test_phase_brief_includes_objective_blocks_and_dose():
    briefs = derive_phase_mental_briefs(
        athlete_model=_athlete_model(),
        phase_briefs=_phase_briefs_for_test(),
    )
    assert set(briefs.keys()) == {"GPP", "SPP", "TAPER"}

    gpp = briefs["GPP"]
    assert gpp["primary_blocks"] == ["pressure", "rushing"]
    assert gpp["objective"]
    assert gpp["weekly_pattern"]
    assert gpp["per_session_minutes"]
    assert gpp["coach_voice"]
    # GPP should call out building the habit
    assert "build" in gpp["load_bias"].lower()
    # Per-block briefs include drills with attach hints
    for block_brief in gpp["block_briefs"]:
        assert block_brief["block"] in {"pressure", "rushing"}
        assert block_brief["preferred_session_roles"], "blocks should expose session affinity"
        assert block_brief["drills"], "every block should ship at least one drill"
        for drill in block_brief["drills"]:
            assert drill["name"]
            assert drill["purpose"]


def test_taper_brief_forbids_new_drills():
    briefs = derive_phase_mental_briefs(
        athlete_model=_athlete_model(),
        phase_briefs=_phase_briefs_for_test(),
    )
    taper = briefs["TAPER"]
    assert any("new" in line.lower() and "drill" in line.lower() for line in taper["do_not"])
    assert "minimal" in taper["load_bias"].lower()


def test_pure_striker_drops_takedown_block():
    briefs = derive_phase_mental_briefs(
        athlete_model=_athlete_model(mental_blocks=["fear of takedowns"]),
        phase_briefs=_phase_briefs_for_test(),
    )
    primary = briefs["SPP"]["primary_blocks"]
    assert "fear of takedowns" not in primary
    # Falls back gracefully (generic or another canonical block)
    assert primary


def test_grappler_keeps_takedown_block():
    briefs = derive_phase_mental_briefs(
        athlete_model=_athlete_model(
            mental_blocks=["fear of takedowns"],
            technical_styles=["mma"],
            tactical_styles=["wrestler"],
        ),
        phase_briefs=_phase_briefs_for_test(),
    )
    assert "fear of takedowns" in briefs["SPP"]["primary_blocks"]


def test_mma_sport_keeps_takedown_block_even_with_blank_styles():
    """Sport=MMA should keep fear_of_takedowns even if style fields are empty."""
    briefs = derive_phase_mental_briefs(
        athlete_model=_athlete_model(
            sport="mma",
            mental_blocks=["fear of takedowns"],
            technical_styles=[],
            tactical_styles=[],
        ),
        phase_briefs=_phase_briefs_for_test(),
    )
    assert "fear of takedowns" in briefs["SPP"]["primary_blocks"]


def test_fight_format_grappling_keeps_takedown_block():
    briefs = derive_phase_mental_briefs(
        athlete_model={
            **_athlete_model(),
            "fight_format": "bjj",
            "technical_styles": [],
            "tactical_styles": [],
            "mental_blocks": ["fear of takedowns"],
            "sport": "",
        },
        phase_briefs=_phase_briefs_for_test(),
    )
    assert "fear of takedowns" in briefs["SPP"]["primary_blocks"]


def test_mental_candidate_pools_emit_slots_with_alternates():
    pools = build_mental_candidate_pools(
        athlete_model=_athlete_model(),
        phase_briefs=_phase_briefs_for_test(),
    )
    assert set(pools.keys()) == {"GPP", "SPP", "TAPER"}
    gpp_slots = pools["GPP"]
    assert gpp_slots, "expected at least one mental slot per phase"
    primary = gpp_slots[0]
    assert primary["selected"]["source"] == "mental_training_bank"
    assert primary["selected"]["block"]
    assert "slot_id" in primary
    # Slot exposes purpose, dose, and attachment so Stage 2 can render in coach voice
    assert primary["selected"]["purpose"]
    assert primary["selected"]["dose"]
    assert primary["selected"]["attach"]


def test_attach_mental_pairs_pressure_with_sparring_day_when_present():
    briefs = derive_phase_mental_briefs(
        athlete_model=_athlete_model(),
        phase_briefs=_phase_briefs_for_test(),
    )
    weekly_role_map = {
        "weeks": [
            {
                "phase": "SPP",
                "session_roles": [
                    {"role_key": "primary_strength_day", "category": "strength"},
                    {"role_key": "hard_sparring_day", "category": "sparring"},
                    {"role_key": "aerobic_repeatability_day", "category": "conditioning",
                     "preferred_system": "aerobic"},
                    {"role_key": "recovery_reset_day", "category": "recovery"},
                ],
            }
        ]
    }
    attached = attach_mental_to_weekly_role_map(
        weekly_role_map=weekly_role_map,
        phase_mental_briefs=briefs,
    )
    week = attached["weeks"][0]
    by_key = {role["role_key"]: role for role in week["session_roles"]}

    sparring = by_key["hard_sparring_day"]
    assert "mental_attachment" in sparring
    # Pressure / rushing / composure should land on sparring
    assert sparring["mental_attachment"]["block"] in {"pressure", "rushing", "composure"}
    assert sparring["mental_attachment"]["cue"]
    assert sparring["mental_attachment"]["attachment_kind"]

    summary = week["mental_attachments_summary"]
    assert summary["phase"] == "SPP"
    assert summary["primary_blocks"] == ["pressure", "rushing"]
    assert summary["covered_blocks"], "at least one block should land on a real session"
    assert summary["coach_voice"]


def test_attach_caps_each_block_to_one_session_per_week():
    """A single block must not attach to more than one session in the same week."""
    briefs = derive_phase_mental_briefs(
        athlete_model=_athlete_model(mental_blocks=["pressure"]),
        phase_briefs=_phase_briefs_for_test(),
    )
    weekly_role_map = {
        "weeks": [
            {
                "phase": "SPP",
                # Every role here has affinity for "pressure". With the cap,
                # exactly one should carry mental_attachment.
                "session_roles": [
                    {"role_key": "hard_sparring_day", "category": "sparring"},
                    {"role_key": "primary_strength_day", "category": "strength"},
                    {"role_key": "alactic_sharpness_day", "category": "conditioning",
                     "preferred_system": "alactic"},
                    {"role_key": "glycolytic_repeatability_day", "category": "conditioning",
                     "preferred_system": "glycolytic"},
                ],
            }
        ]
    }
    attached = attach_mental_to_weekly_role_map(
        weekly_role_map=weekly_role_map,
        phase_mental_briefs=briefs,
    )
    week = attached["weeks"][0]
    attachments = [role for role in week["session_roles"] if role.get("mental_attachment")]
    assert len(attachments) == 1, "pressure should attach to exactly one session"
    # Best fit is hard_sparring_day (top of pressure's affinity list)
    assert attachments[0]["role_key"] == "hard_sparring_day"


def test_attach_caps_two_blocks_to_two_distinct_sessions():
    """Two blocks should attach to two distinct sessions, never both to the same one."""
    briefs = derive_phase_mental_briefs(
        athlete_model=_athlete_model(mental_blocks=["pressure", "attention"]),
        phase_briefs=_phase_briefs_for_test(),
    )
    weekly_role_map = {
        "weeks": [
            {
                "phase": "SPP",
                "session_roles": [
                    {"role_key": "hard_sparring_day", "category": "sparring"},
                    {"role_key": "primary_strength_day", "category": "strength"},
                    {"role_key": "recovery_reset_day", "category": "recovery"},
                ],
            }
        ]
    }
    attached = attach_mental_to_weekly_role_map(
        weekly_role_map=weekly_role_map,
        phase_mental_briefs=briefs,
    )
    week = attached["weeks"][0]
    attached_roles = [role for role in week["session_roles"] if role.get("mental_attachment")]
    assert len(attached_roles) == 2, "two blocks should produce two attachments"
    blocks_seen = {role["mental_attachment"]["block"] for role in attached_roles}
    role_keys_seen = {role["role_key"] for role in attached_roles}
    assert blocks_seen == {"pressure", "attention"}
    assert len(role_keys_seen) == 2, "no two blocks may share the same session"


def test_attach_does_not_mutate_input_role_map():
    briefs = derive_phase_mental_briefs(
        athlete_model=_athlete_model(),
        phase_briefs=_phase_briefs_for_test(),
    )
    original = {
        "weeks": [
            {
                "phase": "GPP",
                "session_roles": [
                    {"role_key": "primary_strength_day", "category": "strength"},
                ],
            }
        ]
    }
    attach_mental_to_weekly_role_map(
        weekly_role_map=original,
        phase_mental_briefs=briefs,
    )
    assert "mental_attachment" not in original["weeks"][0]["session_roles"][0]
    assert "mental_attachments_summary" not in original["weeks"][0]


def test_attach_with_no_active_phase_brief_is_noop():
    weekly_role_map = {
        "weeks": [
            {
                "phase": "SPP",
                "session_roles": [
                    {"role_key": "primary_strength_day", "category": "strength"},
                ],
            }
        ]
    }
    attached = attach_mental_to_weekly_role_map(
        weekly_role_map=weekly_role_map,
        phase_mental_briefs={},
    )
    assert "mental_attachment" not in attached["weeks"][0]["session_roles"][0]


def test_writing_rules_forbid_standalone_mental_session():
    rules_lower = " ".join(MENTAL_TRAINING_WRITING_RULES).lower()
    assert "standalone session" in rules_lower or "never scheduled as a separate session" in rules_lower
    assert "generic motivation" in rules_lower
    assert "phase dose" in rules_lower or "honor the phase dose" in rules_lower


def test_finalizer_guide_mentions_integration_and_dose():
    text = MENTAL_TRAINING_FINALIZER_GUIDE.lower()
    assert "mental" in text
    assert "do not invent" in text or "do not invent one" in text
    assert "phase dose" in text or "gpp" in text


def _training_context_with_blocks(blocks: list[str]) -> TrainingContext:
    return TrainingContext(
        fatigue="low",
        training_frequency=4,
        days_available=4,
        training_days=["Monday", "Tuesday", "Thursday", "Saturday"],
        injuries=[],
        style_technical=["boxing"],
        style_tactical=["pressure_fighter"],
        weaknesses=["gas_tank"],
        equipment=["heavy_bag", "bodyweight"],
        weight_cut_risk=False,
        weight_cut_pct=0.0,
        fight_format="boxing",
        status="amateur",
        key_goals=["conditioning"],
        training_preference="balanced",
        mental_block=blocks,
        age=27,
        weight=70.0,
        prev_exercises=[],
        recent_exercises=[],
        phase_weeks={"GPP": 2, "SPP": 2, "TAPER": 1, "days": {"GPP": 0, "SPP": 0, "TAPER": 0}},
        days_until_fight=35,
    )


def test_build_stage2_payload_attaches_mental_training_to_phase_briefs_and_pools():
    training_context = _training_context_with_blocks(["pressure", "rushing"])

    payload = build_stage2_payload(
        training_context=training_context,
        mapped_format="boxing",
        record="3-0",
        rounds_format="3x3",
        camp_len=5,
        short_notice=False,
        restrictions=[],
        phase_weeks={"GPP": 2, "SPP": 2, "TAPER": 1, "days": {"GPP": 0, "SPP": 0, "TAPER": 0}},
        strength_blocks={"GPP": None, "SPP": None, "TAPER": None},
        conditioning_blocks={
            "GPP": {"grouped_drills": {}, "why_log": [], "missing_systems": [], "candidate_reservoir": {}},
            "SPP": {"grouped_drills": {}, "why_log": [], "missing_systems": [], "candidate_reservoir": {}},
            "TAPER": {"grouped_drills": {}, "why_log": [], "missing_systems": [], "candidate_reservoir": {}},
        },
        rehab_blocks={"GPP": "", "SPP": "", "TAPER": ""},
    )

    for phase in ("GPP", "SPP", "TAPER"):
        brief = payload["phase_briefs"][phase]
        assert "mental_training" in brief, f"phase {phase} should carry mental_training"
        assert brief["mental_training"]["primary_blocks"] == ["pressure", "rushing"]

        pool = payload["candidate_pools"][phase]
        assert "mental_slots" in pool
        assert pool["mental_slots"], f"phase {phase} should emit at least one mental slot"

    rules = " ".join(payload["rewrite_guidance"]["writing_rules"]).lower()
    assert "mental" in rules
    assert "standalone session" in rules or "never scheduled as a separate session" in rules
    assert payload["rewrite_guidance"]["mental_training_guide"]


def test_build_planning_brief_surfaces_mental_training_in_phase_strategy_and_role_map():
    training_context = _training_context_with_blocks(["pressure"])

    payload = build_stage2_payload(
        training_context=training_context,
        mapped_format="boxing",
        record="3-0",
        rounds_format="3x3",
        camp_len=5,
        short_notice=False,
        restrictions=[],
        phase_weeks={"GPP": 2, "SPP": 2, "TAPER": 1, "days": {"GPP": 0, "SPP": 0, "TAPER": 0}},
        strength_blocks={"GPP": None, "SPP": None, "TAPER": None},
        conditioning_blocks={
            "GPP": {"grouped_drills": {}, "why_log": [], "missing_systems": [], "candidate_reservoir": {}},
            "SPP": {"grouped_drills": {}, "why_log": [], "missing_systems": [], "candidate_reservoir": {}},
            "TAPER": {"grouped_drills": {}, "why_log": [], "missing_systems": [], "candidate_reservoir": {}},
        },
        rehab_blocks={"GPP": "", "SPP": "", "TAPER": ""},
    )
    brief = build_planning_brief(
        athlete_model=payload["athlete_model"],
        restrictions=payload["restrictions"],
        phase_briefs=payload["phase_briefs"],
        candidate_pools=payload["candidate_pools"],
        omission_ledger=payload["omission_ledger"],
        rewrite_guidance=payload["rewrite_guidance"],
    )

    # phase_strategy keeps a compact mental_training summary per phase
    for phase in ("GPP", "SPP", "TAPER"):
        strategy = brief["phase_strategy"][phase]
        assert "mental_training" in strategy
        mental = strategy["mental_training"]
        assert mental["primary_blocks"] == ["pressure"]
        assert mental["weekly_pattern"]
        assert "mental" in strategy["slot_counts"]
        assert strategy["slot_counts"]["mental"] >= 1

    # weekly_role_map carries mental_attachments_summary on at least one week
    weeks = brief["weekly_role_map"].get("weeks") or []
    assert weeks
    assert any(week.get("mental_attachments_summary") for week in weeks)


def test_no_mental_blocks_falls_back_to_generic_intention():
    briefs = derive_phase_mental_briefs(
        athlete_model=_athlete_model(mental_blocks=[]),
        phase_briefs=_phase_briefs_for_test(),
    )
    gpp = briefs["GPP"]
    assert gpp["primary_blocks"] == ["generic"]
    assert gpp["block_briefs"]
    assert gpp["block_briefs"][0]["drills"]


def test_high_fatigue_changes_coach_voice_and_rules():
    briefs = derive_phase_mental_briefs(
        athlete_model=_athlete_model(fatigue="high", readiness_flags=["high_fatigue"]),
        phase_briefs=_phase_briefs_for_test(),
    )
    spp = briefs["SPP"]
    rules_lower = " ".join(spp["integration_rules"]).lower()
    assert "fatigue" in rules_lower


def test_active_weight_cut_softens_mental_load():
    briefs = derive_phase_mental_briefs(
        athlete_model=_athlete_model(
            weight_cut_risk=True,
            weight_cut_pct=4.5,
            readiness_flags=["active_weight_cut"],
        ),
        phase_briefs=_phase_briefs_for_test(),
    )
    rules_lower = " ".join(briefs["SPP"]["integration_rules"]).lower()
    assert "cut" in rules_lower
    do_not_lower = " ".join(briefs["SPP"]["do_not"]).lower()
    assert "cut" in do_not_lower or "visualization" in do_not_lower


def test_finalizer_packet_preserves_mental_attachment_and_summary():
    """The compact LLM-facing packet must surface mental_attachment and
    mental_attachments_summary so the finalizer can render mental cues on the
    right sessions."""
    training_context = _training_context_with_blocks(["pressure", "attention"])

    payload = build_stage2_payload(
        training_context=training_context,
        mapped_format="boxing",
        record="3-0",
        rounds_format="3x3",
        camp_len=5,
        short_notice=False,
        restrictions=[],
        phase_weeks={"GPP": 2, "SPP": 2, "TAPER": 1, "days": {"GPP": 0, "SPP": 0, "TAPER": 0}},
        strength_blocks={"GPP": None, "SPP": None, "TAPER": None},
        conditioning_blocks={
            "GPP": {"grouped_drills": {}, "why_log": [], "missing_systems": [], "candidate_reservoir": {}},
            "SPP": {"grouped_drills": {}, "why_log": [], "missing_systems": [], "candidate_reservoir": {}},
            "TAPER": {"grouped_drills": {}, "why_log": [], "missing_systems": [], "candidate_reservoir": {}},
        },
        rehab_blocks={"GPP": "", "SPP": "", "TAPER": ""},
    )
    brief = build_planning_brief(
        athlete_model=payload["athlete_model"],
        restrictions=payload["restrictions"],
        phase_briefs=payload["phase_briefs"],
        candidate_pools=payload["candidate_pools"],
        omission_ledger=payload["omission_ledger"],
        rewrite_guidance=payload["rewrite_guidance"],
    )

    packet = build_stage2_finalizer_packet(
        stage2_payload=payload,
        planning_brief=brief,
    )

    weeks = packet["selected_plan"]["weekly_role_map"].get("weeks") or []
    assert weeks, "packet should carry weekly_role_map weeks"

    summary_count = sum(1 for week in weeks if week.get("mental_attachments_summary"))
    assert summary_count >= 1, "packet should preserve mental_attachments_summary on at least one week"

    # At least one role on at least one week should carry mental_attachment.
    attachment_count = sum(
        1
        for week in weeks
        for role in (week.get("session_roles") or [])
        if role.get("mental_attachment")
    )
    assert attachment_count >= 1, "packet should preserve mental_attachment on at least one role"


def test_attachment_is_skipped_when_no_role_has_block_affinity():
    """If no session role has any affinity for the phase's blocks, the attacher
    leaves all roles clean and reports the block as uncovered."""
    weekly_role_map = {
        "weeks": [
            {
                "phase": "GPP",
                # Synthetic role with no role_key and an unknown category — no
                # affinity should be discovered for any block.
                "session_roles": [
                    {"role_key": "", "category": "unknown_category"},
                ],
            }
        ]
    }
    briefs = derive_phase_mental_briefs(
        athlete_model=_athlete_model(mental_blocks=["pressure"]),
        phase_briefs=_phase_briefs_for_test(),
    )
    attached = attach_mental_to_weekly_role_map(
        weekly_role_map=weekly_role_map,
        phase_mental_briefs=briefs,
    )
    role = attached["weeks"][0]["session_roles"][0]
    assert "mental_attachment" not in role
    summary = attached["weeks"][0]["mental_attachments_summary"]
    assert summary["covered_blocks"] == []
    assert "pressure" in summary["uncovered_blocks"]
