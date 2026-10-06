"""Whole-bank audit completeness, classification boundaries and no runtime drift."""
from copy import deepcopy
import hashlib
import json

import pytest

from fightcamp.rehab_clinical import content_hash, load_clinical_policies, policy_review_hash
from tools.audit_rehab_bank_rationalisation import (
    CLASSIFICATIONS, ROOT, affirmative_progression, build_audit, input_digest, json_text, main,
)
from tools.rehab_metadata_review_lib import source_hash
from tools.consolidate_rehab_exact_duplicates import reconstruct_original, digest, validate_archive


def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def inputs():
    return tuple(read("data/" + name + ".json") for name in ("rehab_bank", "rehab_metadata_review", "rehab_pathways"))


@pytest.fixture(scope="module")
def audit(inputs):
    return build_audit(*inputs)


def test_every_identity_classified_once_and_totals_reconcile(inputs, audit):
    report, clusters = audit
    bank_ids = [d["id"] for g in inputs[0] for d in g["drills"]]
    records = report["drills"]
    assert report["integrity_errors"] == []
    assert len(records) == len(bank_ids) == len({r["drill_id"] for r in records})
    assert sorted(bank_ids) == [r["drill_id"] for r in records]
    assert all(r["classification"] in CLASSIFICATIONS and r["rationale"] and r["recommended_next_action"] for r in records)
    assert sum(report["summary"]["primary_classification_counts"].values()) == len(bank_ids)
    assert sum(report["summary"]["drills_by_pathway_family"].values()) == len(bank_ids)
    for cluster in clusters["clusters"]:
        assert len(cluster["drill_ids"]) > 1
        assert set(cluster["drill_ids"]) <= set(bank_ids)
        assert cluster["classification"] in {"exact_duplicate", "near_duplicate", "intentionally_distinct", "uncertain"}


def test_every_live_identity_has_fresh_review_and_exact_active_reference(inputs, audit):
    bank, ledger, pathways = inputs
    report, _ = audit
    bank_index = {d["id"]: (g, d) for g in bank for d in g["drills"]}
    reviews = {r["drill_id"]: r for r in ledger}
    policies = {p["policy_id"]: p for p in pathways["profiles"]}
    for row in report["drills"]:
        group, drill = bank_index[row["drill_id"]]
        assert row["current_content_hash"] == content_hash(drill)
        assert row["current_source_hash"] == source_hash(drill_id=drill["id"], location=group["location"], injury_type=group["type"], name=drill["name"], notes=drill["notes"])
        if row["classification"] != "LIVE":
            assert row["why_dormant"]
            continue
        record = reviews[row["drill_id"]]
        assert row["review_state"] == record["review_state"] == "reviewed"
        assert record["source_hash"] == row["current_source_hash"]
        assert row["referenced_by_active_profile"] and row["live_progression_path_reachable"]
        assert row["advanced_candidate_assessment"] is None
        for ref in row["active_profile_references"]:
            policy = policies[ref["policy_id"]]
            assert policy["status"] == "active" and policy["activation"] == "live"
            rx = next(r for r in policy["prescriptions"] if r["drill_id"] == row["drill_id"])
            assert rx["bank_hash"] == row["current_content_hash"]
            assert ref["stage"] == rx["stage"] in policy["live_stages"]


def test_every_active_prescription_resolves_and_stage_counts_are_unique(inputs, audit):
    rows = {r["drill_id"]: r for r in audit[0]["drills"]}
    actual = {stage: set() for stage in ("calm", "restore", "load", "dynamic", "return")}
    for policy in inputs[2]["profiles"]:
        for rx in policy["prescriptions"]:
            row = rows[rx["drill_id"]]
            assert row["classification"] == "LIVE" and policy["policy_id"] in row["profile_ids"]
            actual[rx["stage"]].add(rx["drill_id"])
    assert audit[0]["summary"]["live_unique_identities_by_stage"] == {s: len(ids) for s, ids in actual.items()}
    assert all(not actual[s] for s in ("load", "dynamic", "return"))


