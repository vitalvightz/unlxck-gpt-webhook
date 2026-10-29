"""Reviewed discovery identities never authorize prescription or substitution."""
from copy import deepcopy

import pytest

from api.contracts.training_library import LibraryPreview
from api.services import training_library as lib
from fightcamp import training_metadata as metadata
from tests.support import _build_client


@pytest.fixture(scope="module")
def index():
    return lib.LibraryCache().get()


@pytest.mark.parametrize("ordinal", range(6))
@pytest.mark.parametrize("category", ["training", "rehab", "learn"])
def test_reviewed_aliases_have_one_option_distinct_counts_and_legacy_compatibility(index, ordinal, category):
    mapping = index.projection["mappings"][ordinal]
    field = "equipment" if mapping["field"] == "equipment" else "body_focus"
    # Anatomical aliases apply only to Training, never clinical regions.
    if field == "body_focus" and category != "training":
        for alias in mapping["source_values"]:
            assert metadata.canonical_filter(field, alias, category, index.projection) == alias
        return
    results = [lib.search(index, category=category, filters={field: value}, limit=3000)
               for value in (*mapping["source_values"], mapping["canonical_id"])]
    assert all(r == results[0] for r in results)
    assert results[0]["total"] == len({r["catalogue_id"] for r in results[0]["entries"]})
    options = lib.search(index, category=category, limit=1)["facets"][field]
    matching = [o for o in options if o["value"] in {*mapping["source_values"], mapping["canonical_id"]}]
    assert len(matching) == bool(results[0]["total"])
    if matching:
        assert matching[0] == {"value": mapping["canonical_id"], "label": mapping["label"], "count": results[0]["total"]}


def test_all_original_metadata_and_provenance_remain_available(index):
    for record in index.records:
        detail = lib.preview(record)
        serialized = LibraryPreview.model_validate(detail).model_dump()["metadata_projection"]
        for value in serialized:
            if not value["goal_evidence"]:
                value.pop("goal_evidence")
        assert serialized == detail["metadata_projection"]
        assert detail["equipment_source"]["raw"] == record["entry"]["raw"].get("equipment")
        for value in record["projection"]:
            raw = record["entry"]["raw"][value["source_field"]]
            assert value["source_value"] in raw if isinstance(raw, list) else value["source_value"] == raw
            assert value["source"] == record["entry"]["source"]
            assert value["source_revision"] == record["entry"]["source_sha256"]
            assert value["row_revision"] == record["entry"]["row_sha256"]
            if value["audit_decision"]:
                assert value["audit_report"] == metadata.AUDIT_REPORT
                assert value["audit_revision"] == metadata.AUDIT_REVISION
        assert detail["prescription_allowed"] is False


@pytest.mark.parametrize("field,values", [
    ("equipment", ["bands", "mini_band", "spin_bike", "assault_bike", "thai_pads", "focus_mitts", "climbing_rope"]),
    ("body_focus", ["neck", "neck_vestibular", "groin_adductor", "hip_adductors"]),
    ("goal", ["hand_foot_timing", "foot_hand_timing", "reaction", "mech_reactive", "grip", "mech_grip_support", "alactic", "glycolytic"]),
])
def test_unreviewed_concepts_are_not_flattened(index, field, values):
    assert [metadata.canonical_filter(field, v, "training", index.projection) for v in values] == values


@pytest.mark.parametrize("value", ["bands,heavy_bag", "treadmill/rower", "sledgehammer/tire"])
def test_compounds_are_raw_unresolved_tokens_without_invented_and_or(index, value):
    source = deepcopy(index.records[0]["entry"])
    source["raw"]["equipment"] = [value]
    source["metadata"]["equipment"]["state"] = "known"
    record = lib._prepare(source, projection=index.projection)
    assert record["facets"]["equipment"] == {value}
    assert record["projection"][0]["source_value"] == value
    assert record["projection"][0]["status"] == "unresolved_compound"
    assert record["projection"][0]["audit_decision"] is None


def test_unknown_equipment_does_not_become_no_equipment_or_a_verified_alias(index):
    source = deepcopy(index.records[0]["entry"])
    source["raw"]["equipment"] = ["kettlebells"]
    source["metadata"]["equipment"]["state"] = "unknown"
    record = lib._prepare(source, projection=index.projection)
    assert not record["facets"]["equipment"]
    assert record["summary"]["equipment"] is None
    assert record["projection"][0]["canonical_id"] == "kettlebells"
    assert not record["projection"][0]["filter_eligible"]


