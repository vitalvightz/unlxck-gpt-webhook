"""Preservation and evidence contracts for the investigation-only audit."""
from __future__ import annotations

import json

import pytest

from tools import audit_metadata_integrity as audit


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


def test_fixed_duration_range_is_valid_while_repeated_risk_token_is_flagged():
    entry = {"catalogue_id": "test:fixed", "source": "test.json", "name": "Rehearsal", "source_pointer": "/0",
             "row_sha256": "evidence", "content_class": "visualisation",
             "raw": {"name": "Rehearsal", "duration_min": [3, 3], "mechanical_risk_tags": ["mech_reactive", "mech_reactive"]}}
    rules = {r["rule"] for r in audit.accuracy([entry])}
    assert "repeated_array_value:duration_min" not in rules
    assert "repeated_array_value:mechanical_risk_tags" in rules


def test_source_drift_is_rejected_instead_of_refreshing_baseline(monkeypatch):
    changed = json.loads(audit.BASELINE.read_bytes())
    changed["banks"]["exercise_bank.json"]["sha256"] = "f" * 64
    monkeypatch.setattr(audit, "snapshot", lambda root: changed)
    with pytest.raises(ValueError, match="Baseline banks, identities, or production sources changed"):
        audit.build_reports()