def test_production_bank_source_history_and_all_64_profiles_unchanged():
    baseline = read("tests/fixtures/rehab_bank_rationalisation_baseline.json")
    bank = read("data/rehab_bank.json")
    ledger = read("data/rehab_metadata_review.json")
    archive = read("data/rehab_archive/exact_duplicates.json")
    original_bank, original_ledger = reconstruct_original(bank, ledger, archive)
    # Retained + archived content must recover the immutable original baseline.
    assert digest(original_bank) == baseline["input_sha256"]["rehab_bank.json"]
    assert digest(original_ledger) == baseline["input_sha256"]["rehab_metadata_review.json"]
    from tools.rehab_metadata_review_lib import pathway_inventory_snapshot
    assert digest(pathway_inventory_snapshot(read("data/rehab_pathways.json"))) == baseline["input_sha256"]["rehab_pathways.json"]
    assert sorted(d["id"] for g in original_bank for d in g["drills"]) == baseline["bank_drill_ids"]
    raw = read("data/rehab_pathways.json")
    assert validate_archive(bank, ledger, raw, archive) == []
    assert len(raw["profiles"]) == len(baseline["profile_hashes"]) == 64
    assert {p["policy_id"]: p["content_hash"] for p in raw["profiles"]} == baseline["profile_hashes"]
    assert {p["policy_id"]: hashlib.sha256(json.dumps(p, sort_keys=True, separators=(",", ":")).encode()).hexdigest() for p in raw["profiles"]} == baseline["profile_raw_sha256"]
    for policy in load_clinical_policies():
        assert policy_review_hash(policy) == baseline["profile_hashes"][policy.policy_id]
        assert set(policy.live_stages) <= {"calm", "restore"}
        assert not any(t.promotable for t in policy.transitions)


def test_report_generation_byte_determinism_and_no_mutation(inputs, audit, tmp_path):
    original = deepcopy(inputs)
    assert build_audit(*inputs) == audit
    assert inputs == original
    assert main(["--output-dir", str(tmp_path)]) == 0
    first = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert main(["--output-dir", str(tmp_path)]) == 0
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == first
    assert main(["--output-dir", str(tmp_path), "--check"]) == 0
    assert main(["--check"]) == 0
    assert json_text(audit[0]) == json_text(build_audit(*inputs)[0])
    assert inputs == original


def test_git_input_provenance_is_portable_across_windows_and_linux(tmp_path):
    lf = tmp_path / "lf.json"
    crlf = tmp_path / "crlf.json"
    lf.write_bytes(b'{\n  "notes": "retain this source history"\n}\n')
    crlf.write_bytes(lf.read_bytes().replace(b"\n", b"\r\n"))
    assert input_digest(lf) == input_digest(crlf)
    crlf.write_bytes(b'{\r\n  "notes": "changed source"\r\n}\r\n')
    assert input_digest(lf) != input_digest(crlf)


def test_dormant_advanced_candidates_do_not_become_prescriptions(audit):
    report, _ = audit
    candidates = [r for r in report["drills"] if r["classification"] == "ADVANCED_CANDIDATE"]
    assert candidates
    for row in candidates:
        assert row["review_state"] == "reviewed"
        assert not row["referenced_by_active_profile"]
        assert not row["live_progression_path_reachable"]
        assert row["advanced_candidate_assessment"]["readiness_class"] == "GOOD_FIXED_MECHANICS_GATE_NOT_READY"
        assert row["advanced_candidate_assessment"]["safety_blocks"]
    assert report["summary"]["promotable_advanced_transitions"] == 0
    assert report["summary"]["profiles_with_load_or_above"] == []


