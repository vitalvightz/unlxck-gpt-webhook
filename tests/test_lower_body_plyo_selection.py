"""Lower-body plyometric selection guarantees and safety regressions.

Covers the seven must-fixes from reports/lower_body_plyometric_audit.md:

* box treated as universally available (removed from equipment gating)
* kettlebells -> kettlebell equipment alias
* bilateral plyos eligible in GPP
* healthy SPP power athlete gets a lower-body plyo inside the D-21..D-8 window
* plyometric dose is not routed through the barbell %1RM template
* unknown-movement strength slots receive in-role alternates

Plus safety regressions that MUST stay green: depth jumps and other
high-impact plyos remain blocked late, and no lower-body plyo appears in the
final week.
"""
from __future__ import annotations

import json
from pathlib import Path

from fightcamp import strength
from fightcamp.strength import (
    _classify_prescription_type,
    _prescription_templates,
    equipment_score_adjust,
)
from fightcamp.stage2_payload import _build_strength_slots
from fightcamp.training_context import known_equipment, normalize_equipment_list


BANK = json.loads(Path("data/exercise_bank.json").read_text(encoding="utf-8"))
BY_NAME = {e["name"]: e for e in BANK}

BILATERAL_PLYOS = ("Jump Squat", "Box Jump", "Jump-in-Place (Max Frequency)")
BOX_EXERCISES = (
    "Box Jump",
    "Ballistic Box Jump (Min Ground Contact)",
    "Single-Leg Box Jump",
    "Depth Jump (Stick Landing)",
    "Depth Jump to Sprint",
    "Single-Leg Depth Drop (Stick Landing)",
    "Lateral Box Push-Off",
)


def _reset_caches() -> None:
    strength._exercise_bank_cache = None
    strength._universal_strength_cache = None
    strength._universal_strength_names_cache = None


def _strength_flags(days_until_fight: int, **overrides) -> dict:
    phase = "SPP" if days_until_fight >= 8 else "TAPER"
    base = {
        "phase": phase,
        "fatigue": "low",
        "fight_format": "boxing",
        "sport": "boxing",
        "style_tactical": [],
        "style_technical": ["boxing"],
        # Deliberately NO box in equipment: box must be universally available.
        "equipment": ["bodyweight", "medicine_ball", "bands", "dumbbells", "barbell", "trap_bar"],
        "training_days": ["Mon", "Wed", "Fri"],
        "training_frequency": 3,
        "days_available": 3,
        "key_goals": ["power"],
        "weaknesses": ["power"],
        "injuries": [],
        "days_until_fight": days_until_fight,
    }
    return {**base, **overrides}


def _selected_names(days_until_fight: int, **overrides) -> list[str]:
    _reset_caches()
    result = strength.generate_strength_block(
        flags=_strength_flags(days_until_fight, **overrides),
        weaknesses=overrides.get("weaknesses", ["power"]),
    )
    return [e.get("name") for e in result["exercises"]]


# --------------------------------------------------------------------------- #
# H3 — box is universally available
# --------------------------------------------------------------------------- #
def test_box_removed_from_exercise_equipment():
    for name in BOX_EXERCISES:
        tokens = normalize_equipment_list(BY_NAME[name].get("equipment", []))
        assert "box" not in tokens, f"{name} still gates on 'box': {tokens}"


def test_box_exercises_selectable_without_declaring_box():
    # An athlete who never ticked a box must still be able to reach box work.
    assert equipment_score_adjust(
        BY_NAME["Box Jump"].get("equipment", []), ["bodyweight"], known_equipment
    ) == 0


# --------------------------------------------------------------------------- #
# H4 — kettlebells -> kettlebell alias
# --------------------------------------------------------------------------- #
def test_kettlebells_intake_token_normalizes_to_kettlebell():
    assert normalize_equipment_list(["kettlebells"]) == ["kettlebell"]


def test_kettlebell_exercise_reachable_when_athlete_declares_kettlebells():
    assert equipment_score_adjust("kettlebell", ["kettlebells"], known_equipment) == 0


# --------------------------------------------------------------------------- #
# H2 — bilateral plyos available in GPP
# --------------------------------------------------------------------------- #
def test_bilateral_plyos_available_in_gpp():
    for name in ("Jump Squat", "Box Jump"):
        assert "GPP" in BY_NAME[name].get("phases", []), f"{name} is not GPP-eligible"


