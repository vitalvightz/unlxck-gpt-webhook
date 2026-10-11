"""Two focused checks for the closed descriptive dictionary and public AND filters."""
from copy import deepcopy

from api.services import training_library as lib
from fightcamp.training_metadata import exercise_details
from tests.support import _build_client

AUTH = {"Authorization": "Bearer athlete-token"}


def test_dictionary_is_field_scoped_descriptive_and_source_supported():
    index = lib.LibraryCache().get()
    rules = index.projection["discovery_filters"]
    assert len(rules) == 21
    assert {r["group"] for r in rules} == set(lib.DETAIL_FILTERS)
    for rule in rules:
        for source in rule["sources"]:
            for value in source["values"]:
                assert any(value in ([raw] if isinstance(raw, str) else raw or [])
                           for record in index.records if record["summary"]["category"] == "training"
                           for raw in [record["entry"]["raw"].get(source["field"])])
    sample = deepcopy(next(r["entry"] for r in index.records if r["summary"]["category"] == "training"))
    sample["raw"] = {"tags": ["mech_reactive", "mech_grip_support", "mech_trunk_rotation", "injury_risk", "rehab_friendly", "taper"],
                     "goals": ["isometric"], "contraindications": ["footwork"], "method": "rotational"}
    assert exercise_details(sample, index.projection) == []
    sample["raw"] = {"movement": "rotational", "tags": ["isometric"], "method": "strength"}
    assert {v["value"] for v in exercise_details(sample, index.projection)} == {"rotation", "static_holds", "resistance"}
    sample["content_class"] = "rehabilitation"
    assert exercise_details(sample, index.projection) == []
    training = [r for r in index.records if r["summary"]["category"] == "training"]
    assert sum(bool(r["facets"]["goal"]) for r in training) == 278
    assert sum(bool(r["summary"]["exercise_details"]) for r in training) == 483
    holds = lib.search(index, filters={"training_method": "static_holds"}, limit=3000)
    assert holds["total"] > 0
    assert holds["total"] == len({e["catalogue_id"] for e in holds["entries"]})
    assert any(not e["verified_goals"] for e in holds["entries"])
    friendly = lib.search(index, q="static holds", limit=3000)
    assert {e["catalogue_id"] for e in holds["entries"]} <= {e["catalogue_id"] for e in friendly["entries"]}
    assert next(r["label"] for r in rules if r["id"] == "slow_lowering") == "Lowering-focused"
    for alias in index.projection["facet_aliases"]:
        field = alias["field"]
        # Both spellings select the exact same distinct exercises, including
        # rows containing both values; raw source requirements remain intact.
        results = [lib.search(index, filters={field: value}, limit=3000) for value in alias["source_values"]]
        assert all(result == results[0] for result in results)
        expected = {r["entry"]["catalogue_id"] for r in training if alias["canonical_id"] in r["facets"][field]}
        assert {e["catalogue_id"] for e in results[0]["entries"]} == expected
        options = lib.search(index)["facets"][field]
        assert next(o for o in options if o["value"] == alias["canonical_id"])["count"] == len(expected)
        assert not {o["value"] for o in options}.intersection(set(alias["source_values"]) - {alias["canonical_id"]})
    assert next(o for o in lib.search(index)["facets"]["body_focus"] if o["value"] == "lower_body")["label"] == "Legs"
    assert "neck_vestibular" in {o["value"] for o in lib.search(index)["facets"]["body_focus"]}


def test_api_combines_optional_groups_counts_pagination_and_category_boundary():
    index = lib.LibraryCache().get()
    client, _, _ = _build_client()
    filters = {"goal": "Power", "movement": "rotation", "training_method": "power_practice"}
    expected = {r["entry"]["catalogue_id"] for r in index.records if lib._matches(r, filters)}
    assert len(expected) > 1
    response = client.get("/api/training/library", headers=AUTH, params={**filters, "limit": 1})
    assert response.status_code == 200, response.text
    first = response.json()
    assert first["total"] == len(expected)
    second = client.get("/api/training/library", headers=AUTH,
                        params={**filters, "limit": 50, "offset": first["next_offset"], "revision": first["revision"]}).json()
    ids = [e["catalogue_id"] for e in first["entries"] + second["entries"]]
    assert len(ids) == len(set(ids)) == len(expected)
    assert set(ids) == expected
    assert second["next_offset"] is None
    no_goal = client.get("/api/training/library", headers=AUTH, params={"training_method": "static_holds", "limit": 50}).json()
    assert no_goal["total"] == 77
    assert any(not e["verified_goals"] for e in no_goal["entries"])
    assert next(f["count"] for f in no_goal["facets"]["training_method"] if f["value"] == "static_holds") == 77
    for group in lib.DETAIL_FILTERS:
        assert client.get("/api/training/library", headers=AUTH, params={group: "unknown"}).json()["total"] == 0
    for category in ("rehab", "learn"):
        result = client.get("/api/training/library", headers=AUTH, params={"category": category}).json()
        assert not set(lib.DETAIL_FILTERS).intersection(result["facets"])
        assert all(not e["exercise_details"] for e in result["entries"])
        assert client.get("/api/training/library", headers=AUTH,
                          params={"category": category, "movement": "rotation"}).json()["total"] == 0
