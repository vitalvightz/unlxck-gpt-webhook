"""Energy-system classification must match the written prescription.

``system`` is not a free label: ``_has_dense_glycolytic_profile`` keys the
late-window density gate off it, and the Stage-1 selector pools candidates by
it. An entry whose prescription contradicts its system is therefore both a
programming error and a safety one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fightcamp.bank_schema import _has_dense_glycolytic_profile
from fightcamp.conditioning import _conditioning_verified_interval_dose


def _bank(name: str) -> dict[str, dict]:
    return {
        entry["name"]: entry
        for entry in json.loads(Path(f"data/{name}").read_text(encoding="utf-8"))
    }


BANK = _bank("conditioning_bank.json")
STYLE_BANK = _bank("style_conditioning_bank.json")


def test_sled_sprint_finisher_is_classified_from_its_prescription():
    """6 x 20 sec max efforts on 1:2 recovery are lactate work, not alactic.

    Every comparable 20-second interval in the bank -- "Defensive Level Change
    Drill" (10x20s, 40s rest) most exactly -- is glycolytic with a high lactate
    load. This entry was the lone outlier at ATP-PCr / low.
    """
    drill = BANK["Sled Sprint Finisher"]
    assert drill["duration"] == "6x20s sprint, 2:1 rest"
    assert (drill["work_sec"], drill["rest_sec"], drill["rounds"]) == (20, 40, 6)
    assert drill["rpe"] == 9
    assert drill["system"] == "glycolytic"
    assert drill["lactate_load"] == "high"


def test_sled_sprint_finisher_correction_tightens_the_density_gate():
    # The correction must not quietly exempt hard work from late-window gating.
    drill = BANK["Sled Sprint Finisher"]
    assert _has_dense_glycolytic_profile(drill, normalized_system="glycolytic") is True


def test_sled_sprint_finisher_keeps_its_dose_and_cost_metadata():
    drill = BANK["Sled Sprint Finisher"]
    assert drill["phases"] == ["SPP"]
    assert drill["total_minutes"] == 5.33
    assert drill["intensity"] == "max"
    assert drill["impact_cost"] == "low"
    assert drill["movement_cost"] == "low"
    assert "power" in drill["tags"] and "explosive" in drill["tags"]


@pytest.mark.parametrize("bank_name", ["conditioning_bank.json", "style_conditioning_bank.json"])
def test_no_alactic_entry_prescribes_lactate_producing_work(bank_name):
    """No ATP-PCr entry may prescribe long work on incomplete recovery.

    Alactic work is short and fully recovered. 20+ seconds at RPE 8+ with rest
    under twice the work interval is glycolytic by prescription, and labelling
    it ATP-PCr both pools it wrongly and hides it from the density gate.
    """
    offenders = []
    for entry in _bank(bank_name).values():
        if str(entry.get("system")) != "ATP-PCr":
            continue
        dose = _conditioning_verified_interval_dose(entry)
        if dose is None:
            continue
        work, rest, _rounds = dose
        if work >= 20 and rest <= work * 2 and (entry.get("rpe") or 0) >= 8:
            offenders.append(entry["name"])
    assert offenders == []


@pytest.mark.parametrize("bank_name", ["conditioning_bank.json", "style_conditioning_bank.json"])
def test_structural_classification_fields_are_complete(bank_name):
    for entry in _bank(bank_name).values():
        assert entry.get("system"), entry["name"]
        phases = entry.get("phases") or []
        assert phases, entry["name"]
        assert not set(phases) - {"GPP", "SPP", "TAPER"}, entry["name"]


@pytest.mark.parametrize("bank_name", ["conditioning_bank.json", "style_conditioning_bank.json"])
def test_no_taper_entry_carries_a_high_lactate_load(bank_name):
    # Taper-eligible conditioning may be sharp, but never lactate-dense.
    offenders = [
        entry["name"]
        for entry in _bank(bank_name).values()
        if "TAPER" in (entry.get("phases") or []) and str(entry.get("lactate_load")) == "high"
    ]
    assert offenders == []
