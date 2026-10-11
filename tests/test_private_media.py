"""Focused private-media boundary checks; no live services or credentials."""

import copy
import json
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from api.services import private_media as service
from api.services.exercise_media import VideoCheck, youtube_duration_seconds, YOUTUBE_API_KEY_ENV
from api.store import SupabaseAppStore
from media_processor import process as processor
from tests.support import _build_client
from tools.private_media_worker import docker_command, isolated_run

AUTH = {"Authorization": "Bearer athlete-token"}
OTHER = {"Authorization": "Bearer admin-token"}
BASE = "/api/private-media"


@pytest.fixture
def api(monkeypatch):
    client, store, _ = _build_client()
    rows, assets = {}, {}
    store.claim_private_media_budget = lambda owner: None
    store.private_media_worker_healthy = lambda: True
    store.get_private_media = (
        lambda owner, key: rows.get(key)
        if rows.get(key, {}).get("athlete_id") == owner
        else None
    )
    store.get_private_video_asset = (
        lambda owner, key: assets.get(key)
        if assets.get(key, {}).get("athlete_id") == owner
        else None
    )
    store.get_private_media_for_asset = lambda owner, key: next(
        (
            m
            for m in rows.values()
            if m["athlete_id"] == owner and m.get("asset_id") == key
        ),
        None,
    )
    store.private_video_signed_url = MagicMock(
        return_value="https://storage.test/signed-rendition"
    )

    def create(owner, fields):
        row = {"id": str(uuid4()), "athlete_id": owner, **fields}
        rows[row["id"]] = row
        return row

    store.create_private_media = create
    monkeypatch.setenv(YOUTUBE_API_KEY_ENV, "test-key")
    monkeypatch.setattr(
        service,
        "check_youtube_video",
        lambda *a, **kw: VideoCheck(
            status="ok",
            duration_seconds=120,
            made_for_kids=False,
            channel_title="Coach",
        ),
    )
    return client, store, rows, assets


def clip():
    return {
        "url": "https://www.youtube.com/watch?v=abcdefghijk",
        "start_s": 20,
        "end_s": 50,
    }


def manual(media_id):
    return {
        "name": "My plan",
        "sessions": [
            {
                "id": str(uuid4()),
                "name": "Training",
                "exercises": [
                    {
                        "id": str(uuid4()),
                        "origin": "manual",
                        "name": "My drill",
                        "media_id": media_id,
                    },
                ],
            }
        ],
    }


def test_clip_and_plan_reopen_are_private_and_media_is_immutable(api):
    client, store, rows, _ = api
    generated = copy.deepcopy(store.plans)
    first = client.post(BASE + "/youtube", headers=AUTH, json=clip())
    assert first.status_code == 201, first.text
    media = first.json()
    assert (
        media["provider"] == "youtube"
        and media["video_id"] == "abcdefghijk"
        and media["asset_id"] is None
    )
    assert client.get(f"{BASE}/{media['id']}", headers=OTHER).status_code == 404
    assert (
        client.post(
            "/api/custom-plans", headers=OTHER, json=manual(media["id"])
        ).status_code
        == 404
    )
    body = manual(media["id"])
    saved = client.post("/api/custom-plans", headers=AUTH, json=body)
    assert saved.status_code == 201, saved.text
    assert (
        client.get(f"/api/custom-plans/{saved.json()['id']}", headers=AUTH).json()[
            "sessions"
        ][0]["exercises"][0]["media_id"]
        == media["id"]
    )
    legacy = copy.deepcopy(body)
    del legacy["sessions"][0]["exercises"][0]["media_id"]
    legacy_saved = client.put(f"/api/custom-plans/{saved.json()['id']}", headers=AUTH, json=legacy)
    assert legacy_saved.status_code == 200
    assert legacy_saved.json()["sessions"][0]["exercises"][0]["media_id"] == media["id"]
    second = client.post(
        BASE + "/youtube", headers=AUTH, json={**clip(), "start_s": 50, "end_s": 60}
    ).json()
    assert second["id"] != media["id"] and rows[media["id"]]["start_s"] == 20
    body["sessions"][0]["exercises"][0]["media_id"] = None
    edited = client.put(
        f"/api/custom-plans/{saved.json()['id']}", headers=AUTH, json=body
    )
    assert (
        edited.status_code == 200
        and edited.json()["sessions"][0]["exercises"][0]["media_id"] is None
    )
    assert store.plans == generated


