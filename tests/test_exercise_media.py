from __future__ import annotations

import copy
import json
import re
import unicodedata
from pathlib import Path
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


REPO_ROOT = Path(__file__).resolve().parents[1]


def _row(key, video_id="dQw4w9WgXcQ", **extra):
    return {
        "exercise_key": key,
        "video_id": video_id,
        "start_s": 42,
        "end_s": 70,
        "made_for_kids": False,
        **extra,
    }


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
        ("Romanian Deadlift (RDL)", "romanian-deadlift-rdl"),
        ("Step-Back Pivot Reset - technical", "step-back-pivot-reset-technical"),
        ("Sled Push – light", "sled-push-light"),
        ("Box Jump (Max Height)", "box-jump-max-height"),
        ("  Single-Leg Rotational Hop to Balance ", "single-leg-rotational-hop-to-balance"),
        ("Clean & Press", "clean-and-press"),
        ("Hollow-Body Hold", "hollow-body-hold"),
        ("Hollow Body Hold", "hollow-body-hold"),
        ("Pallof Press", "pallof-press"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_exercise_key(name, expected):
    assert media.normalize_exercise_key(name) == expected


def _bank_exercise_names() -> set[str]:
    names: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            name = node.get("name")
            if isinstance(name, str) and name.strip():
                names.add(name)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for path in sorted((REPO_ROOT / "data").glob("*bank*.json")):
        walk(json.loads(path.read_text(encoding="utf-8")))
    return names


def test_media_key_keeps_every_word_of_every_bank_name():
    """Variants such as "Box Jump (Max Height)" and "Box Jump (Stick Landing)"
    must never collapse onto one key and inherit each other's video. Only an
    explicit alias on the media row may join two names."""
    names = _bank_exercise_names()
    assert len(names) > 500

    for name in names:
        folded = unicodedata.normalize("NFKD", name.lower()).encode("ascii", "ignore").decode("ascii")
        words = set(re.findall(r"[a-z0-9]+", folded.replace("&", " and ")))
        key_words = set(media.normalize_exercise_key(name).split("-"))
        assert words <= key_words, f"{name!r} lost {sorted(words - key_words)}"

    for left, right in [
        ("Box Jump (Max Height)", "Box Jump (Stick Landing)"),
        ("Sled Drag (Side)", "Sled Drag (Light, RPE 4)"),
        ("Box Jump", "Box Jump (Max Height)"),
        ("Random Attack Counter Rounds", "Random Attack Counter Rounds — Kickboxing"),
    ]:
        assert media.normalize_exercise_key(left) != media.normalize_exercise_key(right)


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
            _row("inverted", video_id="CCCCCCCCCCC", start_s=30, end_s=10),
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
    index = media.build_media_index([_row("romanian-deadlift-rdl", aliases=["RDL"])])

    resolved = media.resolve_plan_exercise_media(plan, index)

    assert set(resolved) == {"Romanian Deadlift (RDL)", "RDL"}
    assert resolved["RDL"] == ExerciseMedia(video_id="dQw4w9WgXcQ", start_s=42, end_s=70)


def test_variants_do_not_inherit_a_base_exercises_video():
    plan = StructuredTrainingPlan.model_validate(
        _plan_with_blocks("Box Jump", "Box Jump (Max Height)", "Box Jump (Stick Landing)")
    )
    index = media.build_media_index(
        [
            _row("box-jump", video_id="AAAAAAAAAAA"),
            _row("box-jump-stick-landing", video_id="BBBBBBBBBBB"),
        ]
    )

    resolved = media.resolve_plan_exercise_media(plan, index)

    assert resolved["Box Jump"].video_id == "AAAAAAAAAAA"
    assert resolved["Box Jump (Stick Landing)"].video_id == "BBBBBBBBBBB"
    assert "Box Jump (Max Height)" not in resolved


def test_index_serves_only_videos_checked_as_not_made_for_kids():
    index = media.build_media_index(
        [
            _row("checked", made_for_kids=False, channel_title="Coach Channel"),
            _row("made-for-kids", made_for_kids=True),
            _row("never-checked", made_for_kids=None),
        ]
    )
    assert set(index) == {"checked"}
    assert index["checked"].channel_title == "Coach Channel"


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

API_KEY = "test-api-key"


def _video(video_id, *, embeddable=True, made_for_kids=False, privacy="public", upload="processed"):
    status = {"uploadStatus": upload, "privacyStatus": privacy, "embeddable": embeddable}
    if made_for_kids is not None:
        status["madeForKids"] = made_for_kids
    return {
        "id": video_id,
        "snippet": {"title": f"Demo {video_id}", "channelTitle": "Strength Channel"},
        "status": status,
    }


def _data_api(items_by_id: dict, *, status_code=200, requests: list | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "www.googleapis.com"
        if requests is not None:
            requests.append(request)
        if status_code != 200:
            return httpx.Response(status_code, json={"error": {"code": status_code}})
        ids = request.url.params["id"].split(",")
        return httpx.Response(200, json={"items": [items_by_id[i] for i in ids if i in items_by_id]})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_check_youtube_videos_classifies_each_video():
    items = {
        "AAAAAAAAAAA": _video("AAAAAAAAAAA"),
        "BBBBBBBBBBB": _video("BBBBBBBBBBB", embeddable=False),
        "CCCCCCCCCCC": _video("CCCCCCCCCCC", made_for_kids=True),
        "DDDDDDDDDDD": _video("DDDDDDDDDDD", made_for_kids=None),
        "EEEEEEEEEEE": _video("EEEEEEEEEEE", privacy="private"),
        "FFFFFFFFFFF": _video("FFFFFFFFFFF", upload="rejected"),
    }
    requests: list[httpx.Request] = []
    ids = [*items, "GGGGGGGGGGG", "nope"]

    results = media.check_youtube_videos(ids, api_key=API_KEY, client=_data_api(items, requests=requests))

    assert {vid: (r.status, r.reason) for vid, r in results.items()} == {
        "AAAAAAAAAAA": ("ok", None),
        "BBBBBBBBBBB": ("unavailable", "embedding disabled"),
        "CCCCCCCCCCC": ("unavailable", "made for kids"),
        "DDDDDDDDDDD": ("unknown", "status not reported"),
        "EEEEEEEEEEE": ("unavailable", "private"),
        "FFFFFFFFFFF": ("unavailable", "upload rejected"),
        "GGGGGGGGGGG": ("unavailable", "not found or private"),
        "nope": ("unavailable", "invalid video id"),
    }
    ok = results["AAAAAAAAAAA"]
    assert (ok.made_for_kids, ok.title, ok.channel_title) == (False, "Demo AAAAAAAAAAA", "Strength Channel")
    # One call for the batch, and the key travels in a header, never the URL
    # (request logging would otherwise record it).
    assert len(requests) == 1
    assert requests[0].headers["X-Goog-Api-Key"] == API_KEY
    assert API_KEY not in str(requests[0].url)


def test_check_youtube_videos_batches_fifty_ids_per_call():
    ids = [f"{i:011d}" for i in range(120)]
    requests: list[httpx.Request] = []
    results = media.check_youtube_videos(
        ids, api_key=API_KEY, client=_data_api({i: _video(i) for i in ids}, requests=requests)
    )
    assert [len(r.url.params["id"].split(",")) for r in requests] == [50, 50, 20]
    assert all(r.status == "ok" for r in results.values())


@pytest.mark.parametrize("status_code", [403, 500])
def test_check_youtube_videos_treats_api_errors_as_unknown(status_code):
    result = media.check_youtube_video(
        "dQw4w9WgXcQ", api_key=API_KEY, client=_data_api({}, status_code=status_code)
    )
    assert result.status == "unknown"


def test_check_youtube_videos_treats_transport_errors_as_unknown():
    def handler(request):
        raise httpx.ConnectError("offline", request=request)

    result = media.check_youtube_video(
        "dQw4w9WgXcQ", api_key=API_KEY, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert result.status == "unknown"


def test_verification_sweep_rechecks_unavailable_rows_and_skips_unknown():
    rows = [
        {"exercise_key": "good", "video_id": "AAAAAAAAAAA", "status": "ok"},
        {"exercise_key": "gone", "video_id": "BBBBBBBBBBB", "status": "ok"},
        {"exercise_key": "kids", "video_id": "CCCCCCCCCCC", "status": "ok"},
        # Was restricted for a while and is fine again: it must come back.
        {"exercise_key": "recovered", "video_id": "DDDDDDDDDDD", "status": "unavailable"},
        {"exercise_key": "unreported", "video_id": "EEEEEEEEEEE", "status": "ok"},
    ]
    items = {
        "AAAAAAAAAAA": _video("AAAAAAAAAAA"),
        "CCCCCCCCCCC": _video("CCCCCCCCCCC", made_for_kids=True),
        "DDDDDDDDDDD": _video("DDDDDDDDDDD"),
        "EEEEEEEEEEE": _video("EEEEEEEEEEE", made_for_kids=None),
    }
    updates: dict[str, dict] = {}

    class Store:
        def list_exercise_media_for_verification(self):
            return rows

        def update_exercise_media_status(self, key, **fields):
            updates[key] = fields

    counts = media.run_media_verification_sweep(Store(), api_key=API_KEY, client=_data_api(items))

    assert {key: fields["status"] for key, fields in updates.items()} == {
        "good": "ok",
        "gone": "unavailable",
        "kids": "unavailable",
        "recovered": "ok",
    }
    assert updates["kids"]["made_for_kids"] is True
    assert updates["recovered"]["channel_title"] == "Strength Channel"
    assert counts == {"ok": 2, "unavailable": 2, "unknown": 1}


def test_verification_sweep_stops_between_batches_when_asked():
    rows = [{"exercise_key": f"k{i}", "video_id": f"{i:011d}", "status": "ok"} for i in range(120)]
    requests: list[httpx.Request] = []
    updates: list[str] = []
    checks = {"n": 0}

    class Store:
        def list_exercise_media_for_verification(self):
            return rows

        def update_exercise_media_status(self, key, **fields):
            updates.append(key)

    def should_stop():
        checks["n"] += 1
        return checks["n"] > 1  # shutdown requested after the first batch

    counts = media.run_media_verification_sweep(
        Store(),
        api_key=API_KEY,
        client=_data_api({r["video_id"]: _video(r["video_id"]) for r in rows}, requests=requests),
        should_stop=should_stop,
    )

    assert len(requests) == 1
    assert len(updates) == 50
    assert counts["ok"] == 50


def test_worker_runs_the_first_media_sweep_on_start(monkeypatch):
    import asyncio

    from api import worker

    calls: list[object] = []
    monkeypatch.setattr(media, "run_media_verification_sweep", lambda store, **kw: calls.append(kw))
    monkeypatch.setattr(worker, "_MEDIA_SWEEP_TASK", {"task": None})
    # An interval longer than any host's uptime stands in for a freshly
    # booted host, whose monotonic clock is still below the interval.
    interval = 10**12

    async def run():
        state: dict[str, float] = {}
        event = asyncio.Event()
        await worker._run_exercise_media_sweep_if_due(
            store=object(), state=state, interval_seconds=interval, shutdown_event=event
        )
        await worker._MEDIA_SWEEP_TASK["task"]
        # Not due again until the interval has passed.
        await worker._run_exercise_media_sweep_if_due(
            store=object(), state=state, interval_seconds=interval, shutdown_event=event
        )
        return event

    event = asyncio.run(run())
    assert len(calls) == 1
    assert calls[0]["should_stop"] == event.is_set


def test_store_pages_through_every_media_row():
    from api.store import SupabaseAppStore

    table_rows = [{"exercise_key": f"k{i:04d}", "status": "ok"} for i in range(2500)]
    ranges: list[tuple[int, int]] = []

    class Query:
        def __init__(self):
            self.window = (0, 0)

        def select(self, _columns):
            return self

        def eq(self, *_args):
            return self

        def order(self, column):
            assert column == "exercise_key"
            return self

        def range(self, start, end):
            ranges.append((start, end))
            self.window = (start, end)
            return self

        def execute(self):
            start, end = self.window
            return SimpleNamespace(data=table_rows[start : end + 1])

    store = SupabaseAppStore.__new__(SupabaseAppStore)
    store.client = SimpleNamespace(table=lambda _name: Query())
    store._run_with_transient_retry = lambda *, operation, fn: fn()

    rows = store.list_exercise_media_for_verification()

    assert len(rows) == 2500
    assert ranges == [(0, 999), (1000, 1999), (2000, 2999)]


def test_verification_sweep_needs_an_api_key(monkeypatch):
    monkeypatch.delenv(media.YOUTUBE_API_KEY_ENV, raising=False)

    class Store:
        def list_exercise_media_for_verification(self):
            raise AssertionError("must not run without a key")

    assert media.run_media_verification_sweep(Store()) == {"ok": 0, "unavailable": 0, "unknown": 0}


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
    # Each variant keeps its own key; `family` only groups them for the curator.
    assert [(row["exercise_key"], row["family"], row["occurrences"]) for row in rows] == [
        ("pallof-press", "pallof-press", 2),
        ("sled-push", "sled-push", 1),
        ("sled-push-light", "sled-push", 1),
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
    assert payload["aliases"] == ["barbell-rdl", "rdl", "romanian-deadlift-rdl"]

    assert media_tool.parse_import_row({"exercise_key": "x", "youtube_url": ""}) == (None, None)
    assert media_tool.parse_import_row({"exercise_key": "x", "youtube_url": "https://vimeo.com/1"})[1]
    assert media_tool.parse_import_row(
        {"exercise_key": "x", "youtube_url": "dQw4w9WgXcQ", "start_s": "30", "end_s": "10"}
    )[1]
    assert media_tool.parse_import_row({"exercise_key": "x" * 121, "youtube_url": "dQw4w9WgXcQ"})[1]


def _write_import_csv(tmp_path, rows):
    path = tmp_path / "media.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = media_tool.csv.DictWriter(handle, fieldnames=media_tool.CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in media_tool.CSV_COLUMNS})
    return path


def test_import_refuses_to_run_without_an_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv(media.YOUTUBE_API_KEY_ENV, raising=False)
    path = _write_import_csv(tmp_path, [{"exercise_key": "pallof-press", "youtube_url": "dQw4w9WgXcQ"}])
    with pytest.raises(SystemExit) as exc:
        media_tool.main(["import", str(path), "--dry-run"])
    assert exc.value.code == 2


def test_import_rejects_a_csv_without_the_required_columns(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(media.YOUTUBE_API_KEY_ENV, API_KEY)
    path = tmp_path / "media.csv"
    path.write_text("exercise_key,youtube_link\npallof-press,dQw4w9WgXcQ\n", encoding="utf-8")

    assert media_tool.main(["import", str(path), "--dry-run"]) == 2
    assert "needs a youtube_url column" in capsys.readouterr().err


def test_operational_failures_exit_2_not_1(tmp_path, capsys):
    assert media_tool.main(["import", str(tmp_path / "missing.csv"), "--dry-run"]) == 2
    assert "FileNotFoundError" in capsys.readouterr().err


def test_import_rejects_names_another_row_already_owns(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(media.YOUTUBE_API_KEY_ENV, API_KEY)
    ok = media.VideoCheck(status="ok", made_for_kids=False)
    monkeypatch.setattr(media_tool, "check_youtube_videos", lambda ids, **_: {i: ok for i in ids})
    upserts: list[dict] = []

    class Store:
        def list_exercise_media_for_verification(self):
            return [{"exercise_key": "romanian-deadlift-rdl", "aliases": ["rdl"], "status": "ok"}]

        def upsert_exercise_media(self, row):
            upserts.append(row)

    monkeypatch.setattr(media_tool, "_build_store", lambda: Store())
    path = _write_import_csv(
        tmp_path,
        [
            # Takes an alias another stored row owns.
            {"exercise_key": "barbell-rdl", "youtube_url": "AAAAAAAAAAA", "aliases": "RDL"},
            # Its key is another stored row's alias.
            {"exercise_key": "rdl", "youtube_url": "BBBBBBBBBBB"},
            # Re-import of the stored row under its own key: allowed.
            {"exercise_key": "romanian-deadlift-rdl", "youtube_url": "CCCCCCCCCCC", "aliases": "RDL"},
            # Two new rows in the same CSV claiming one alias: the second loses.
            {"exercise_key": "sled-push", "youtube_url": "DDDDDDDDDDD", "aliases": "Sled Push - light"},
            {"exercise_key": "sled-push-heavy", "youtube_url": "EEEEEEEEEEE", "aliases": "Sled Push - light"},
        ],
    )

    assert media_tool.main(["import", str(path)]) == 1

    out = capsys.readouterr().out
    assert "line 2: rejected - rdl already belongs to romanian-deadlift-rdl" in out
    assert "line 3: rejected - rdl already belongs to romanian-deadlift-rdl" in out
    assert "line 6: rejected - sled-push-light already belongs to sled-push" in out
    assert [row["exercise_key"] for row in upserts] == ["romanian-deadlift-rdl", "sled-push"]


def test_import_rejects_made_for_kids_videos(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(media.YOUTUBE_API_KEY_ENV, API_KEY)
    checks = {
        "AAAAAAAAAAA": media.VideoCheck(status="ok", made_for_kids=False, title="Pallof", channel_title="C"),
        "BBBBBBBBBBB": media.VideoCheck(status="unavailable", reason="made for kids", made_for_kids=True),
    }
    monkeypatch.setattr(media_tool, "check_youtube_videos", lambda ids, **_: {i: checks[i] for i in ids})
    path = _write_import_csv(
        tmp_path,
        [
            {"exercise_key": "pallof-press", "youtube_url": "AAAAAAAAAAA"},
            {"exercise_key": "box-jump", "youtube_url": "BBBBBBBBBBB"},
        ],
    )

    assert media_tool.main(["import", str(path), "--dry-run"]) == 1

    out = capsys.readouterr().out
    assert "pallof-press -> AAAAAAAAAAA" in out
    assert "box-jump rejected - made for kids" in out


# -- plan read ---------------------------------------------------------------


def test_plan_read_serves_media_for_matching_blocks_only():
    client, store, _ = _build_client()
    store.ensure_profile(
        AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari", metadata={})
    )
    store.list_exercise_media = lambda: [
        _row("back-squat", aliases=["Barbell Back Squat"], source="coach", channel_title="UNLXCK")
    ]
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
            "channel_title": "UNLXCK",
        }
    }
