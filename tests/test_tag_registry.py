from __future__ import annotations

import json
from pathlib import Path

import pytest

from fightcamp.tag_vocabulary import parse_tag_vocabulary_payload, read_tag_vocabulary_items
from fightcamp.tagging import normalize_tag
from tools.audit_tag_registry import (
    DATA_DIR,
    collect_bank_tags,
    collect_runtime_control_tags,
    collect_scoring_tags,
)
from tools.check_tag_registry import authority_failures, load_review_decisions
from tools.injury_tag_authority import collect_generated_injury_tags
from tools.migrate_tag_registry_data import planned_changes
from tools.validate_banks import discover_banks


def test_tag_vocabulary_parser_accepts_all_supported_schemas(tmp_path: Path):
    assert parse_tag_vocabulary_payload(["speed", " power "]) == ["speed", "power"]
    assert parse_tag_vocabulary_payload({"items": ["speed"]}) == ["speed"]
    assert parse_tag_vocabulary_payload({"data": ["speed"]}) == ["speed"]

    path = tmp_path / "tag_vocabulary.json"
    path.write_text(json.dumps({"items": ["speed", "power"]}), encoding="utf-8")
    assert read_tag_vocabulary_items(path) == ["speed", "power"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        {"items": []},
        {"data": [""]},
        ["speed", 123],
    ],
)
def test_tag_vocabulary_parser_rejects_invalid_schemas(payload):
    with pytest.raises(ValueError):
        parse_tag_vocabulary_payload(payload)


def test_bank_tag_collection_normalizes_aliases_and_tracks_coverage(tmp_path: Path):
    path = tmp_path / "exercise_bank.json"
    path.write_text(
        json.dumps(
            [
                {
                    "name": "Alias Example",
                    "tags": ["distance fighter", "gas_tank", "gas_tank"],
                }
            ]
        ),
        encoding="utf-8",
    )

    result = collect_bank_tags([path])

    assert result["canonical_counts"]["distance_striker"] == 1
    assert result["canonical_counts"]["gas_tank"] == 2
    assert result["aliases"]["distance fighter"] == "distance_striker"
    assert result["files_by_tag"]["gas_tank"] == {"exercise_bank.json"}


def test_vocabulary_is_canonical_collision_free_and_excludes_field_names():
    raw_vocab = read_tag_vocabulary_items(DATA_DIR / "tag_vocabulary.json")
    canonical = [normalize_tag(tag) for tag in raw_vocab]

    assert all(tag and tag == normalized for tag, normalized in zip(raw_vocab, canonical))
    assert len(canonical) == len(set(canonical))
    assert "distance_fighter" not in raw_vocab
    assert "distance_striker" in raw_vocab
    assert "late_windows" not in raw_vocab
    assert "cut_buckets_allowed" not in raw_vocab


def test_scoring_tag_inventory_includes_all_live_scoring_surfaces():
    scoring = collect_scoring_tags()
    all_tags = set().union(*scoring.values())

    assert {"goal", "weakness", "style", "clarification_detail", "clarification_generic", "phase"}.issubset(scoring)
    assert "movement_quality" in all_tags
    assert "ringcraft" in all_tags
    assert "distance_striker" in all_tags
    assert "decision_speed" not in all_tags
    assert "tempo" not in all_tags


def test_all_scoring_tags_are_canonical_vocab_tags_with_bank_coverage():
    vocab = set(read_tag_vocabulary_items(DATA_DIR / "tag_vocabulary.json"))
    bank = collect_bank_tags(discover_banks(DATA_DIR))
    bank_tags = set(bank["canonical_counts"])
    scoring = collect_scoring_tags()
    scoring_tags = set().union(*scoring.values())

    assert scoring_tags <= vocab
    assert scoring_tags <= bank_tags


def test_runtime_tag_inventory_is_precise_and_keeps_late_safety_controls():
    runtime = collect_runtime_control_tags()
    all_tags = set().union(*runtime.values())

    assert {
        "d1_ok",
        "d1_if_familiar",
        "familiarity_required",
        "no_d4_to_d1",
        "no_d7_to_d1",
        "balance_challenge",
        "vestibular_sensitive",
    }.issubset(all_tags)
    assert not {"blockquote", "h1", "iframe", "table", "tbody", "meta"}.intersection(all_tags)
    assert not {"late_windows", "cut_buckets_allowed"}.intersection(all_tags)


