from __future__ import annotations

import json
from pathlib import Path

import pytest

from fightcamp.tag_vocabulary import parse_tag_vocabulary_payload, read_tag_vocabulary_items
from tools.audit_tag_registry import collect_bank_tags, collect_scoring_tags


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


def test_scoring_tag_inventory_includes_current_live_dimensions():
    scoring = collect_scoring_tags()
    all_tags = set().union(*scoring.values())

    assert "decision_speed" in all_tags
    assert "movement_quality" in all_tags
    assert "ringcraft" in all_tags
    assert "distance_striker" in all_tags