def test_unassigned_region_inventory_is_visible_without_borrowing_a_diagnosis(audit):
    report, _ = audit
    row = next(r for r in report["drills"] if r["drill_id"] == "hamstring_unspecified_nordic_hamstring_curl_eccentrics")
    assert row["injury_type"] == "unspecified"
    assert row["plausible_future_stages"] == ["load"]
    assert not row["referenced_by_active_profile"]
    assert row["advanced_candidate_assessment"]["regional_indication_requires_clinical_review"]
    profile = next(p for p in report["profiles"] if p["policy_id"] == "hamstring_strain")
    assert row["drill_id"] in profile["unassigned_regional_inventory_candidates"]
    assert row["drill_id"] not in profile["advanced_candidates"]
    assert row["classification"] != "LIVE"


@pytest.mark.parametrize("identity,expected", [
    ("hand_hyperextension_wall_crawls_backhand_contact", ["load"]),
    ("shoulder_unspecified_prone_trap_3_raises_grappling_initiation", ["load"]),
    ("ankle_impingement_banded_ankle_distraction", []),
])
def test_contact_with_a_wall_sport_intent_and_passive_band_are_not_sport_return(audit, identity, expected):
    row = next(r for r in audit[0]["drills"] if r["drill_id"] == identity)
    assert row["plausible_future_stages"] == expected


@pytest.mark.parametrize("identity", ["quads_strain_foam_roller_quad_sweep", "hamstrings_strain_massage_gun_biceps_femoris_sweep"])
def test_passive_recovery_load_tag_is_not_a_loading_candidate(audit, identity):
    row = next(r for r in audit[0]["drills"] if r["drill_id"] == identity)
    assert row["rehab_stage"] == "load" and row["review_state"] == "reviewed"
    assert row["plausible_future_stages"] == []
    assert row["classification"] == "KEEP_DORMANT"


def test_exact_alias_duplicates_cross_type_and_near_duplicates_keep_boundaries(audit):
    rows = {r["drill_id"]: r for r in audit[0]["drills"]}
    clusters = audit[1]["clusters"]
    assert rows["bicep_strain_band_resisted_eccentric_curl"]["canonical_region"] == "biceps"
    assert rows["hamstrings_strain_isometric_hamstring_bridge"]["canonical_region"] == "hamstring"
    archive = read("data/rehab_archive/exact_duplicates.json")
    cluster = next(r['original_cluster'] for r in archive['records'] if r['retired_id'] == 'calf_strain_double_leg_calf_raises_2')
    assert cluster["classification"] == "exact_duplicate"
    assert cluster["canonical_identity_candidates_to_keep"] == ["calf_strain_double_leg_calf_raises"]
    assert rows["calf_strain_double_leg_calf_raises"]["classification"] == "LIVE"
    assert "calf_strain_double_leg_calf_raises_2" not in rows
    assert not any(c['classification'] == 'exact_duplicate' for c in clusters)
    for c in clusters:
        if len(c["injury_types"]) > 1 or len(c["canonical_regions"]) > 1:
            assert c["ids_for_later_deprecation_review"] == []
        if c["classification"] != "exact_duplicate":
            assert c["ids_for_later_deprecation_review"] == []


def test_negated_progression_and_bounded_amount_are_not_hidden_load(audit):
    assert affirmative_progression("Do not add weight, increase speed or add resistance.") == ([], ["add resistance", "add weight", "increase speed"])
    assert affirmative_progression("Do not add weight. Later progress to jumping.")[0] == ["progress to"]
    rows = {r["drill_id"]: r for r in audit[0]["drills"]}
    assert rows["achilles_tendonitis_reviewed_restore"]["prohibited_progression_matches"] == ["add weight"]
    assert rows["ankle_sprain_supported_balance"]["hidden_progression_kind"] == "bounded_self_paced_amount"
    assert not any(r["hidden_progression_matches"] for r in rows.values() if r["classification"] == "LIVE")


