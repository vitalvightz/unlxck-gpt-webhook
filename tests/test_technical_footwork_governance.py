"""Cubic finding C: rep-based technical footwork must be first-class through
every governance layer that sees the bank — bank validation, the selector, the
late-window evaluator, and Stage 2 serialization — never penalised or flagged
for missing timed-dose metadata simply because it intentionally uses reps.
"""
from __future__ import annotations

from copy import deepcopy

from fightcamp import bank_schema, conditioning
from fightcamp.stage2_payload import _serialize_conditioning_option


BANK = {d["name"]: d for d in conditioning.get_technical_footwork_bank()}
_TIMED_DOSE_ISSUES = {"missing_work_sec", "missing_rounds", "missing_total_minutes"}
REP_DRILL = "Sprawl Exit to Ring Angle"   # sets + reps_per_side + rest_sec + quality_stop_rule
TIMED_DRILL = "Stance Reset Line Drill"   # work_sec + rounds + rest_sec


# --- 1. Bank validation -------------------------------------------------------

def test_bank_validation_does_not_flag_rep_based_footwork_for_missing_timed_dose():
    rep = BANK[REP_DRILL]
    timed = BANK[TIMED_DRILL]
    # A rep-based drill is not flagged for missing timed-dose metadata...
    assert not (_TIMED_DOSE_ISSUES & set(rep.get("_schema_issues", [])))
    # ...and a timed drill is not either. Both validate on equal footing.
    assert not (_TIMED_DOSE_ISSUES & set(timed.get("_schema_issues", [])))
    # The dedicated dose contract recognises both shapes.
    assert bank_schema._technical_footwork_dose_ok(rep)
    assert bank_schema._technical_footwork_dose_ok(timed)


def test_bank_validation_still_rejects_a_drill_with_no_valid_dose():
    # A drill that carries neither a valid timed nor a valid quality-rep dose is
    # flagged — the contract is enforced, not fabricated away.
    broken = deepcopy(BANK[REP_DRILL])
    broken.pop("quality_stop_rule", None)  # invalidates the quality-rep shape
    broken.pop("_schema_issues", None)
    bank_schema.validate_training_item(
        broken, source="technical_footwork_bank.json", require_phases=True, mode="runtime"
    )
    assert "missing_technical_footwork_dose" in broken.get("_schema_issues", [])
    # And a valid rep drill run through the same validator is clean of both the
    # dose-contract issue and the timed-dose issues.
    valid = deepcopy(BANK[REP_DRILL])
    valid.pop("_schema_issues", None)
    bank_schema.validate_training_item(
        valid, source="technical_footwork_bank.json", require_phases=True, mode="runtime"
    )
    issues = set(valid.get("_schema_issues", []))
    assert "missing_technical_footwork_dose" not in issues
    assert not (_TIMED_DOSE_ISSUES & issues)


# --- 2. Selector --------------------------------------------------------------

def _flags(sport: str, style: str) -> dict:
    return {
        "phase": "SPP",
        "fatigue": "low",
        "sport": sport,
        "fight_format": sport,
        "style_tactical": [style],
        "style_technical": [sport],
        "equipment": ["bodyweight"],
        "key_goals": ["footwork"],
        "weaknesses": [],
        "injuries": [],
        "days_until_fight": 21,
    }


def test_selector_keeps_rep_based_footwork_selectable():
    selected = conditioning.select_technical_footwork_drill(
        _flags("mma", "wrestler"), set(), []
    )
    assert selected is not None
    assert selected["name"] == REP_DRILL
    # It is genuinely rep-based, not silently converted to timed dose.
    assert selected.get("reps_per_side") == 3
    assert "work_sec" not in selected


# --- 3. Late-window evaluator -------------------------------------------------

def _governed_footwork_twin(*, dose: str) -> dict:
    """Two drills identical in everything the late evaluator gates on (phase,
    late_windows, cost, governance) except the dose shape, to isolate whether a
    rep-based dose is penalised where a timed one is not."""
    base = {
        "name": f"Twin {dose}",
        "modality": "technical_footwork",
        "system": "aerobic",
        "phases": ["TAPER"],
        "tags": ["footwork", "movement_quality"],
        "late_windows": ["d6_to_d5"],
        "impact_cost": "low",
        "movement_cost": "low",
        "lactate_load": "low",
        "rpe": 5,
        "rpe_max": 5,
        "stress_class": "support",
        "cost_class": "low",
        "support_only": True,
        "meaningful_stress": False,
        "rest_sec": 60,
    }
    if dose == "timed":
        base.update({"work_sec": 60, "rounds": 2})
    else:
        base.update({"sets": 2, "reps_per_side": 4, "quality_stop_rule": "Stop when quality drops."})
    bank_schema.validate_training_item(
        base, source="technical_footwork_bank.json", require_phases=True, mode="runtime"
    )
    return base


def test_late_evaluator_treats_rep_and_timed_footwork_identically():
    timed = _governed_footwork_twin(dose="timed")
    rep = _governed_footwork_twin(dose="rep")

    # Neither twin is flagged for missing timed-dose metadata after validation.
    assert not (_TIMED_DOSE_ISSUES & set(rep.get("_schema_issues", [])))

    for window in ("d13_to_d8", "d6_to_d5"):
        timed_eval = conditioning._evaluate_conditioning_late_window(
            timed, system="aerobic", window=window, bridge_rules=None,
            source="technical_footwork_bank.json",
        )
        rep_eval = conditioning._evaluate_conditioning_late_window(
            rep, system="aerobic", window=window, bridge_rules=None,
            source="technical_footwork_bank.json",
        )
        # The rep-based twin is neither blocked nor penalised where the timed
        # twin is clean: no false late-window/dose penalty for using reps.
        assert rep_eval["blocked"] == timed_eval["blocked"], window
        assert set(rep_eval["penalty_codes"]) == set(timed_eval["penalty_codes"]), window
        assert set(rep_eval["block_codes"]) == set(timed_eval["block_codes"]), window


# --- 4. Stage 2 serialization -------------------------------------------------

def test_stage2_serialization_carries_rep_dose_without_fabricated_timed_metadata():
    option = _serialize_conditioning_option(
        BANK[REP_DRILL], conditioning.TECHNICAL_FOOTWORK_GROUP, "style-function match"
    )
    prescription = option["technical_footwork_prescription"]
    assert prescription["reps_per_side"] == 3
    assert prescription["sets"] == 2
    assert "work_sec" not in prescription
    assert "rounds" not in prescription
    # The human-facing prescription reflects the truthful rep dose.
    assert "clean reactions each direction" in option["prescription"]
