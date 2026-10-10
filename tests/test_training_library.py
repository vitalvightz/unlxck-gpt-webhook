"""Discovery relevance, evidence boundaries and authenticated API integration."""
from collections import Counter, defaultdict
from copy import deepcopy
import json
import shutil

import pytest

from api.services import training_library as lib
from api.services.exercise_media import reset_media_index_cache
from fightcamp.training_catalogue import ALIASES_FILE, DATA_DIR, MANIFEST_FILE, SOURCE_CLASSES
from tests.support import _build_client

AUTH = {"Authorization": "Bearer athlete-token"}


@pytest.fixture(scope="module")
def index():
    return lib.LibraryCache().get()


@pytest.fixture
def copied_data(tmp_path):
    for source in (*SOURCE_CLASSES, MANIFEST_FILE, ALIASES_FILE):
        target = tmp_path / source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DATA_DIR / source, target)
    return tmp_path


def test_inventory_categories_and_boundaries(index):
    assert len(index.by_id) == 2855
    assert Counter(r["summary"]["category"] for r in index.records) == dict(training=1010, rehab=1499, learn=346)
    assert all(not r["summary"]["prescription_allowed"] for r in index.records)
    for category, boundary in (("training", "training_validation_required"), ("rehab", "rehab_pathway_only"), ("learn", "excluded")):
        found = lib.search(index, category=category)
        assert found["catalogue_total"] == 2855
        assert {r["selection_boundary"] for r in found["entries"]} == {boundary}


@pytest.mark.parametrize("query", ["Punching power", "Reaction speed", "Stamina", "Core stability", "Shoulder control", "Footwork", "Explosive legs", "Medicine ball", "Defensive movement", "medicne ball", "punchng power"])
def test_fighter_language_and_typos(index, query):
    assert lib.search(index, q=query)["total"] > 0


def test_reviewed_punching_aliases_lead_and_generic_rotation_is_not_an_alias(index):
    result = lib.search(index, q="punching power")
    assert [e["name"] for e in result["entries"][:2]] == ["Medicine Ball Hook Throw", "Standing Cable Punch Simulation"]
    for r in index.records:
        if "Punching power" in r["facets"]["goal"]:
            assert r["entry"]["name"] in {"Medicine Ball Hook Throw", "Standing Cable Punch Simulation"}
        if "Stamina" in r["facets"]["goal"]:
            assert "aerobic" in r["entry"]["raw"].get("tags", []) or "aerobic_capacity" in r["entry"]["raw"].get("qualities", [])
        if "Reaction speed" in r["facets"]["goal"]:
            assert "reaction" in r["entry"]["raw"].get("tags", []) or {"reaction", "decision_reaction", "tactile_reaction", "reactive_agility"}.intersection(r["entry"]["raw"].get("qualities", []))
        if "Explosive legs" in r["facets"]["goal"]:
            assert r["entry"]["raw"].get("category") == "lower_body"
            assert "explosive" in r["entry"]["raw"].get("tags", [])
        if "Defensive movement" in r["facets"]["goal"]:
            assert {"defensive_exit", "takedown_defense"}.intersection(r["entry"]["raw"].get("tactical_function", []))


def test_rank_exact_phrase_partial_alias_and_description(index):
    target = next(r for r in index.records if r["entry"]["name"] == "Medicine Ball Hook Throw")
    exact = lib.search(index, q=target["entry"]["name"])["entries"][0]
    assert exact["catalogue_id"] == target["entry"]["catalogue_id"]
    assert target["entry"]["catalogue_id"] in {e["catalogue_id"] for e in lib.search(index, q="medicine ball hook")["entries"]}
    # Controlled ranking examples exercise every tier without changing bank data.
    records = []
    for name, alias, description in (("Test Drill", "", ""), ("Test Drill Extended", "", ""), ("Different", "test drill", ""), ("Other", "", "test drill")):
        record = deepcopy(target)
        record.update(name=name.lower(), aliases=alias, metadata="", description=description, words=frozenset(f"{name.lower()} {alias} {description}".split()))
        record["summary"].update(name=name, catalogue_id=name)
        record["entry"]["catalogue_id"] = name
        records.append(record)
    fixture = lib.LibraryIndex((), "test", tuple(records), {})
    assert [e["name"] for e in lib.search(fixture, q="test drill")["entries"]] == ["Test Drill", "Test Drill Extended", "Different", "Other"]


