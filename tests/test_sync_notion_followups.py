"""Minimal regression tests for the scheduled Notion sync."""

import importlib.util
from datetime import date
from io import BytesIO
from urllib.error import HTTPError

import pytest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools" / "sync_notion_followups.py"
spec = importlib.util.spec_from_file_location("sync_notion_followups", MODULE)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def row(*, stage="Replied", sent="0", synced=None, copied="old DM", formula="next DM"):
    return {
        "id": "sample",
        "properties": {
            "Stage (AI Fills First)": {"select": {"name": stage}},
            "Follow-Ups Sent": {"select": {"name": sent} if sent else None},
            "Synced Follow-Ups Sent": {"number": synced},
            "Follow-Up DM": {"formula": {"type": "string", "string": formula}},
            "Copy Follow-Up": {"rich_text": [{"plain_text": copied}]},
        },
    }


def test_first_run_syncs_text_without_inventing_old_send_date():
    changed = sync.get_changes(row(sent="1"), date(2026, 10, 16))
    assert changed["Synced Follow-Ups Sent"] == {"number": 1}
    assert changed["Copy Follow-Up"]["rich_text"][0]["text"]["content"] == "next DM"
    assert "Last Follow-Up Sent" not in changed


def test_increment_updates_text_and_true_send_date():
    changed = sync.get_changes(row(sent="1", synced=0), date(2026, 10, 16))
    assert changed["Last Follow-Up Sent"] == {"date": {"start": "2026-10-16"}}
    assert changed["Synced Follow-Ups Sent"] == {"number": 1}


def test_final_followup_removes_stale_copy():
    changed = sync.get_changes(row(sent="2", synced=1, formula=""), date(2026, 10, 16))
    assert changed["Copy Follow-Up"] == {"rich_text": []}
    assert changed["Synced Follow-Ups Sent"] == {"number": 2}


def test_no_changes_when_already_synced():
    assert sync.get_changes(row(sent="1", synced=1, copied="next DM"), date(2026, 10, 16)) == {}


def test_paginates_all_outreach_rows(monkeypatch):
    calls = []

    def fake_request(method, path, body=None):
        calls.append(body)
        return {"results": [row()], "has_more": len(calls) == 1, "next_cursor": "more" if len(calls) == 1 else None}

    monkeypatch.setattr(sync, "request", fake_request)
    assert len(list(sync.pages())) == 2
    assert "start_cursor" not in calls[0]
    assert calls[1]["start_cursor"] == "more"


def test_changed_stage_before_update_skips_write(monkeypatch):
    original = row(copied="old")
    newer = row(stage="Contacted", copied="old")
    actions = []

    def fake_request(method, path, body=None):
        actions.append(method)
        if method == "GET":
            return newer
        pytest.fail("Should not overwrite a lead after their stage changes")

    monkeypatch.setattr(sync, "pages", lambda: iter([original]))
    monkeypatch.setattr(sync, "request", fake_request)
    assert sync.sync(date(2026, 10, 16)) == (1, 0)
    assert actions == ["GET"]


def test_retries_rate_limit_529(monkeypatch):
    calls = []
    sleeps = []

    def fake_urlopen(req, timeout):
        calls.append(req)
        if len(calls) == 1:
            raise HTTPError(req.full_url, 529, "Overloaded", {"Retry-After": "1"}, None)
        return BytesIO(b'{"ok": true}')

    monkeypatch.setenv("NOTION_TOKEN", "fake-secret")
    monkeypatch.setattr(sync, "urlopen", fake_urlopen)
    monkeypatch.setattr(sync.time, "sleep", sleeps.append)
    monkeypatch.setattr(sync.random, "uniform", lambda *_: 0)
    assert sync.request("GET", "/pages/example") == {"ok": True}
    assert len(calls) == 2
    assert sleeps == [0.35, 1.0, 0.35]


def test_does_not_retry_failed_patch(monkeypatch):
    attempts = []

    def fail(req, timeout):
        attempts.append(req)
        raise HTTPError(req.full_url, 500, "Server failure", {}, None)

    monkeypatch.setenv("NOTION_TOKEN", "fake-secret")
    monkeypatch.setattr(sync, "urlopen", fail)
    monkeypatch.setattr(sync.time, "sleep", lambda _: None)
    with pytest.raises(HTTPError):
        sync.request("PATCH", "/pages/example", {"properties": {}})
    assert len(attempts) == 1