def test_quantities_alternatives_and_optional_attachments_remain_evidence(index):
    source = deepcopy(index.records[0]["entry"])
    source["metadata"]["equipment"]["state"] = "known"
    source["metadata"]["instructions"] = {"state": "known"}
    for raw, instruction in (("kettlebell", "Use one kettlebell; optional handle attachment."),
                             ("kettlebells", "Use two kettlebells simultaneously, or use a barbell.")):
        source["raw"].update(equipment=[raw], instructions=instruction)
        detail = lib.preview(lib._prepare(source, projection=index.projection))
        assert detail["metadata_projection"][0]["canonical_id"] == "kettlebell"
        assert detail["metadata_projection"][0]["requirement_evidence"]["instructions"] == instruction
        assert detail["equipment_source"]["raw"] == [raw]
        assert detail["guidance"]["Instructions"][0] == instruction
        assert detail["equipment_source"]["guidance"]["notes"] == source["raw"]["notes"]


def test_filters_keep_and_semantics_and_independent_counts(index):
    gear = lib.search(index, filters={"equipment": "kettlebell"}, limit=3000)
    strength = lib.search(index, filters={"type": "strength_power"}, limit=3000)
    both = lib.search(index, filters={"equipment": "kettlebells", "type": "strength_power"}, limit=3000)
    def ids(result):
        return {e["catalogue_id"] for e in result["entries"]}
    assert ids(both) == ids(gear) & ids(strength)
    assert both["facets"]["equipment"] == strength["facets"]["equipment"]
    assert both["facets"]["type"] == gear["facets"]["type"]
    assert both["total"] > 0


def test_two_alias_tokens_on_one_row_count_as_one_exercise(index):
    source = deepcopy(index.records[0]["entry"])
    source["raw"]["equipment"] = ["kettlebell", "kettlebells"]
    source["metadata"]["equipment"]["state"] = "known"
    record = lib._prepare(source, projection=index.projection)
    isolated = lib.LibraryIndex((), "fixture", (record,), {source["catalogue_id"]: record}, index.projection)
    result = lib.search(isolated, filters={"equipment": "kettlebells"})
    assert result["total"] == 1
    assert result["facets"]["equipment"] == [{"value": "kettlebell", "label": "Kettlebell", "count": 1}]
    assert [v["source_value"] for v in record["projection"] if v["source_field"] == "equipment"] == ["kettlebell", "kettlebells"]


def test_anatomical_focus_has_reviewed_training_evidence_only(index):
    result = lib.search(index, filters={"body_focus": "adductor"}, limit=3000)
    assert result["total"] == 7
    for row in result["entries"]:
        values = index.by_id[row["catalogue_id"]]["projection"]
        anatomy = next(v for v in values if v["dimension"] == "anatomical_focus" and v["canonical_id"] == "adductors")
        assert anatomy["subtype"] == "hip_adductors"
        assert anatomy["source_field"] == "tags"
    assert all(not any(v["dimension"] == "anatomical_focus" for v in r["projection"]) for r in index.records if r["summary"]["category"] != "training")


def test_canonical_words_are_searchable_without_losing_exact_name_priority(index):
    for mapping in index.projection["mappings"]:
        field = "equipment" if mapping["field"] == "equipment" else "body_focus"
        filtered = lib.search(index, filters={field: mapping["canonical_id"]}, limit=3000)
        searched = lib.search(index, q=mapping["label"], filters={field: mapping["canonical_id"]}, limit=3000)
        assert {e["catalogue_id"] for e in searched["entries"]} == {e["catalogue_id"] for e in filtered["entries"]}
    assert lib.search(index, q="Kettlebell Snatch Test")["entries"][0]["name"] == "Kettlebell Snatch Test"


def test_cache_revision_includes_reviewed_contracts(index, tmp_path, monkeypatch):
    cache = lib.LibraryCache()
    before = cache.get()
    paths = []
    for path in metadata.CONTRACT_FILES:
        target = tmp_path / path.name
        target.write_bytes(path.read_bytes())
        paths.append(target)
    monkeypatch.setattr(lib, "CONTRACT_FILES", tuple(paths))
    after = cache.get()
    assert after.revision == before.revision
    paths[1].write_bytes(paths[1].read_bytes() + b"\n")
    assert cache.get().revision != before.revision
    assert index.revision == before.revision


def test_api_preview_serializes_canonical_and_original_fields(monkeypatch, index):
    client, _, _ = _build_client()
    monkeypatch.setattr(lib, "cache", lib.LibraryCache())
    target = next(r for r in index.records if any(v["source_value"] == "kettlebells" for v in r["projection"]))
    try:
        response = client.get("/api/training/library/entry", params={"catalogue_id": target["entry"]["catalogue_id"]}, headers={"Authorization": "Bearer athlete-token"})
        assert response.status_code == 200
        detail = response.json()
        assert detail["equipment_source"]["raw"] == target["entry"]["raw"]["equipment"]
        assert any(v["source_value"] == "kettlebells" and v["canonical_id"] == "kettlebell" for v in detail["metadata_projection"])
        assert detail["prescription_allowed"] is False
    finally:
        client.close()