@pytest.mark.parametrize("field,value", [("type", "strength_power"), ("goal", "Punching power"), ("sport", "boxing"), ("equipment", "medicine_ball"), ("body_focus", "lower_body"), ("equipment", "no_equipment")])
def test_verified_filters(index, field, value):
    result = lib.search(index, filters={field: value}, limit=3000)
    assert result["total"] > 0
    for summary in result["entries"]:
        record = index.by_id[summary["catalogue_id"]]
        assert value in record["facets"][field] or (field == "sport" and "universal" in record["facets"][field])
        if field == "equipment" and value == "no_equipment":
            assert record["entry"]["metadata"]["equipment"]["state"] == "known"
            assert set(summary["equipment"]) <= {"none", "bodyweight"}


def test_query_and_filters_combine_and_reset(index):
    params = dict(q="punching power", filters=dict(type="strength_power", equipment="medicine_ball", goal="Punching power"))
    result = lib.search(index, **params)
    assert [e["name"] for e in result["entries"]] == ["Medicine Ball Hook Throw"]
    assert lib.search(index, q="punching power", filters={"equipment": "barbell"})["total"] == 0
    assert lib.search(index, q="punching power")["total"] == 4
    assert "difficulty" not in result["facets"]


def test_missing_metadata_does_not_exclude_name_search_and_unknown_is_not_no_equipment(index):
    target = next(r for r in index.records if r["summary"]["category"] == "training" and not r["facets"]["sport"])
    assert target["entry"]["catalogue_id"] in {e["catalogue_id"] for e in lib.search(index, q=target["entry"]["name"], limit=100)["entries"]}
    no_gear = next(r for r in index.records if r["summary"]["equipment"] is None)
    assert not no_gear["facets"]["equipment"]
    assert no_gear["summary"]["equipment_state"] != "known"
    assert all(v["value"] not in {"unknown", "unreviewed", "unspecified"} for values in lib.search(index)["facets"].values() for v in values)


def test_duplicate_names_keep_ids_and_distinguishing_context(index):
    results = lib.search(index, category="learn", q="Pressure Reset", limit=50)["entries"]
    repeated = [e for e in results if e["name"] == "Pressure → Reset"]
    assert len(repeated) == 17
    assert len({e["catalogue_id"] for e in repeated}) == len(repeated)
    assert len({e["context"] for e in repeated}) == len(repeated)
    groups = defaultdict(list)
    for record in index.records:
        groups[(record["summary"]["category"], record["entry"]["name"])].append(record["summary"])
    assert all(len({r["context"] for r in group}) == len(group) for group in groups.values() if len(group) > 1)


def test_pagination_deterministic_and_complete(index):
    pages = [lib.search(index, offset=offset, limit=50) for offset in range(0, 1010, 50)]
    ids = [e["catalogue_id"] for page in pages for e in page["entries"]]
    assert len(ids) == len(set(ids)) == 1010
    assert pages[-1]["next_offset"] is None
    assert lib.search(index, offset=50, limit=50) == pages[1]


def test_cache_reuses_index_reloads_sources_and_fails_closed(copied_data, monkeypatch):
    cache = lib.LibraryCache(copied_data)
    first = cache.get()
    original = lib.build_catalogue
    calls = []
    monkeypatch.setattr(lib, "build_catalogue", lambda path: (calls.append(path), original(path))[1])
    assert cache.get() is first
    assert calls == []
    source = copied_data / "exercise_bank.json"
    payload = json.loads(source.read_bytes())
    source.write_text(json.dumps(list(reversed(payload))), encoding="utf-8")
    second = cache.get()
    assert len(calls) == 1 and second.revision != first.revision
    assert set(second.by_id) == set(first.by_id)
    payload[0]["name"] += " changed without identity review"
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="identity"):
        cache.get()
    with pytest.raises(ValueError):
        cache.get()  # never serve the valid stale index


