"""The live rehab stage has to survive the whole plan-generation path.

PR5's selector is only worth having if production actually reaches it. The
regression here is deliberately end-to-end rather than a unit test of the
selector: it starts from an ``injury_flags`` row, resolves the stage with the
real resolver (no hand-written stage string), runs real plan generation against
the real bank, and finishes at the structured rehab slot the app renders.

Every link is a place a previous revision silently dropped the stage:

    injury flag
      -> api.contracts.rehab_stage.resolve_rehab_stage     (RESTORE)
      -> parsed injury entry
      -> rehab_protocols._merge_injuries_by_location       (whitelist)
      -> generate_rehab_protocols                          (live-stage branch)
      -> rehab_selector.select_rehab_candidate
      -> stage2_payload._build_rehab_slots                 (structured card)
      -> canonical rehab_drill_id
"""

from __future__ import annotations

import pytest

from api.contracts.rehab_stage import (
    MAX_RESOLVABLE_STAGE,
    STAGE_CALM,
    STAGE_RESTORE,
    resolve_rehab_stage,
)
from fightcamp import rehab_protocols
from fightcamp.rehab_protocols import generate_rehab_protocols, rehab_drill_by_id
from fightcamp.stage2_payload import _build_rehab_slots


def _injury_flag(**overrides) -> dict:
    """An ankle sprain the athlete has reported on again, as improving."""
    flag = {
        "id": "ankle-1",
        "body_area": "left ankle",
        "description": "ankle sprain",
        "severity": "moderate",
        "status": "monitoring",
        "latest_reported_status": "improving",
        "created_at": "2026-07-01",
    }
    flag.update(overrides)
    return flag


def _parsed_entry_from_flag(flag: dict, stage: str) -> dict:
    """The injury as plan generation receives it, carrying the resolved stage."""
    return {
        "canonical_location": "ankle",
        "location": "ankle",
        "injury_type": "sprain",
        "rehab_type": "sprain",
        "severity": flag["severity"],
        "laterality": "left",
        "athlete_id": "athlete-a",
        "id": flag["id"],
        "episode_id": "episode-a",
        "rehab_stage": stage,
    }


def test_resolver_produces_restore_for_a_followed_up_injury():
    """Guard the premise: if this stops being RESTORE the chain below is vacuous."""
    decision = resolve_rehab_stage(_injury_flag())
    assert decision.stage == STAGE_RESTORE


def test_resolved_stage_survives_the_merge_into_plan_generation():
    """The merged group is a whitelist. The live rehab context must be on it."""
    flag = _injury_flag()
    stage = resolve_rehab_stage(flag).stage
    entry = _parsed_entry_from_flag(flag, stage)

    merged = rehab_protocols._merge_injuries_by_location([entry])[0]

    assert merged["rehab_stage"] == stage
    assert merged["injury_id"] == flag["id"]
    assert merged["episode_id"] == "episode-a"
    assert merged["athlete_id"] == "athlete-a"


def test_the_selector_actually_runs_during_plan_generation(monkeypatch):
    """The live-stage branch is reached, with the resolved stage, not bypassed."""
    flag = _injury_flag()
    stage = resolve_rehab_stage(flag).stage
    seen: list[str] = []

    real_select = rehab_protocols.select_rehab_candidate

    def spy(**kwargs):
        seen.append(kwargs["rehab_stage"])
        return real_select(**kwargs)

    monkeypatch.setattr(rehab_protocols, "select_rehab_candidate", spy)

    generate_rehab_protocols(
        injury_string="left ankle sprain",
        exercise_data=[],
        current_phase="GPP",
        parsed_entries=[_parsed_entry_from_flag(flag, stage)],
    )

    assert seen == [STAGE_RESTORE]


@pytest.mark.parametrize("stage", [STAGE_CALM, STAGE_RESTORE])
def test_live_stage_reaches_the_structured_rehab_block_with_a_canonical_id(stage):
    """The full chain, ending at the id the app stores against a completion."""
    flag = _injury_flag()
    entry = _parsed_entry_from_flag(flag, stage)

    rehab_block, _seen = generate_rehab_protocols(
        injury_string="left ankle sprain",
        exercise_data=[],
        current_phase="GPP",
        parsed_entries=[entry],
    )

    # Stage-aware selection must not empty the rehab block: the whole bank is
    # still unmigrated for rehab_stage, and rejecting it wholesale is what
    # replaced real drills with a "consult a professional" note.
    assert "Consult with a healthcare professional" not in rehab_block
    assert rehab_block.strip()

    slots = _build_rehab_slots(rehab_block, "GPP")
    assert slots, "no structured rehab slot was produced"

    drill_id = slots[0]["selected"]["rehab_drill_id"]
    assert drill_id, "structured rehab slot carries no canonical bank id"
    assert rehab_drill_by_id(drill_id) is not None