def test_generated_injury_safety_tags_are_registered():
    vocabulary = set(read_tag_vocabulary_items(DATA_DIR / "tag_vocabulary.json"))
    injury_tags = collect_generated_injury_tags()

    assert {
        "max_velocity",
        "landing_stress_high",
        "achilles_high_risk_impact",
        "contact",
        "head_impact",
        "decel_high",
    }.issubset(injury_tags)
    assert injury_tags <= vocabulary


def test_persisted_banks_are_canonical_and_reviewed_removed_tokens_are_gone():
    bank = collect_bank_tags(discover_banks(DATA_DIR))
    bank_tags = set(bank["canonical_counts"])

    assert bank["aliases"] == {}
    decisions = load_review_decisions()
    for tag, row in decisions.items():
        if row["decision"] == "remove_from_tags":
            assert tag not in bank_tags
        else:
            assert tag in bank_tags


def test_tag_registry_data_migration_is_up_to_date():
    assert planned_changes() == []


def _clean_gate_report(**overrides):
    report = {
        "aliases_in_vocabulary": {},
        "vocabulary_collisions": {},
        "bank_missing_vocab": [],
        "scoring_missing_vocab": [],
        "runtime_missing_vocab": [],
        "scoring_zero_bank_coverage": [],
        "bank_aliases": {},
        "synonym_canonicals": ["boxing", "recovery", "coordination", "skill"],
        "bank_tag_details": {
            "boxing": {},
            "recovery": {},
            "coordination": {},
            "skill": {},
            "max_velocity": {},
            "reviewed_descriptor": {},
        },
    }
    report.update(overrides)
    return report


def test_authority_gate_rejects_any_persisted_alias_debt():
    vocabulary = {"boxing", "recovery", "coordination", "skill", "max_velocity", "reviewed_descriptor"}
    assert authority_failures(_clean_gate_report(), vocabulary) == []

    failures = authority_failures(
        _clean_gate_report(bank_aliases={"boxer": "boxing"}),
        vocabulary,
    )
    assert any("bank_aliases" in failure for failure in failures)


def test_authority_gate_rejects_missing_synonym_targets():
    failures = authority_failures(
        _clean_gate_report(),
        {"boxing", "recovery", "coordination", "max_velocity", "reviewed_descriptor"},
    )
    assert any("synonym_targets_missing_from_vocabulary" in failure for failure in failures)


def test_authority_gate_rejects_new_generated_safety_tag_without_registration():
    vocabulary = {"boxing", "recovery", "coordination", "skill", "reviewed_descriptor"}
    failures = authority_failures(
        _clean_gate_report(),
        vocabulary,
        generated_injury_tags={"max_velocity", "brand_new_safety_tag"},
    )
    assert any("generated_injury_tags_missing_from_vocabulary" in failure for failure in failures)


def test_review_decisions_are_enforced_by_gate():
    vocabulary = {"boxing", "recovery", "coordination", "skill", "max_velocity", "reviewed_descriptor"}
    failures = authority_failures(
        _clean_gate_report(),
        vocabulary,
        review_decisions={
            "reviewed_descriptor": {
                "decision": "allow_canonical",
                "category": "movement_quality",
                "rationale": "Reviewed descriptor.",
            },
            "setup_only": {
                "decision": "remove_from_tags",
                "category": "setup_metadata",
                "rationale": "Not a semantic tag.",
            },
        },
    )
    assert failures == []

    failures = authority_failures(
        _clean_gate_report(bank_tag_details={"reviewed_descriptor": {}, "setup_only": {}}),
        vocabulary | {"setup_only"},
        review_decisions={
            "setup_only": {
                "decision": "remove_from_tags",
                "category": "setup_metadata",
                "rationale": "Not a semantic tag.",
            }
        },
    )
    assert any("reviewed_removed_tag_still_live" in failure for failure in failures)