@pytest.mark.parametrize(
    "patch",
    [
        {"end_s": 51},
        {"end_s": 20},
        {"start_s": -1},
        {"start_s": 0.5},
        {"start_s": True},
        {"start_s": "10"},
        {"url": "https://youtube.com.evil.test/watch?v=abcdefghijk"},
        {"url": "http://youtube.com/watch?v=abcdefghijk"},
        {"url": "javascript:alert(1)"},
        {"url": "https://evil.test/abcdefghijk"},
        {"url": '<iframe src="evil"></iframe>'},
        {"url": "https://user:secret@youtube.com/watch?v=abcdefghijk"},
        {"url": "https://youtube.com:bad/watch?v=abcdefghijk"},
        {"video_id": "forged"},
    ],
)
def test_invalid_links_and_segments_never_persist(api, patch):
    client, _, rows, _ = api
    assert (
        client.post(
            BASE + "/youtube", headers=AUTH, json={**clip(), **patch}
        ).status_code
        == 422
    )
    assert not rows


@pytest.mark.parametrize(
    "check,expected",
    [
        (VideoCheck(status="unknown"), 503),
        (VideoCheck(status="unavailable", duration_seconds=120), 422),
        (VideoCheck(status="ok", duration_seconds=40), 422),
        (VideoCheck(status="ok"), 503),
    ],
)
def test_youtube_verification_fails_closed(api, monkeypatch, check, expected):
    client, _, rows, _ = api
    monkeypatch.setattr(service, "check_youtube_video", lambda *a, **kw: check)
    assert (
        client.post(BASE + "/youtube", headers=AUTH, json=clip()).status_code
        == expected
    )
    assert not rows


def test_missing_key_worker_and_disabled_flag_never_grant_uploads(api, monkeypatch):
    client, store, _, _ = api
    body = {"size_bytes": 200, "content_type": "video/mp4"}
    monkeypatch.delenv("PRIVATE_VIDEO_UPLOADS_ENABLED", raising=False)
    assert client.post(BASE + "/uploads", headers=AUTH, json=body).status_code == 503
    monkeypatch.setenv("PRIVATE_VIDEO_UPLOADS_ENABLED", "true")
    store.private_media_worker_healthy = lambda: False
    assert (
        client.get(BASE + "/settings", headers=AUTH).json()["uploads_available"]
        is False
    )
    assert client.post(BASE + "/uploads", headers=AUTH, json=body).status_code == 503
    monkeypatch.delenv(YOUTUBE_API_KEY_ENV)
    assert client.post(BASE + "/youtube", headers=AUTH, json=clip()).status_code == 503


def test_unverified_and_cross_owner_assets_cannot_be_previewed_or_attached(api):
    client, store, rows, assets = api
    asset_id, media_id = str(uuid4()), str(uuid4())
    assets[asset_id] = {
        "id": asset_id,
        "athlete_id": "athlete-1",
        "status": "processing",
        "rendition_path": "safe/demo.mp4",
    }
    rows[media_id] = {
        "id": media_id,
        "athlete_id": "athlete-1",
        "provider": "uploaded",
        "asset_id": asset_id,
        "end_s": 10,
        "start_s": 0,
    }
    assert client.get(f"{BASE}/{media_id}", headers=AUTH).status_code == 409
    assert (
        client.post(
            "/api/custom-plans", headers=AUTH, json=manual(media_id)
        ).status_code
        == 409
    )
    assert client.get(f"{BASE}/uploads/{asset_id}", headers=OTHER).status_code == 404
    store.private_video_signed_url.assert_not_called()
    assets[asset_id]["status"] = "verified"
    assert (
        client.get(f"{BASE}/{media_id}", headers=AUTH).json()["url"]
        == "https://storage.test/signed-rendition"
    )
    store.private_video_signed_url.assert_called_once_with(
        "safe/demo.mp4", expires_in=60
    )