def test_source_change_during_loading_is_rejected(copied_data, monkeypatch):
    cache = lib.LibraryCache(copied_data)
    original = lib.build_catalogue
    def changing_source(path):
        entries = original(path)
        source = path / "conditioning_bank.json"
        source.write_bytes(source.read_bytes() + b"\n")
        return entries
    monkeypatch.setattr(lib, "build_catalogue", changing_source)
    with pytest.raises(ValueError, match="changed while loading"):
        cache.get()


def test_api_auth_pagination_media_and_preview(index, monkeypatch):
    client, store, _ = _build_client()
    reset_media_index_cache()
    monkeypatch.setattr(lib, "cache", lib.LibraryCache())
    try:
        assert client.get("/api/training/library").status_code == 401
        assert client.get("/api/training/library", headers=AUTH, params={"limit": 51}).status_code == 422
        first = client.get("/api/training/library", headers=AUTH, params={"q": "punching power"}).json()
        target = first["entries"][0]
        store.exercise_media[target["exercise_key"]] = {"exercise_key": target["exercise_key"], "video_id": "abcdefghijk", "made_for_kids": False, "status": "ok", "source": "curated"}
        reset_media_index_cache()
        result = client.get("/api/training/library/entry", headers=AUTH, params={"catalogue_id": target["catalogue_id"]})
        assert result.status_code == 200
        detail = result.json()
        assert detail["media"]["video_id"] == "abcdefghijk"
        assert detail["guidance"] == {}  # unavailable source coaching is not fabricated
        assert detail["prescription_allowed"] is False
        assert index.by_id[target["catalogue_id"]]["summary"]["media"] is None
        assert client.get("/api/training/library", headers=AUTH, params={"revision": "old"}).status_code == 409
        assert client.get("/api/training/library/entry", headers=AUTH, params={"catalogue_id": "unknown"}).status_code == 404
        learn = client.get("/api/training/library", headers=AUTH, params={"category": "learn", "q": "Pressure Reset"}).json()["entries"][0]
        guidance = client.get("/api/training/library/entry", headers=AUTH, params={"catalogue_id": learn["catalogue_id"]}).json()
        assert guidance["guidance"]["Instructions"] and guidance["guidance"]["Why"]
        assert guidance["media"] is None
        rehab = next(r["entry"] for r in index.records if r["summary"]["category"] == "rehab")
        from fightcamp.exercise_identity import normalize_exercise_key
        drill_key = normalize_exercise_key(rehab["source_id"])
        name_key = normalize_exercise_key(rehab["name"])
        store.exercise_media = {name_key: {"exercise_key": name_key, "video_id": "abcdefghijk", "made_for_kids": False, "status": "ok"}}
        reset_media_index_cache()
        params = {"catalogue_id": rehab["catalogue_id"]}
        assert client.get("/api/training/library/entry", headers=AUTH, params=params).json()["media"] is None
        store.exercise_media[drill_key] = {"exercise_key": drill_key, "video_id": "01234567890", "made_for_kids": False, "status": "ok"}
        reset_media_index_cache()
        assert client.get("/api/training/library/entry", headers=AUTH, params=params).json()["media"]["video_id"] == "01234567890"
    finally:
        reset_media_index_cache()


def test_api_invalid_catalogue_returns_503_and_no_stale_data(monkeypatch):
    client, _, _ = _build_client()
    monkeypatch.setattr(lib.cache, "get", lambda: (_ for _ in ()).throw(ValueError("private source path")))
    for path, params in (("/api/training/library", {}), ("/api/training/library/entry", {"catalogue_id": "id"})):
        result = client.get(path, headers=AUTH, params=params)
        assert result.status_code == 503
        assert "private source" not in result.text
