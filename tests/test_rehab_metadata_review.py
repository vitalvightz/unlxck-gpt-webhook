"""The rehab clinical-metadata review + migration pipeline.

Covers the generator, the deterministic source hash, the conservative proposal
rules, the variable-demand flags, and the hash-verified applicator — and the
safety boundaries the pipeline must never cross: no fabricated demand, no
unknown->safe coercion, no camp-phase stage inference, no historical-exposure
mutation, and LOAD/DYNAMIC/RETURN still unreachable in production.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from api.contracts.load_eligibility import LOAD_CRITERIA_REGISTRY
from api.contracts.rehab_stage import (
    MAX_RESOLVABLE_STAGE,
    STAGE_DYNAMIC,
    STAGE_LOAD,
    STAGE_RESTORE,
    STAGE_RETURN,
)
from fightcamp.rehab_schema import (
    CONTACT_LEVEL_VALUES,
    CONTRACTION_TYPE_VALUES,
    IMPACT_VALUES,
    LATERALITY_APPLICABILITY_VALUES,
    LOAD_VALUES,
    REHAB_FUNCTIONS,
    REHAB_STAGES,
    SPORT_SPECIFICITY_VALUES,
    VELOCITY_VALUES,
)
from tools.apply_rehab_metadata_review import apply_reviews
from tools.generate_rehab_metadata_review import build_ledger
from tools.rehab_metadata_review_lib import (
    FLAG_CONTACT_PROGRESSION,
    FLAG_IMPACT_PROGRESSION,
    FLAG_LOAD_PROGRESSION,
    FLAG_POSSIBLE_DRILL_SPLIT,
    FLAG_VARIABLE_DEMAND,
    MOVEMENT_ARCHETYPES,
    REVIEW_FIELDS,
    REVIEW_STATE_NEEDS_REVIEW,
    REVIEW_STATE_REVIEWED,
    classify_movement_archetype,
    detect_variable_demand_flags,
    iter_msk_drills,
    load_bank,
    propose_metadata,
    render_bank,
    render_ledger,
    source_hash,
)
from tools.report_rehab_metadata_coverage import build_report
from tools.validate_rehab_metadata_review import validate

REPO_ROOT = Path(__file__).resolve().parents[1]
BANK_PATH = REPO_ROOT / "data" / "rehab_bank.json"
LEDGER_PATH = REPO_ROOT / "data" / "rehab_metadata_review.json"
TOOL_FILES = [
    "rehab_metadata_review_lib.py",
    "generate_rehab_metadata_review.py",
    "apply_rehab_metadata_review.py",
    "report_rehab_metadata_coverage.py",
    "validate_rehab_metadata_review.py",
]


def _drill(drill_id="ankle_sprain_iso_hold", name="Isometric Ankle Hold", notes="GPP: gentle isometric hold", **extra):
    base = {
        "id": drill_id,
        "name": name,
        "notes": notes,
        "rehab_stage": None,
        "function": None,
        "equipment": None,
        "impact": None,
        "load": None,
        "velocity": None,
        "target_regions": ["ankle"],
        "laterality_applicability": "unknown",
        "target_tissues": None,
        "contraction_type": "unknown",
        "sport_specificity": "unknown",
        "contact_level": "unknown",
        "evidence_notes": None,
    }
    base.update(extra)
    return base


def _msk_group(*drills, location="ankle", injury_type="sprain"):
    return {"location": location, "type": injury_type, "phase_progression": "GPP", "drills": list(drills)}


def _surface_group(*drills):
    return {"location": "cheek", "type": "laceration", "phase_progression": "GPP", "drills": list(drills)}


# --------------------------------------------------------------------------- #
# Generator
# --------------------------------------------------------------------------- #


def test_01_generator_covers_every_msk_drill():
    entries = load_bank(BANK_PATH)
    ledger = build_ledger(entries)
    msk_ids = [str(d.get("id")) for *_x, d in iter_msk_drills(entries)]
    assert [r["drill_id"] for r in ledger] == msk_ids
    assert len(ledger) == len(msk_ids)


def test_02_surface_drill_is_excluded_from_review():
    entries = [_msk_group(_drill()), _surface_group({"id": "cheek_laceration_clean", "name": "Clean", "notes": "x"})]
    ledger = build_ledger(entries)
    ids = {r["drill_id"] for r in ledger}
    assert "ankle_sprain_iso_hold" in ids
    assert "cheek_laceration_clean" not in ids


def test_03_generator_is_byte_identical_on_rerun():
    entries = load_bank(BANK_PATH)
    first = build_ledger(entries)
    second = build_ledger(entries, prior=first)
    assert render_ledger(first) == render_ledger(second)


def test_committed_ledger_matches_the_generator():
    entries = load_bank(BANK_PATH)
    committed = LEDGER_PATH.read_text(encoding="utf-8")
    prior = json.loads(committed)
    assert render_ledger(build_ledger(entries, prior)) == committed


def test_generator_preserves_a_reviewed_record_verbatim():
    entries = [_msk_group(_drill())]
    reviewed = build_ledger(entries)
    reviewed[0]["review_state"] = REVIEW_STATE_REVIEWED
    reviewed[0]["proposed"]["load"] = "low"
    regenerated = build_ledger(entries, prior=reviewed)
    assert regenerated[0] == reviewed[0]


# --------------------------------------------------------------------------- #
# Source hash
# --------------------------------------------------------------------------- #


def test_04_source_hash_stable_for_unchanged_drill():
    args = dict(drill_id="d", location="ankle", injury_type="sprain", name="N", notes="notes")
    assert source_hash(**args) == source_hash(**args)


def test_05_source_hash_changes_when_notes_change():
    a = source_hash(drill_id="d", location="ankle", injury_type="sprain", name="N", notes="one")
    b = source_hash(drill_id="d", location="ankle", injury_type="sprain", name="N", notes="two")
    assert a != b


# --------------------------------------------------------------------------- #
# Applicator
# --------------------------------------------------------------------------- #


def _reviewed_ledger(entries, **proposed_overrides):
    ledger = build_ledger(entries)
    ledger[0]["review_state"] = REVIEW_STATE_REVIEWED
    ledger[0]["proposed"].update(proposed_overrides)
    return ledger


def test_07_needs_review_entry_cannot_modify_bank():
    entries = [_msk_group(_drill())]
    ledger = build_ledger(entries)  # all needs_review
    ledger[0]["proposed"]["load"] = "low"  # even with a value, needs_review is inert
    applied_entries, applied, stale = apply_reviews(entries, ledger)
    assert applied == [] and stale == []
    assert render_bank(applied_entries) == render_bank(entries)


def test_08_reviewed_entry_applies_values_correctly():
    entries = [_msk_group(_drill())]
    ledger = _reviewed_ledger(entries, load="low", impact="none", velocity="low")
    applied_entries, applied, stale = apply_reviews(entries, ledger)
    assert applied == ["ankle_sprain_iso_hold"] and stale == []
    drill = applied_entries[0]["drills"][0]
    assert (drill["load"], drill["impact"], drill["velocity"]) == ("low", "none", "low")


def test_06_reviewed_entry_with_changed_source_is_stale_and_rejected():
    entries = [_msk_group(_drill())]
    ledger = _reviewed_ledger(entries, load="low")
    # Source changes after review.
    entries[0]["drills"][0]["notes"] = "materially different progression: add load"
    applied_entries, applied, stale = apply_reviews(entries, ledger)
    assert applied == [] and stale == ["ankle_sprain_iso_hold"]
    assert applied_entries[0]["drills"][0]["load"] is None  # not applied
    errors = validate(entries, ledger)
    assert any("STALE_SOURCE_HASH" in e for e in errors)


def test_09_reviewed_unknown_stays_unknown():
    entries = [_msk_group(_drill())]
    ledger = _reviewed_ledger(entries, load="unknown")
    applied_entries, _applied, _stale = apply_reviews(entries, ledger)
    assert applied_entries[0]["drills"][0]["load"] == "unknown"  # not coerced to low/none


def test_10_null_proposed_leaves_bank_value_unchanged():
    entries = [_msk_group(_drill(load=None, impact="moderate"))]
    ledger = _reviewed_ledger(entries, load=None, impact="none")
    applied_entries, _applied, _stale = apply_reviews(entries, ledger)
    drill = applied_entries[0]["drills"][0]
    assert drill["load"] is None  # unresolved proposal never writes
    assert drill["impact"] == "none"  # resolved proposal writes


def test_11_no_unknown_to_none_or_low_coercion_anywhere():
    entries = load_bank(BANK_PATH)
    for record in build_ledger(entries):
        for field in ("load", "impact", "velocity"):
            # proposals never invent a load; impact/velocity are only ever the
            # mechanical facts none/low, never derived from an unknown source.
            assert record["proposed"][field] in (None, "none", "low")
        assert record["proposed"]["load"] is None  # load is never auto-proposed


def test_15_16_17_applicator_preserves_ids_and_ordering():
    entries = [
        _msk_group(_drill("a1", "A1"), _drill("a2", "A2"), location="ankle"),
        _msk_group(_drill("k1", "K1"), location="knee", injury_type="strain"),
    ]
    ledger = build_ledger(entries)
    for record in ledger:
        record["review_state"] = REVIEW_STATE_REVIEWED
        record["proposed"]["load"] = "low"
    applied_entries, _applied, _stale = apply_reviews(entries, ledger)
    assert [g["location"] for g in applied_entries] == ["ankle", "knee"]
    assert [d["id"] for d in applied_entries[0]["drills"]] == ["a1", "a2"]
    assert [d["id"] for d in applied_entries[1]["drills"]] == ["k1"]


def test_18_19_duplicate_debt_and_wound_care_records_preserved():
    surface_drill = {"id": "cheek_laceration_clean", "name": "Clean and dress", "notes": "wound care"}
    entries = [_msk_group(_drill()), _surface_group(surface_drill), _msk_group(_drill(), location="ankle")]
    ledger = _reviewed_ledger(entries, load="low")
    applied_entries, _applied, _stale = apply_reviews(entries, ledger)
    assert len(applied_entries) == 3  # no group merged/removed
    assert applied_entries[1]["drills"][0] == surface_drill  # wound-care byte-identical


def test_20_applicator_second_run_is_a_noop():
    entries = [_msk_group(_drill())]
    ledger = _reviewed_ledger(entries, load="low", impact="none")
    once, _a, _s = apply_reviews(entries, ledger)
    twice, applied2, stale2 = apply_reviews(once, ledger)
    assert render_bank(once) == render_bank(twice)
    assert applied2 == [] and stale2 == []  # nothing left to change


def test_applicator_never_touches_non_review_fields():
    entries = [_msk_group(_drill(dose={"sets": 3}, pain_ceiling=4, allowed_severities=["low"]))]
    ledger = _reviewed_ledger(entries, load="low")
    applied_entries, _a, _s = apply_reviews(entries, ledger)
    drill = applied_entries[0]["drills"][0]
    assert drill["dose"] == {"sets": 3}
    assert drill["pain_ceiling"] == 4
    assert drill["allowed_severities"] == ["low"]


# --------------------------------------------------------------------------- #
# Movement archetypes, proposals, flags
# --------------------------------------------------------------------------- #


def test_archetypes_are_from_the_canonical_vocabulary():
    entries = load_bank(BANK_PATH)
    for record in build_ledger(entries):
        assert record["movement_archetype"] in MOVEMENT_ARCHETYPES


@pytest.mark.parametrize(
    "name,notes,expected",
    [
        ("Isometric Ankle Hold", "static hold", "isometric"),
        ("Single-Leg Depth Jump", "jump and stick landing", "hop_jump_landing"),
        ("Calf Stretch", "gentle range of motion", "mobility_rom"),
        ("Foam Roll Calf", "soft tissue release", "manual_recovery"),
        ("Nothing Recognisable", "", "unknown"),
    ],
)
def test_classify_movement_archetype(name, notes, expected):
    assert classify_movement_archetype(name, notes) == expected


def test_12_camp_phase_never_determines_rehab_stage():
    for phase_notes in ("GPP: early control", "SPP → TAPER: progress", "TAPER: sharpen"):
        proposed = propose_metadata(
            archetype="isometric", name="Iso Hold", location="ankle",
            drill=_drill(notes=phase_notes),
        )
        assert proposed["rehab_stage"] is None  # stage is never inferred from camp phase


def test_13_variable_load_progression_is_flagged():
    flags = detect_variable_demand_flags("GPP: bodyweight → SPP: add load progressively")
    assert FLAG_LOAD_PROGRESSION in flags
    assert FLAG_VARIABLE_DEMAND in flags
    assert FLAG_POSSIBLE_DRILL_SPLIT in flags


def test_14_hop_progression_is_flagged():
    flags = detect_variable_demand_flags("GPP: balance → SPP: add hop and jump landings")
    assert FLAG_IMPACT_PROGRESSION in flags
    assert FLAG_POSSIBLE_DRILL_SPLIT in flags


def test_contact_progression_is_flagged():
    flags = detect_variable_demand_flags("progress to controlled contact with partner")
    assert FLAG_CONTACT_PROGRESSION in flags


def test_single_note_without_progression_is_not_flagged():
    assert detect_variable_demand_flags("gentle isometric hold, no progression") == []


# --------------------------------------------------------------------------- #
# Validator
# --------------------------------------------------------------------------- #


def test_committed_ledger_validates_against_the_real_bank():
    assert validate(load_bank(BANK_PATH), json.loads(LEDGER_PATH.read_text(encoding="utf-8"))) == []


def test_validator_rejects_missing_msk_record():
    entries = [_msk_group(_drill())]
    assert any("no ledger record" in e for e in validate(entries, []))


def test_validator_rejects_surface_review_record():
    surface_drill = {"id": "cheek_laceration_clean", "name": "Clean", "notes": "x"}
    entries = [_surface_group(surface_drill)]
    bad = [{
        "drill_id": "cheek_laceration_clean", "source_hash": "0" * 64, "location": "cheek",
        "injury_type": "laceration", "name": "Clean", "notes": "x", "movement_archetype": "unknown",
        "proposed": {f: None for f in REVIEW_FIELDS}, "flags": [], "review_state": "needs_review", "review_version": 1,
    }]
    assert any("must not receive MSK review metadata" for e in validate(entries, bad))


def test_validator_rejects_bad_enum_and_archetype_and_duplicates():
    entries = [_msk_group(_drill())]
    ledger = build_ledger(entries)
    ledger[0]["movement_archetype"] = "not_a_real_archetype"
    ledger[0]["proposed"]["load"] = "enormous"
    ledger.append(copy.deepcopy(ledger[0]))  # duplicate drill_id
    errors = validate(entries, ledger)
    assert any("invalid movement_archetype" in e for e in errors)
    assert any("proposed.load" in e for e in errors)
    assert any("duplicate drill_id" in e for e in errors)


def test_proposed_enum_values_conform_to_schema():
    entries = load_bank(BANK_PATH)
    allowed = {
        "rehab_stage": REHAB_STAGES, "function": REHAB_FUNCTIONS, "impact": IMPACT_VALUES,
        "load": LOAD_VALUES, "velocity": VELOCITY_VALUES,
        "laterality_applicability": LATERALITY_APPLICABILITY_VALUES,
        "contraction_type": CONTRACTION_TYPE_VALUES, "sport_specificity": SPORT_SPECIFICITY_VALUES,
        "contact_level": CONTACT_LEVEL_VALUES,
    }
    for record in build_ledger(entries):
        for field, values in allowed.items():
            proposed = record["proposed"][field]
            assert proposed is None or proposed in values


# --------------------------------------------------------------------------- #
# Coverage reporter
# --------------------------------------------------------------------------- #


def test_coverage_report_is_honest_about_the_unmigrated_bank():
    report = build_report(load_bank(BANK_PATH), json.loads(LEDGER_PATH.read_text(encoding="utf-8")))
    assert report["totals"]["msk_drills"] == len(build_ledger(load_bank(BANK_PATH)))
    assert report["fully_known_mechanical_demand"] == 0  # nothing migrated yet
    assert report["field_levels"]["load"].get("known", 0) == 0
    assert report["stale_reviews"] == 0
    assert report["review_states"] == {REVIEW_STATE_NEEDS_REVIEW: report["totals"]["msk_drills"]}


# --------------------------------------------------------------------------- #
# Safety boundaries
# --------------------------------------------------------------------------- #


def test_21_pipeline_has_no_write_path_to_historical_exposures():
    """No tool imports or touches stored rehab exposure evidence or any store.

    The pipeline reads and writes only ``rehab_bank.json`` and the review ledger.
    (The word "exposure" appears in docstrings meaning a drill's *mechanical*
    exposure, which is unrelated to the stored ``rehab_exposures`` evidence rows.)
    """
    forbidden = (
        "rehab_exposures",
        "create_rehab_exposure",
        "record_rehab_exposure",
        "list_rehab_exposure",
        "RehabExposureEvent",
        "api.contracts.rehab_exposure",
        "api.contracts.rehab_completion",
        "AppStore",
        "supabase",
    )
    for filename in TOOL_FILES:
        text = (REPO_ROOT / "tools" / filename).read_text(encoding="utf-8")
        for symbol in forbidden:
            assert symbol not in text, f"{filename} unexpectedly references {symbol!r}"


def test_22_23_24_load_dynamic_return_remain_production_inaccessible():
    assert MAX_RESOLVABLE_STAGE == STAGE_RESTORE
    assert MAX_RESOLVABLE_STAGE not in {STAGE_LOAD, STAGE_DYNAMIC, STAGE_RETURN}
    assert dict(LOAD_CRITERIA_REGISTRY) == {}
    # The ledger never proposes a stage above the production ceiling.
    for record in build_ledger(load_bank(BANK_PATH)):
        assert record["proposed"]["rehab_stage"] in (None, "calm", "restore")


def test_applying_the_committed_ledger_does_not_change_the_committed_bank():
    """All production records are needs_review, so the bank stays byte-identical."""
    entries = load_bank(BANK_PATH)
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    applied_entries, applied, stale = apply_reviews(entries, ledger)
    assert applied == [] and stale == []
    assert render_bank(applied_entries) == BANK_PATH.read_text(encoding="utf-8")
