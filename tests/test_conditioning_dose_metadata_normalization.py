"""Regression tests for the conditioning dose-metadata normalisation pass.

These guard the corrections applied to ``data/conditioning_bank.json`` and
``data/style_conditioning_bank.json`` by
``tools/audit_conditioning_dose_metadata.py``.

The dose contract under test:

    work_sec       seconds per work interval
    rest_sec       seconds of genuine recovery between intervals
    rounds         number of work intervals
    total_minutes  full elapsed block time = (rounds*work_sec + (rounds-1)*rest_sec)/60

The pass fixes work-only / missing ``total_minutes`` and missing ``rest_sec`` for
timed interval drills whose written prescription states an explicit discrete rest.
It must NOT redose drills, and must NOT touch the rep-count / distance ``work_sec``
entries that cannot be resolved from the prescription alone.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.audit_conditioning_dose_metadata import classify, elapsed_minutes

def _load(name: str) -> dict:
    return {
        entry["name"]: entry
        for entry in json.loads(Path(f"data/{name}").read_text(encoding="utf-8"))
    }


_BANK = _load("conditioning_bank.json")
_STYLE_BANK = _load("style_conditioning_bank.json")

# Derived directly from the banks via the auditor's classifier so the tests do
# not depend on any generated report artifact.
_CLEAN = [e for e in _BANK.values() if classify(e)[0] == "ok"]
_AMBIGUOUS = {e["name"]: classify(e)[1] for e in _BANK.values() if classify(e)[0] == "ambiguous"}
_STYLE_CLEAN = [e for e in _STYLE_BANK.values() if classify(e)[0] == "ok"]


def _elapsed(work_sec: float, rest_sec: float, rounds: float) -> float:
    return round((work_sec * rounds + (rounds - 1) * rest_sec) / 60, 2)


# --- Canonical example from the linked plan --------------------------------


def test_plyo_step_up_intervals_encodes_work_rest_and_elapsed_block():
    drill = _BANK["Plyo Step-Up Intervals"]
    # 6 x 30s work with 90s rest -> three minutes is WORK time, not elapsed.
    assert drill["work_sec"] == 30
    assert drill["rest_sec"] == 90
    assert drill["rounds"] == 6
    assert drill["total_minutes"] == 10.5
    assert drill["total_minutes"] == _elapsed(30, 90, 6)


def test_plyo_step_up_intervals_preserves_training_purpose():
    # The correction must not redose or reclassify the drill.
    drill = _BANK["Plyo Step-Up Intervals"]
    assert drill["system"] == "glycolytic"
    assert drill["intensity"] == "high"
    assert drill["lactate_load"] == "high"
    assert drill["rpe"] == 8
    assert drill["duration"] == "6x30s on/1:30 off"  # readable prescription preserved


# --- Contract holds for every clean timed-interval entry -------------------


def test_every_clean_timed_interval_satisfies_the_elapsed_contract():
    # The bank must contain a healthy number of contract-clean interval drills.
    assert len(_CLEAN) >= 50
    for entry in _CLEAN:
        assert entry["total_minutes"] == elapsed_minutes(
            entry["work_sec"], entry["rest_sec"], entry["rounds"]
        )


@pytest.mark.parametrize("entry", _CLEAN, ids=[e["name"] for e in _CLEAN])
def test_clean_timed_interval_units_are_valid(entry):
    # rest_sec is whole seconds of genuine recovery.
    assert isinstance(entry["rest_sec"], int)
    assert entry["rest_sec"] > 0
    # rounds is a positive whole number of intervals.
    assert isinstance(entry["rounds"], int)
    assert entry["rounds"] >= 2
    # total_minutes is elapsed block time, strictly greater than work-only time.
    work_only = (entry["work_sec"] * entry["rounds"]) / 60
    assert entry["total_minutes"] > work_only


def test_no_timed_interval_leaves_a_stated_rest_unencoded():
    # After the pass no auto-correctable entry should remain in either bank: the
    # auditor must report zero remaining ``fix`` actions.
    remaining = [
        e["name"]
        for bank in (_BANK, _STYLE_BANK)
        for e in bank.values()
        if classify(e)[0] == "fix"
    ]
    assert remaining == []


# --- style_conditioning_bank.json satisfies the same contract --------------


def test_style_bank_clean_timed_intervals_satisfy_the_elapsed_contract():
    # The style bank was normalised in the same pass; every clean timed interval
    # must carry elapsed-convention total_minutes.
    assert len(_STYLE_CLEAN) >= 150
    for entry in _STYLE_CLEAN:
        assert entry["total_minutes"] == elapsed_minutes(
            entry["work_sec"], entry["rest_sec"], entry["rounds"]
        )


def test_style_bank_word_order_prescription_is_corrected():
    # "5sec work, 60sec rest x 8 rounds" -> elapsed (40 + 7*60)/60 = 7.67, not 7.
    drill = _STYLE_BANK["Entry-Exit Burst"]
    assert drill["work_sec"] == 5
    assert drill["rest_sec"] == 60
    assert drill["rounds"] == 8
    assert drill["total_minutes"] == 7.67
    assert drill["total_minutes"] == elapsed_minutes(5, 60, 8)


# --- Purpose retained: sample across systems -------------------------------


def test_corrected_entries_retain_energy_system_labels():
    # Spot-check that corrections spanned several energy systems and none were
    # flipped by the metadata fix (systems come straight from the bank).
    assert _BANK["Hill Sprint Repeats"]["system"] == "glycolytic"
    assert _BANK["Pad Round Triples"]["system"] == "glycolytic"
    assert _BANK["Sled Push Aerobic Intervals"]["system"] == "aerobic"


# --- Ambiguous entries must be left untouched (no auto-redose) --------------


def test_rep_encoded_plyo_entry_is_reported_not_modified():
    # "Depth Jump to Sprint" prescribes 5x3 reps: work_sec=3 is a rep count, not
    # seconds. The pass must leave it exactly as-is and flag it for manual review.
    drill = _BANK["Depth Jump to Sprint"]
    assert drill["work_sec"] == 3
    assert drill["rest_sec"] == 120
    assert drill["total_minutes"] == 0.25
    assert "Depth Jump to Sprint" in _AMBIGUOUS
    assert "reps/distance" in _AMBIGUOUS["Depth Jump to Sprint"]


def test_active_recovery_interval_is_reported_not_modified():
    # "Echo Bike Tempo Intervals" (4x3min hard, 2min easy) has no discrete rest;
    # the easy bout is work, so rest_sec stays unset and total_minutes unchanged.
    drill = _BANK["Echo Bike Tempo Intervals"]
    assert "rest_sec" not in drill or drill["rest_sec"] is None
    assert drill["total_minutes"] == 12
    assert "Echo Bike Tempo Intervals" in _AMBIGUOUS


def test_ambiguous_entries_are_never_clean_timed_intervals():
    clean_names = {entry["name"] for entry in _CLEAN}
    assert clean_names.isdisjoint(_AMBIGUOUS)


# --- Prior corrections remain intact ---------------------------------------


def test_previous_dose_corrections_are_preserved():
    # From tests/test_conditioning_dose_metadata_corrections.py -- the earlier
    # elapsed-convention entries must still satisfy the same contract.
    treadmill = _BANK["Treadmill Hill Sprints"]
    assert treadmill["total_minutes"] == _elapsed(
        treadmill["work_sec"], treadmill["rest_sec"], treadmill["rounds"]
    )
