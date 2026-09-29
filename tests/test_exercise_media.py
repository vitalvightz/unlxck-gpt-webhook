from __future__ import annotations

import copy
from types import SimpleNamespace

import httpx
import pytest

from api.auth import AuthenticatedUser
from api.models import ExerciseMedia, PlanOutputs
from api.services import exercise_media as media
from api.structured_plan_models import StructuredTrainingPlan
from support import _build_client, _build_request, finalized_result
from test_structured_plan_models import _valid_plan
from tools import exercise_media as media_tool


@pytest.fixture(autouse=True)
def _fresh_index():
    media.reset_media_index_cache()
    yield
    media.reset_media_index_cache()


def _row(key, video_id="dQw4w9WgXcQ", **extra):
    return {"exercise_key": key, "video_id": video_id, "start_s": 42, "end_s": 70, **extra}


def _plan_with_blocks(*names: str) -> dict:
    """The model-valid fixture plan, with its first session's blocks renamed."""
    plan = copy.deepcopy(_valid_plan())
    session = plan["weeks"][0]["days"][0]["sessions"][0]
    template = session["blocks"][0]
    session["blocks"] = [
        {**copy.deepcopy(template), "block_id": f"b-{i}", "display_name": name}
        for i, name in enumerate(names)
    ]
    return plan


# -- normalization -----------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Romanian Deadlift (RDL)", "romanian-deadlift"),
        ("Step-Back Pivot Reset - technical", "step-back-pivot-reset"),
        ("Sled Push – light", "sled-push"),
        ("  Single-Leg Rotational Hop to Balance ", "single-leg-rotational-hop-to-balance"),
        ("Clean & Press", "clean-and-press"),
        ("Pallof Press", "pallof-press"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_exercise_key(name, expected):
    assert media.normalize_exercise_key(name) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?t=10", "dQw4w9WgXcQ"),
        ("youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://vimeo.com/123456", None),
        ("https://www.youtube.com/watch?v=short", None),
        ("", None),
    ],
)
def test_parse_youtube_video_id(value, expected):
    assert media.parse_youtube_video_id(value) == expected


# -- index + resolution ------------------------------------------------------


def test_primary_key_beats_another_rows_alias():
    index = media.build_media_index(
        [
            _row("sled-push", video_id="AAAAAAAAAAA"),
            _row("sled-drag", video_id="BBBBBBBBBBB", aliases=["Sled Push"]),
        ]
    )
    assert index["sled-push"].video_id == "AAAAAAAAAAA"
    assert index["sled-drag"].video_id == "BBBBBBBBBBB"


def test_index_skips_malformed_rows_and_drops_inverted_segment():
    index = media.build_media_index(
        [
            _row("bad-id", video_id="nope"),
            {"exercise_key": "inverted", "video_id": "CCCCCCCCCCC", "start_s": 30, "end_s": 10},
            _row("coach", source="coach"),
        ]
    )
    assert "bad-id" not in index
    assert index["inverted"].end_s is None
    assert index["coach"].source == "coach"


def test_resolve_keys_media_by_exact_display_name():
    plan = StructuredTrainingPlan.model_validate(
        _plan_with_blocks("Romanian Deadlift (RDL)", "Breathing Reset", "RDL")
    )
    index = media.build_media_index([_row("romanian-deadlift", aliases=["RDL"])])

    resolved = media.resolve_plan_exercise_media(plan, index)

    assert set(resolved) == {"Romanian Deadlift (RDL)", "RDL"}
    assert resolved["RDL"] == ExerciseMedia(video_id="dQw4w9WgXcQ", start_s=42, end_s=70)


def test_load_index_is_cached_and_survives_store_failure():
    calls = {"n": 0}

    class Store:
        def list_exercise_media(self):
            calls["n"] += 1
            if calls["n"] > 1:
                raise RuntimeError("supabase down")
            return [_row("sled-push")]

    store = Store()
    first = media.load_media_index(store, now=0.0)
    cached = media.load_media_index(store, now=10.0)
    after_failure = media.load_media_index(store, now=media.INDEX_TTL_SECONDS + 1)

    assert calls["n"] == 2
    assert "sled-push" in first and cached is first
    # A failed refresh keeps serving the last good index instead of dropping videos.
    assert "sled-push" in after_failure


def test_attach_never_raises_and_skips_stores_without_media():
    outputs = PlanOutputs(plan_text="", structured_plan=None)
    detail = SimpleNamespace(outputs=outputs)
    assert media.attach_exercise_media(detail, object()) is detail
    assert outputs.exercise_media == {}

    boom = SimpleNamespace(outputs=SimpleNamespace(structured_plan=object()))

    class Store:
        def list_exercise_media(self):
            raise RuntimeError("boom")

    media.attach_exercise_media(boom, Store())