def test_invalid_sizes_mime_and_unauthenticated_calls(api):
    client, _, _, _ = api
    for body in (
        {"size_bytes": 20971521, "content_type": "video/mp4"},
        {"size_bytes": 0, "content_type": "video/mp4"},
        {"size_bytes": 5, "content_type": "text/html"},
    ):
        assert (
            client.post(BASE + "/uploads", headers=AUTH, json=body).status_code == 422
        )
    assert client.get(BASE + "/settings").status_code == 401
    assert client.post(BASE + "/youtube", json=clip()).status_code == 401
    assert (
        client.post(
            BASE + "/uploads", json={"size_bytes": 5, "content_type": "video/mp4"}
        ).status_code
        == 401
    )
    assert client.get(f"{BASE}/{uuid4()}").status_code == 401
    assert client.get(f"{BASE}/uploads/{uuid4()}").status_code == 401


def test_duration_parser():
    assert youtube_duration_seconds("PT1H2M3.5S") == 3723.5
    assert youtube_duration_seconds("PT30S") == 30
    assert youtube_duration_seconds("P1D") is None


@pytest.mark.parametrize(
    "method,args",
    [
        ("get_private_media", ("owner", "media")),
        ("get_private_video_asset", ("owner", "asset")),
        ("get_private_media_for_asset", ("owner", "asset")),
    ],
)
def test_store_reads_are_owner_scoped(method, args):
    client = MagicMock()
    query = client.table.return_value
    query.select.return_value = query.eq.return_value = query.limit.return_value = query
    query.execute.return_value = SimpleNamespace(data=[])
    getattr(SupabaseAppStore(client=client, admin_emails=set()), method)(*args)
    query.eq.assert_any_call("athlete_id", "owner")


def probe(duration=30, width=1280, height=720, codec="h264"):
    return {
        "format": {"format_name": "mov,mp4", "duration": str(duration)},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": codec,
                "width": width,
                "height": height,
            },
        ],
    }


@pytest.mark.parametrize(
    "metadata",
    [
        probe(30.01),
        probe(float("nan")),
        probe(0),
        probe(width=10000),
        probe(codec="mjpeg"),
        {
            **probe(),
            "streams": probe()["streams"]
            + [{"codec_type": "attachment", "codec_name": "ttf"}],
        },
    ],
)
def test_processor_rejects_invalid_duration_dimensions_codecs_and_streams(
    tmp_path, monkeypatch, metadata
):
    source = tmp_path / "source"
    source.write_bytes(b"\x00\x00\x00\x10ftypisom0000")
    monkeypatch.setattr(
        processor, "run", lambda *a, **kw: json.dumps(metadata).encode()
    )
    with pytest.raises(ValueError):
        processor.inspect_video(source)


def test_processor_rejects_disguised_content_and_malware_before_decode(
    tmp_path, monkeypatch
):
    source = tmp_path / "source"
    source.write_bytes(b"<html>bad</html>")
    with pytest.raises(ValueError):
        processor.inspect_video(source)
    monkeypatch.setattr(processor, "signatures_current", lambda: None)
    calls = []

    def malware(args, **kw):
        calls.append(args[0])
        raise ValueError("malware")

    monkeypatch.setattr(processor, "run", malware)
    with pytest.raises(ValueError):
        processor.process(source, tmp_path / "target")
    assert calls == ["clamscan"]


def test_docker_sandbox_digest_and_timeout_removal(monkeypatch):
    image = "sha256:" + "a" * 64
    command = docker_command(image, source="/input")
    for required in (
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--memory=3g",
        "--pids-limit=64",
    ):
        assert required in command
    with pytest.raises(ValueError):
        docker_command("latest")
    calls = []

    def run(args, **kw):
        calls.append(args)

    monkeypatch.setattr(
        "tools.private_media_worker.subprocess.Popen",
        MagicMock(side_effect=TimeoutError()),
    )
    monkeypatch.setattr("tools.private_media_worker.subprocess.run", run)
    with pytest.raises(TimeoutError):
        isolated_run(command)
    assert calls[0][:3] == ["docker", "rm", "-f"]
