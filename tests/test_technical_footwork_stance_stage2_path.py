"""End-to-end regression: the athlete's stance identity must survive the
canonical production path and reach the Stage 2 handoff/finalizer with the
correct technical-footwork side/stance instruction.

Path under test:

    PlanInput.stance
      -> TrainingContext.stance
      -> _build_athlete_model (athlete_model / athlete_snapshot)
      -> build_planning_brief (athlete_snapshot)
      -> build_stage2_finalizer_packet (compact athlete_model)

The technical-footwork side/stance instruction is derived from the canonical
existing stance identity only — there is no second stance field or ontology.
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from fightcamp import conditioning
from fightcamp.stage2_finalizer_packet import build_stage2_finalizer_packet
from fightcamp.stage2_payload import build_planning_brief, build_stage2_payload
from fightcamp.training_context import TrainingContext


_PHASE_WEEKS = {"GPP": 2, "SPP": 2, "TAPER": 1, "days": {"GPP": 0, "SPP": 0, "TAPER": 0}}


def _training_context(stance: str) -> TrainingContext:
    return TrainingContext(
        fatigue="low",
        training_frequency=4,
        days_available=4,
        training_days=["Monday", "Tuesday", "Thursday", "Saturday"],
        injuries=[],
        style_technical=["boxing"],
        style_tactical=["counter_striker"],
        weaknesses=["footwork"],
        equipment=["bodyweight", "heavy_bag"],
        weight_cut_risk=False,
        weight_cut_pct=0.0,
        fight_format="boxing",
        status="amateur",
        key_goals=["footwork"],
        training_preference="balanced",
        mental_block=[],
        age=25,
        weight=70.0,
        prev_exercises=[],
        recent_exercises=[],
        phase_weeks=_PHASE_WEEKS,
        days_until_fight=35,
        stance=stance,
    )


def _conditioning_blocks_with_footwork(drill_name: str) -> dict:
    """Real technical-footwork bank drill injected into the SPP conditioning
    block exactly as the Stage 1 conditioning generator would hand it off."""
    drill = deepcopy(
        next(
            d
            for d in conditioning.get_technical_footwork_bank()
            if d["name"] == drill_name
        )
    )
    empty = {"grouped_drills": {}, "why_log": [], "missing_systems": [], "candidate_reservoir": {}}
    spp = {
        "grouped_drills": {conditioning.TECHNICAL_FOOTWORK_GROUP: [drill]},
        "why_log": [{"name": drill["name"], "reasons": {}, "explanation": "footwork guarantee"}],
        "missing_systems": [],
        "candidate_reservoir": {},
    }
    return {"GPP": deepcopy(empty), "SPP": spp, "TAPER": deepcopy(empty)}


def _run_pipeline(stance: str, drill_name: str = "Step-Back Pivot Reset"):
    training_context = _training_context(stance)
    payload = build_stage2_payload(
        training_context=training_context,
        mapped_format="boxing",
        record="3-0",
        rounds_format="3x3",
        camp_len=5,
        short_notice=False,
        restrictions=[],
        phase_weeks=_PHASE_WEEKS,
        strength_blocks={"GPP": None, "SPP": None, "TAPER": None},
        conditioning_blocks=_conditioning_blocks_with_footwork(drill_name),
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
    packet = build_stage2_finalizer_packet(stage2_payload=payload, planning_brief=brief)
    return payload, brief, packet


def _footwork_side_instruction(payload: dict) -> str:
    spp = payload["candidate_pools"]["SPP"]
    slot = next(
        s
        for s in spp["conditioning_slots"]
        if s["selected"].get("technical_footwork_prescription")
    )
    return slot["selected"]["technical_footwork_prescription"]["side_instruction"]


@pytest.mark.parametrize(
    ("stance", "expected_side_instruction"),
    [
        ("orthodox", "Start in your orthodox stance and work both directions evenly."),
        ("southpaw", "Start in your southpaw stance and work both directions evenly."),
        ("switch", "Work both directions evenly from each stance."),
        ("", "Work both directions evenly from your normal stance."),
    ],
)
def test_stance_reaches_finalizer_with_correct_side_instruction(
    stance: str, expected_side_instruction: str
):
    payload, brief, packet = _run_pipeline(stance)

    # Stance survives every authoritative hop, reusing the one canonical field.
    assert payload["athlete_model"]["stance"] == stance
    assert brief["athlete_snapshot"]["stance"] == stance
    assert packet["athlete_model"]["stance"] == stance

    # The technical-footwork side/stance instruction is correct at the Stage 2
    # handoff, derived from the canonical stance identity only.
    assert _footwork_side_instruction(payload) == expected_side_instruction


def test_missing_stance_degrades_to_neutral_bilateral_wording():
    payload, brief, packet = _run_pipeline("")

    assert packet["athlete_model"]["stance"] == ""
    side_instruction = _footwork_side_instruction(payload)
    assert side_instruction == "Work both directions evenly from your normal stance."
    # No raw enum leakage and no assumed orthodox/southpaw side.
    assert "orthodox" not in side_instruction.lower()
    assert "southpaw" not in side_instruction.lower()


def test_alternate_stance_drill_reflects_switch_identity():
    # A drill whose own side_rule alternates stances renders alternation wording
    # rather than the raw enum, still keyed off the canonical stance identity.
    payload, _brief, packet = _run_pipeline("switch", drill_name="Switch-Step Stance Recovery")
    assert packet["athlete_model"]["stance"] == "switch"
    side_instruction = _footwork_side_instruction(payload)
    assert side_instruction == "Alternate orthodox and southpaw stances each rep."
    assert "alternate_stances" not in side_instruction