# -- availability checks -----------------------------------------------------


def _client_for(status_code: int, body: dict | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "www.youtube.com"
        return httpx.Response(status_code, json=body or {})

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [(200, "ok"), (401, "unavailable"), (404, "unavailable"), (400, "unavailable"), (500, "unknown")],
)
def test_check_youtube_video_maps_oembed_status(status_code, expected):
    result = media.check_youtube_video("dQw4w9WgXcQ", client=_client_for(status_code, {"title": "RDL demo"}))
    assert result.status == expected


def test_check_youtube_video_treats_transport_errors_as_unknown():
    def handler(request):
        raise httpx.ConnectError("offline", request=request)

    result = media.check_youtube_video("dQw4w9WgXcQ", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert result.status == "unknown"


def test_verification_sweep_updates_ok_and_unavailable_but_not_unknown():
    statuses = {"good": 200, "gone": 404, "flaky": 503}
    ids = {"good": "AAAAAAAAAAA", "gone": "BBBBBBBBBBB", "flaky": "CCCCCCCCCCC"}
    by_id = {vid: statuses[key] for key, vid in ids.items()}
    updates: list[tuple[str, str]] = []

    class Store:
        def list_exercise_media_for_verification(self):
            return [{"exercise_key": key, "video_id": vid} for key, vid in ids.items()]

        def update_exercise_media_status(self, key, *, status, reason):
            updates.append((key, status))

    def handler(request):
        vid = request.url.params["url"].rsplit("=", 1)[-1]
        return httpx.Response(by_id[vid], json={})

    counts = media.run_media_verification_sweep(Store(), client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert sorted(updates) == [("gone", "unavailable"), ("good", "ok")]
    assert counts == {"ok": 1, "unavailable": 1, "unknown": 1}


# -- curation tool -----------------------------------------------------------


def test_rank_candidates_skips_existing_and_non_demo_blocks():
    plan = {
        "weeks": [
            {
                "days": [
                    {
                        "sessions": [
                            {
                                "blocks": [
                                    {"display_name": "Sled Push", "block_type": "strength"},
                                    {"display_name": "Sled Push - light", "block_type": "strength"},
                                    {"display_name": "Pallof Press", "block_type": "accessory"},
                                    {"display_name": "Body Attack Opportunity", "block_type": "mindset"},
                                    {"display_name": "RDL", "block_type": "strength"},
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }
    rows = media_tool.rank_candidates([plan, None], existing_keys={"rdl"}, limit=10)
    assert [(row["exercise_key"], row["occurrences"]) for row in rows] == [
        ("sled-push", 2),
        ("pallof-press", 1),
    ]


def test_parse_import_row_validates_and_collects_aliases():
    payload, error = media_tool.parse_import_row(
        {
            "exercise_key": "romanian-deadlift",
            "example_name": "Romanian Deadlift (RDL)",
            "youtube_url": "https://youtu.be/dQw4w9WgXcQ",
            "start_s": "42",
            "end_s": "70",
            "source": "coach",
            "aliases": "RDL | Barbell RDL",
        }
    )
    assert error is None
    assert payload["video_id"] == "dQw4w9WgXcQ"
    assert payload["source"] == "coach"
    assert payload["aliases"] == ["barbell-rdl", "rdl"]

    assert media_tool.parse_import_row({"exercise_key": "x", "youtube_url": ""}) == (None, None)
    assert media_tool.parse_import_row({"exercise_key": "x", "youtube_url": "https://vimeo.com/1"})[1]
    assert media_tool.parse_import_row(
        {"exercise_key": "x", "youtube_url": "dQw4w9WgXcQ", "start_s": "30", "end_s": "10"}
    )[1]


# -- plan read ---------------------------------------------------------------


def test_plan_read_serves_media_for_matching_blocks_only():
    client, store, _ = _build_client()
    store.ensure_profile(
        AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari", metadata={})
    )
    store.list_exercise_media = lambda: [_row("back-squat", aliases=["Barbell Back Squat"], source="coach")]
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_media",
        request=_build_request(),
        result=finalized_result(
            structured_plan=_valid_plan()
        ),
    )

    response = client.get(f"/api/plans/{plan['id']}", headers={"Authorization": "Bearer athlete-token"})

    assert response.status_code == 200
    outputs = response.json()["outputs"]
    assert outputs["structured_plan"] is not None
    assert outputs["exercise_media"] == {
        "Barbell Back Squat": {
            "provider": "youtube",
            "video_id": "dQw4w9WgXcQ",
            "start_s": 42,
            "end_s": 70,
            "source": "coach",
        }
    }