# --------------------------------------------------------------------------- #
# H1 — the D-21..D-8 dead zone is closed
# --------------------------------------------------------------------------- #
def test_bilateral_plyo_has_late_windows_backfilled():
    for name in BILATERAL_PLYOS:
        windows = BY_NAME[name].get("late_windows") or []
        assert "d21_to_d14" in windows and "d13_to_d8" in windows, (
            f"{name} late_windows={windows}"
        )


def test_healthy_power_athlete_gets_lower_body_plyo_at_d21():
    selected = _selected_names(21)
    assert any(name in BILATERAL_PLYOS for name in selected), selected


def test_healthy_power_athlete_gets_lower_body_plyo_at_d10():
    selected = _selected_names(10)
    assert any(name in BILATERAL_PLYOS for name in selected), selected


# --------------------------------------------------------------------------- #
# H6 — plyometric dose is not a barbell %1RM prescription
# --------------------------------------------------------------------------- #
def test_loaded_jump_not_routed_to_barbell_template():
    name = "Trap Bar Jump"
    ptype = _classify_prescription_type(BY_NAME[name])
    assert ptype != "barbell", f"{name} routed to barbell template"
    template = _prescription_templates("SPP")[ptype]
    assert "1RM" not in template, f"{name} prescription mentions 1RM: {template}"


def test_single_leg_box_jump_not_general_reps():
    ptype = _classify_prescription_type(BY_NAME["Single-Leg Box Jump"])
    assert ptype == "ballistic", ptype


def test_contrast_pairs_keep_contrast_template():
    # A contrast/complex pair (RDL -> broad jump) legitimately wants the loaded
    # contrast prescription and must NOT be rerouted to the light ballistic one.
    ptype = _classify_prescription_type(BY_NAME["Heavy RDL → Broad Jump"])
    assert ptype == "barbell", ptype


# --------------------------------------------------------------------------- #
# H5 — unknown-movement slots get in-role alternates
# --------------------------------------------------------------------------- #
def test_unknown_movement_slot_uses_strength_support_role():
    alt = {"name": "Bodyweight Power Alt", "movement": "unknown", "tags": ["explosive"], "equipment": ["bodyweight"]}
    selected = {"name": "Reactive Bound", "movement": "unknown", "tags": ["explosive"], "equipment": ["bodyweight"]}
    strength_block = {
        "exercises": [selected],
        "num_sessions": 1,
        "why_log": [{"name": "Reactive Bound", "reasons": {}, "explanation": "x"}],
        "candidate_reservoir": {
            "strength_support": [
                {"exercise": selected, "score": 2.0, "reasons": {}, "explanation": "x", "score_evidence": {}},
                {"exercise": alt, "score": 1.5, "reasons": {}, "explanation": "y", "score_evidence": {}},
            ]
        },
    }
    slots = _build_strength_slots(strength_block, "SPP")
    assert len(slots) == 1
    assert slots[0]["role"] == "strength_support"
    assert [a["name"] for a in slots[0]["alternates"]] == ["Bodyweight Power Alt"]


# --------------------------------------------------------------------------- #
# SAFETY REGRESSIONS — must stay green
# --------------------------------------------------------------------------- #
def test_depth_jumps_never_reach_selection_inside_late_window():
    for day in (21, 13, 10, 8):
        selected = _selected_names(day)
        for banned in (
            "Depth Jump (Stick Landing)",
            "Depth Jump to Sprint",
            "Single-Leg Depth Drop (Stick Landing)",
            "Single-Leg Box Jump",
        ):
            assert banned not in selected, f"D-{day} surfaced {banned}: {selected}"


def test_no_lower_body_plyo_in_final_week():
    plyo_names = {
        name
        for name, e in BY_NAME.items()
        if e.get("category") in {"lower_body", "lateral", "locomotion", "reactive"}
        and any(w in name.lower() for w in ("jump", "hop", "bound", "depth"))
    }
    for day in (6, 5, 4, 3, 2, 1):
        selected = set(_selected_names(day))
        leaked = selected & plyo_names
        assert not leaked, f"D-{day} leaked lower-body plyos: {leaked}"


def test_loaded_trap_bar_jump_stays_blocked_late():
    # Metadata backfill must not surface the loaded trap-bar jump late.
    for day in (21, 13, 8):
        selected = _selected_names(day)
        assert "Trap Bar Jump" not in selected, f"D-{day}: {selected}"