def test_surface_inventory_is_not_misrepresented_as_unreachable(audit):
    rows = {r["drill_id"]: r for r in audit[0]["drills"]}
    row = rows["heel_blister_sterile_drainage_if_tense"]
    assert row["classification"] == "DEPRECATE"
    assert row["review_state"] == "outside_msk_review_ledger"
    assert row["source_evidence_ids"] == ["blister"]
    assert "legacy wound-care helper" in row["why_dormant"][0]
    assert rows["eye_cut_no_reopen_protection"]["classification"] == "KEEP_DORMANT"
    assert rows["eye_pain_saccadic_eye_jumps_horizontal_vertical"]["classification"] == "DEPRECATE"


@pytest.mark.parametrize("failure", ["missing_identity", "stale_content", "needs_review_reference", "duplicate_identity", "duplicate_ledger", "missing_ledger"])
def test_genuine_integrity_failure_detected_without_modifying_inputs(inputs, failure):
    bank, ledger, pathways = deepcopy(inputs)
    live_id = "achilles_tendonitis_reviewed_restore"
    group = next(g for g in bank if any(d["id"] == live_id for d in g["drills"]))
    drill = next(d for d in group["drills"] if d["id"] == live_id)
    review = next(r for r in ledger if r["drill_id"] == live_id)
    if failure == "missing_identity":
        group["drills"].remove(drill)
    elif failure == "stale_content":
        drill["notes"] += " Add a jump."
    elif failure == "needs_review_reference":
        review["review_state"] = "needs_review"
    elif failure == "duplicate_identity":
        group["drills"].append(deepcopy(drill))
    elif failure == "duplicate_ledger":
        ledger.append(deepcopy(review))
    elif failure == "missing_ledger":
        ledger.remove(review)
    report, _ = build_audit(bank, ledger, pathways)
    assert report["integrity_errors"]
    assert not any(r["classification"] == "LIVE" and r["review_state"] != "reviewed" for r in report["drills"])


def test_debt_does_not_fail_cli_but_stale_reports_do(tmp_path):
    assert main(["--output-dir", str(tmp_path)]) == 0
    (tmp_path / "rehab-bank-rationalisation.md").write_text("stale", encoding="utf-8")
    assert main(["--output-dir", str(tmp_path), "--check"]) == 1


def test_metadata_generator_and_seed_idempotence_still_hold(tmp_path, monkeypatch):
    from tools import seed_nonspecific_msk_family
    from tools.generate_rehab_metadata_review import build_ledger
    data = tmp_path / "data"
    data.mkdir()
    names = ("rehab_bank.json", "rehab_metadata_review.json", "rehab_pathways.json")
    original = {name: (ROOT / "data" / name).read_bytes() for name in names}
    for name, value in original.items():
        (data / name).write_bytes(value)
    monkeypatch.setattr(seed_nonspecific_msk_family, "ROOT", tmp_path)
    seed_nonspecific_msk_family.main()
    seed_nonspecific_msk_family.main()
    assert {name: (data / name).read_bytes() for name in names} == original
    bank, ledger = json.loads(original[names[0]]), json.loads(original[names[1]])
    assert build_ledger(bank, prior=ledger) == ledger


def test_existing_bank_clinical_metadata_and_vocabulary_validators_pass(inputs):
    from tools.audit_injury_vocabulary import audit as vocabulary_audit
    from tools.validate_rehab_bank import ERROR, REPO_ROOT, load_duplicate_debt, validate_rehab_bank
    from tools.validate_rehab_metadata_review import validate
    from fightcamp.rehab_clinical import validate_clinical_bank
    bank, ledger, _ = inputs
    # Existing duplicate debt is classification input, not new schema failure.
    issues = validate_rehab_bank(bank, duplicate_debt=load_duplicate_debt(REPO_ROOT / "data" / "rehab_bank_duplicate_debt.json"))
    assert not [i for i in issues if i.severity == ERROR]
    assert validate(bank, ledger) == []
    assert validate_clinical_bank(load_clinical_policies(), bank) == []
    drift, _ = vocabulary_audit()
    assert not any(drift.values())
