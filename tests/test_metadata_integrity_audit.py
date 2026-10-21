"""Preservation and evidence contracts for the investigation-only audit."""
from __future__ import annotations

import asyncio
from collections import Counter
from copy import deepcopy
import hashlib
import json

import pytest

from fightcamp.training_catalogue import SOURCE_CLASSES, build_catalogue
from tools import audit_metadata_integrity as audit


@pytest.fixture(scope="module")
def reports():
    paths = [audit.ROOT / path for path in audit.tracked(audit.ROOT)
             if path.endswith((".py", ".json", ".ts", ".tsx", ".sql"))]
    before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    result = audit.historical_reports()
    assert before == {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    return result


def independent_count(source, payload):
    if source == "rehab_bank.json":
        return sum(len(group["drills"]) for group in payload)
    if source == "coordination_bank.json":
        return sum(len(value) for value in payload.values() if isinstance(value, list))
    return len(payload)


def pointer(value, path):
    for part in path.lstrip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def test_all_live_entries_and_zero_row_shim_are_accounted_for(reports):
    rows = reports["inventory.json"]["entries"]
    counts = {source: independent_count(source, json.loads((audit.ROOT / "data" / source).read_bytes()))
              for source in SOURCE_CLASSES}
    assert sum(counts.values()) == len(rows) == 2855
    assert counts["coordination_bank.json"] == 0
    assert Counter(e["source"] for e in rows) == {s: n for s, n in counts.items() if n}
    assert not any("archive" in e["source"] for e in rows)
    assert Counter(e["content_class"] for e in rows) == {
        "strength_power": 339, "conditioning": 588, "technical_coordination": 83,
        "rehabilitation": 1499, "care_instruction": 104,
        "tactical_educational": 183, "visualisation": 59,
    }


def test_inventory_preserves_every_raw_source_row(reports):
    payloads = {source: json.loads(audit.original_equipment_source("data/" + source)) for source in SOURCE_CLASSES}
    for entry in reports["inventory.json"]["entries"]:
        source = pointer(payloads[entry["source"]], entry["source_pointer"])
        assert entry["raw"] == source
        assert entry["row_sha256"] == audit.content_hash(source)
        if entry["source"] == "rehab_bank.json":
            group = payloads[entry["source"]][int(entry["source_pointer"].split("/")[1])]
            assert entry["raw_group"] == {k: v for k, v in group.items() if k != "drills"}


def test_all_field_occurrences_have_exact_raw_value_type_and_identity(reports):
    entries = {e["catalogue_id"]: e for e in reports["inventory.json"]["entries"]}
    for field, metadata in reports["inventory.json"]["fields"].items():
        for value in metadata["values"]:
            assert value["frequency"] == len(value["occurrences"])
            assert value["affected_identity_count"] == len({o["identity"] for o in value["occurrences"]})
            for occurrence in value["occurrences"]:
                entry = entries[occurrence["identity"]]
                raw = entry["raw_group"] if field.startswith("group.") else entry["raw"]
                original = pointer(raw, occurrence["pointer"])
                assert original == value["raw"]
                assert type(original) is type(value["raw"])


def test_null_empty_and_composite_values_are_not_coerced_or_split():
    raw = {"equipment": ["bands,heavy bag", "treadmill/rower"], "dose": {"sets": None, "reps": 0},
           "flags": [True, False], "rules": [], "notes": "  Keep original spacing.  "}
    extracted = list(audit.leaves(raw))
    assert ("equipment", "/equipment/0", "bands,heavy bag") in extracted
    assert ("equipment", "/equipment/1", "treadmill/rower") in extracted
    assert ("dose.sets", "/dose/sets", None) in extracted
    assert ("rules", "/rules", []) in extracted
    assert ("notes", "/notes", "  Keep original spacing.  ") in extracted
    assert not any(value == "bands" or value == "heavy bag" for _, _, value in extracted)
    fields = {"equipment": {"values": [{"raw": "bands,heavy bag"}, {"raw": "treadmill/rower"}]}}
    candidates = audit.candidates(fields)
    assert len(candidates) == 2
    assert all(c["candidate_reason"] == "compound_or_separator" and c["raw_preserved"] for c in candidates)


def test_duplicate_screen_does_not_merge_different_concepts(reports):
    decisions = reports["remediation.json"]["issues"]
    def strings(issue):
        return {v for v in issue["existing_values"] if isinstance(v, str)}
    preserved = next(i for i in decisions if strings(i) == {"reaction", "reactive", "mech_reactive"})
    assert preserved["recommended_action"] == "PRESERVE"
    timing = next(i for i in decisions if strings(i) == {"hand_foot_timing", "foot_hand_timing"})
    assert timing["recommended_action"] == "REVIEW" and timing["manual_review_required"]
    neck = next(i for i in decisions if strings(i) == {"neck", "neck_vestibular"})
    assert neck["recommended_action"] == "PARENT/SUBTYPE"
    assert all(i["manual_review_required"] for i in decisions if i["confidence"] == "screening_only")


def test_fixed_duration_range_is_valid_while_repeated_risk_token_is_flagged():
    entry = {"catalogue_id": "test:fixed", "source": "test.json", "name": "Rehearsal", "source_pointer": "/0",
             "row_sha256": "evidence", "content_class": "visualisation",
             "raw": {"name": "Rehearsal", "duration_min": [3, 3], "mechanical_risk_tags": ["mech_reactive", "mech_reactive"]}}
    rules = {r["rule"] for r in audit.accuracy([entry])}
    assert "repeated_array_value:duration_min" not in rules
    assert "repeated_array_value:mechanical_risk_tags" in rules


def test_reports_are_deterministic_and_retained_reports_match(reports):
    again = audit.historical_reports()
    assert {k: audit.dumps(v) for k, v in reports.items()} == {k: audit.dumps(v) for k, v in again.items()}
    for name, report in reports.items():
        assert (audit.ROOT / audit.OUT / name).read_text(encoding="utf-8") == audit.report_json(report)
    assert (audit.ROOT / audit.OUT / "README.md").read_text(encoding="utf-8") == audit.markdown(reports)


def test_frozen_bank_production_and_identity_baselines_are_unchanged(reports):
    baseline = json.loads(audit.BASELINE.read_bytes())
    with audit.historical_sources() as replay:
        current = audit.snapshot(replay)
    for key in ("banks", "identity_inputs", "identities"):
        assert current[key] == baseline[key]
    # The historical replay above still checks every original production hash;
    # PR 2 separately verifies its narrow allowed diff and frozen plan outputs.
    entries = build_catalogue()
    assert {e["catalogue_id"]: e["exercise_key"] for e in entries} == {
        identity: value["exercise_key"] for identity, value in baseline["identities"].items()
    }
    assert len({e["catalogue_id"] for e in entries}) == 2855
    assert reports["summary.json"]["banks"] == baseline["banks"]


def test_real_compounds_have_not_been_silently_split(reports):
    fields = reports["inventory.json"]["fields"]
    assert any(v["raw"] == "bands,heavy_bag" for v in fields["equipment"]["values"])
    assert any(v["raw"] == "trap_bar,pins" for v in fields["equipment"]["values"])
    raw_ids = {e["catalogue_id"] for e in reports["inventory.json"]["entries"] if "trap_bar,pins" in audit.tokens(e["raw"], "equipment")}
    reported_ids = [o["identity"] for v in fields["equipment"]["values"] if v["raw"] == "trap_bar,pins" for o in v["occurrences"]]
    assert set(reported_ids) == raw_ids


def test_every_field_and_configuration_has_dependency_status(reports):
    inventory = reports["inventory.json"]
    consumers = reports["consumers.json"]
    assert set(inventory["fields"]) <= set(consumers["fields"])
    assert {"config." + f for f in inventory["configuration_fields"]} <= set(consumers["fields"])
    assert {"definition." + f for f in consumers["definition_fields"]} <= set(consumers["fields"])
    assert all(c["status"] for c in consumers["fields"].values())
    frontend = next(w for w in consumers["reviewed_workflows"] if w["function"] == "canonicalizeEquipmentAccessValues")
    assert frontend["file"] == "web/lib/intake-options.ts" and frontend["line"] == 219
    assert "exact alias lookup" in frontend["usage"]
    assert consumers["source_references"]["rehab_archive/exact_duplicates.json"]
    assert consumers["source_references"]["coordination_bank.json"]
    assert not consumers["source_references"]["footwork_conditioning_bank.json"]
    assert reports["summary.json"]["confirmed_unused_values"] == 0
    source_issues = [i for i in reports["remediation.json"]["issues"] if i["field"] == "source_file"]
    assert len(source_issues) == 2
    assert all(i["recommended_action"] == "PRESERVE" and i["manual_review_required"] for i in source_issues)
    assert all(i["affected_entries"] == 0 and i["supporting_evidence"] for i in source_issues)


def test_configuration_case_collision_and_unestablished_restrictions_are_reported(reports):
    collisions = reports["redundancy.json"]["normaliser_alias_collisions"]
    goal = next(c for c in collisions if c["symbol"] == "GOAL_NORMALIZER")
    assert goal["raw_mapping"]["Speed"] == "reactive"
    assert goal["raw_mapping"]["speed"] == "speed"
    issue = next(i for i in reports["remediation.json"]["issues"] if i["field"] == "block_if_fight_within_days")
    assert issue["recommended_action"] == "REVIEW" and issue["manual_review_required"]
    assert issue["supporting_evidence"][0]["unused_claim"] is False
    clinical = next(i for i in reports["remediation.json"]["issues"] if i["field"] == "target_regions" and i["recommended_action"] == "RENAME")
    assert clinical["manual_review_required"]


def test_goal_coverage_is_observed_without_assignment(reports):
    goals = reports["goals.json"]
    assert goals["training_entries"] == 1010
    assert goals["usable_goal_facets"] == 222
    assert goals["explicit_goal_entries"] == 55
    assert all(row["explicit_goals"] == 0 for row in goals["by_source"] if row["source"] != "exercise_bank.json")
    assert sum(bool(e["explicit"]) for e in goals["entries"]) == 55


def test_source_drift_is_rejected_instead_of_refreshing_baseline(monkeypatch):
    changed = json.loads(audit.BASELINE.read_bytes())
    changed["banks"]["exercise_bank.json"]["sha256"] = "f" * 64
    monkeypatch.setattr(audit, "snapshot", lambda root: changed)
    with pytest.raises(ValueError, match="Baseline banks, identities, or production sources changed"):
        audit.build_reports()


def test_retained_historical_receipts_match_frozen_hashes():
    baseline = json.loads(audit.BASELINE.read_bytes())
    expected = {**baseline["production_files"], **baseline["configuration_files"]}
    receipts = json.loads((audit.ROOT / "tools/metadata_integrity_original_sources.json").read_bytes())
    for relative, source in receipts.items():
        assert audit.source_hash(source.encode("utf-8")) == expected[relative], relative


def test_completion_provenance_replay_preserves_exact_frozen_contract_and_live_field():
    from api.contracts.external_training import TrainingHistorySession

    relative = "api/contracts/external_training.py"
    original_bytes = (audit.ROOT / relative).read_bytes()
    expected = json.loads(audit.BASELINE.read_bytes())["production_files"][relative]
    assert audit.source_hash(audit.original_equipment_source(relative)) == expected
    assert "completion_origin" in TrainingHistorySession.model_fields
    assert (audit.ROOT / relative).read_bytes() == original_bytes


def test_provenance_compatibility_does_not_allow_other_external_contract_changes(monkeypatch):
    from pathlib import Path

    target = audit.ROOT / "api/contracts/external_training.py"
    original_read = Path.read_bytes

    def altered(path):
        data = original_read(path)
        if path == target:
            return data.replace(b'Activity = Literal["sparring"', b'Activity = Literal["wrestling"', 1)
        return data

    monkeypatch.setattr(Path, "read_bytes", altered)
    with pytest.raises(ValueError, match="Historical source drift: api/contracts/external_training.py"):
        with audit.historical_sources():
            pytest.fail("Only the exact additive provenance field is compatible")


def test_rehab_permission_replay_preserves_original_and_rejects_other_clearance_changes(monkeypatch):
    from pathlib import Path

    relative = "api/contracts/clinician_clearance.py"
    target = audit.ROOT / relative
    original_read = Path.read_bytes
    expected = json.loads(audit.BASELINE.read_bytes())["production_files"][relative]
    assert audit.source_hash(audit.original_equipment_source(relative)) == expected

    def altered(path):
        data = original_read(path)
        if path == target:
            return data.replace(b'bool(injury.get("episode_id"))', b'True', 1)
        return data

    monkeypatch.setattr(Path, "read_bytes", altered)
    with pytest.raises(ValueError, match="Historical source drift: api/contracts/clinician_clearance.py"):
        with audit.historical_sources():
            pytest.fail("Only the exact shared permission reader revision is compatible")


def test_tampered_historical_receipt_is_rejected(monkeypatch):
    receipt_bytes = (audit.ROOT / "tools/metadata_integrity_original_sources.json").read_bytes()
    receipts = json.loads(receipt_bytes)
    receipts["api/app.py"] += "\n# tampered historical receipt\n"
    original_loads = json.loads
    monkeypatch.setattr(audit.json, "loads", lambda value, *args, **kwargs:
                        receipts if value == receipt_bytes else original_loads(value, *args, **kwargs))
    with pytest.raises(ValueError, match="Historical source drift: api/app.py"):
        with audit.historical_sources():
            pytest.fail("Tampered receipt must be rejected before replay")


def test_custom_plan_boundary_does_not_allow_unrelated_production_changes(monkeypatch):
    from tools import audit_canonical_metadata as canonical

    baseline = json.loads(canonical.BASELINE.read_bytes())
    current = canonical.snapshot()
    current["production_files"]["fightcamp/conditioning.py"] = "f" * 64
    original_snapshot = canonical.snapshot
    monkeypatch.setattr(canonical, "snapshot", lambda root=canonical.ROOT:
                        current if root == canonical.ROOT else original_snapshot(root))
    with pytest.raises(ValueError, match="Unapproved production diff"):
        canonical.preservation(baseline)


def test_running_full_audit_preserves_deterministic_training_outputs(reports):
    from fightcamp.main import generate_plan
    from support import _build_request

    payload = _build_request().to_payload()
    payload["random_seed"] = 7
    before = asyncio.run(generate_plan(deepcopy(payload)))
    audit.historical_reports()
    after = asyncio.run(generate_plan(deepcopy(payload)))
    assert before["plan_text"] and before["plan_text"] == after["plan_text"]
    assert before["stage2_payload"] == after["stage2_payload"]