def test_selection_narrows_the_block_to_the_chosen_drill():
    """Stage-aware selection is a decision, not a passthrough of every drill."""
    flag = _injury_flag()
    entry = _parsed_entry_from_flag(flag, resolve_rehab_stage(flag).stage)

    with_stage, _ = generate_rehab_protocols(
        injury_string="left ankle sprain",
        exercise_data=[],
        current_phase="GPP",
        parsed_entries=[entry],
    )
    without_stage, _ = generate_rehab_protocols(
        injury_string="left ankle sprain",
        exercise_data=[],
        current_phase="GPP",
        parsed_entries=[{k: v for k, v in entry.items() if k != "rehab_stage"}],
    )

    chosen = _build_rehab_slots(with_stage, "GPP")
    legacy = _build_rehab_slots(without_stage, "GPP")
    assert chosen and legacy
    # One drill is chosen rather than the whole matching group being rendered.
    assert len(chosen) == 1
    assert len(chosen) <= len(legacy)
    # The card keeps its alternates either way — selection narrows what is
    # prescribed, it does not strip the athlete's swap options.
    assert chosen[0]["alternates"]


def test_pr5_does_not_move_the_stage_ceiling():
    assert MAX_RESOLVABLE_STAGE == STAGE_RESTORE


def _block_has_drills(block: str) -> bool:
    return bool(block.strip()) and "Consult with a healthcare professional" not in block


@pytest.mark.parametrize("live_stage", [STAGE_CALM, STAGE_RESTORE])
def test_stage_aware_selection_never_empties_a_block_the_bank_can_fill(live_stage):
    """Across the whole real bank, turning selection on never removes rehab.

    Selection narrows *which* drill is prescribed. If it also silently removed
    rehab from injuries the bank covers, the athlete would get a "see a
    professional" note where they used to get drills — which is what happens
    when an unmigrated bank field is treated as a rejection.
    """
    bank = rehab_protocols.get_rehab_bank()
    pairs = sorted(
        {
            (entry["location"], entry["type"])
            for entry in bank
            if entry.get("location") and entry.get("type")
        }
    )
    assert pairs, "the real bank should not be empty"

    def block(location, injury_type, stage):
        entry = {
            "canonical_location": location,
            "location": location,
            "injury_type": injury_type,
            "rehab_type": injury_type,
            "severity": "moderate",
            "laterality": "left",
            "id": "injury-a",
            "episode_id": "episode-a",
        }
        if stage:
            entry["rehab_stage"] = stage
        rendered, _ = generate_rehab_protocols(
            injury_string=f"{location} {injury_type}",
            exercise_data=[],
            current_phase="GPP",
            parsed_entries=[entry],
        )
        return rendered

    emptied = [
        (location, injury_type)
        for location, injury_type in pairs
        if _block_has_drills(block(location, injury_type, None))
        and not _block_has_drills(block(location, injury_type, live_stage))
    ]
    assert not emptied, f"stage-aware selection emptied {len(emptied)}: {emptied[:5]}"


def test_region_matching_survives_the_parser_and_bank_wording_difference():
    """The parser says "biceps", the bank group says "bicep" — same anatomy.

    Matching on the parser's spelling alone rejected every drill in the group
    and emptied the block.
    """
    entry = {
        "canonical_location": "bicep",
        "location": "bicep",
        "injury_type": "contusion",
        "rehab_type": "contusion",
        "severity": "moderate",
        "laterality": "left",
        "id": "injury-a",
        "episode_id": "episode-a",
        "rehab_stage": STAGE_RESTORE,
    }
    rendered, _ = generate_rehab_protocols(
        injury_string="bicep contusion",
        exercise_data=[],
        current_phase="TAPER",
        parsed_entries=[entry],
    )
    assert _block_has_drills(rendered)


def test_a_drill_with_nothing_to_say_in_this_phase_is_not_a_candidate():
    """Selection runs on prescribable drills, not on drills the phase strips.

    Picking first and filtering by phase afterwards can select a drill whose
    notes name no content for the current phase, leaving an empty block.
    """
    # Notes that use the bank's phase progression only render in the phases
    # they name. This is the same rule the renderer applies.
    phase_specific = {
        "id": "gpp_spp_only",
        "name": "Early Work",
        "notes": "GPP: early control work \u2192 SPP: add resistance",
        "target_regions": ["ankle"],
        "laterality_applicability": "unknown",
    }
    assert rehab_protocols._drill_is_prescribable(phase_specific, "GPP", "low")
    assert rehab_protocols._drill_is_prescribable(phase_specific, "SPP", "low")
    assert not rehab_protocols._drill_is_prescribable(phase_specific, "TAPER", "low")

    # Notes without a progression apply to every phase.
    unsplit = {
        "id": "any_phase",
        "name": "Any Phase",
        "notes": "steady control work",
        "target_regions": ["ankle"],
    }
    assert rehab_protocols._drill_is_prescribable(unsplit, "TAPER", "low")

    # A drill too aggressive for the severity is not a candidate either.
    aggressive = {
        "id": "plyo",
        "name": "Depth Jump",
        "notes": "explosive reactive hops",
        "target_regions": ["ankle"],
    }
    assert not rehab_protocols._drill_is_prescribable(aggressive, "GPP", "high")

    # A drill with no name can never render.
    assert not rehab_protocols._drill_is_prescribable(
        {"id": "nameless", "notes": "x"}, "GPP", "low"
    )
