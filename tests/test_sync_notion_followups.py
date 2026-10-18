"""Minimal regression tests for the scheduled Notion sync."""

import importlib.util
from datetime import date, datetime, timedelta, timezone
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


def test_reuses_existing_qualification_worker_token_names(monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_API_KEY", raising=False)
    monkeypatch.delenv("NOTION_INTEGRATION_TOKEN", raising=False)
    assert sync.notion_token() is None
    monkeypatch.setenv("NOTION_API_KEY", "existing-qualification-token")
    assert sync.notion_token() == "existing-qualification-token"
    monkeypatch.setenv("NOTION_TOKEN", "explicit-token")
    assert sync.notion_token() == "explicit-token"


def test_scorecard_rows_include_all_contacted_stages_and_skip_counters(monkeypatch):
    calls = []
    def fake_request(method, path, body=None):
        calls.append(body)
        def item(stage, source=""):
            return {"properties": {
                "Stage (AI Fills First)": {"select": {"name": stage}},
                "Source Detail": {"rich_text": [{"plain_text": source}] if source else []},
            }}
        if len(calls) == 1:
            return {"results": [item("Contacted"), item("Rejected", "SYSTEM_COUNTER")],
                    "has_more": True, "next_cursor": "page-2"}
        return {"results": [item("Inactive"), item("Activated")], "has_more": False}
    monkeypatch.setattr(sync, "request", fake_request)
    rows = list(sync.scorecard_rows())
    assert [r["properties"]["Stage (AI Fills First)"]["select"]["name"] for r in rows] == [
        "Contacted", "Inactive", "Activated",
    ]
    assert calls[0]["filter"] == {"property": "Date Contacted",
                                  "date": {"is_not_empty": True}}
    assert calls[1]["start_cursor"] == "page-2"


def test_scorecard_updates_three_rates_without_touching_other_blocks(monkeypatch):
    def item(stage):
        confirmed = {"rich_text": [{"plain_text": stage}]}
        reply = {"date": {"start": "2026-10-17"}} if stage != "Contacted" else {"date": None}
        accepted = {"date": {"start": "2026-10-17"}} if stage == "Accepted" else {"date": None}
        return {"properties": {
            "Stage (AI Fills First)": {"select": {"name": stage}},
            "Confirmed Stage": confirmed,
            "First Reply Confirmed At": reply,
            "Accepted At": accepted,
            "Registered At": {"date": None},
            "First Meaningful Action At": {"date": None},
        }}
    monkeypatch.delenv("UNLXCK_APP_EVENTS_VERIFIED", raising=False)
    monkeypatch.setattr(sync, "scorecard_rows", lambda: iter(
        [item("Contacted")] * 48 + [item("Replied")] * 11 + [item("Accepted")] * 2
    ))

    def block(identifier, kind, value="", children=False):
        return {"id": identifier, "type": kind, "has_children": children,
                kind: {"rich_text": [{"plain_text": value}]}}
    tree = {"page": [block("columns", "column_list", children=True)],
            "columns": [block("column-" + str(i), "column", children=True) for i in range(3)]}
    labels = ["REPLY RATE", "ACCEPT RATE", "ACTIVATION RATE"]
    for i, label in enumerate(labels):
        tree["column-" + str(i)] = [block("card-" + str(i), "callout", children=True)]
        tree["card-" + str(i)] = [
            block("headline-" + str(i), "heading_2", "0%"),
            block("label-" + str(i), "paragraph", label),
            block("count-" + str(i), "paragraph", "0 of 0 fighters"),
        ]

    monkeypatch.setattr(sync, "SCORECARD_PAGE_ID", "page")
    monkeypatch.setattr(sync, "block_children", lambda identifier: iter(tree[identifier]))
    writes = []
    monkeypatch.setattr(sync, "request", lambda method, path, body=None: writes.append((method, path, body)))
    assert sync.sync_scorecard() == (61, 5)
    assert len(writes) == 5
    assert all(method == "PATCH" and path.startswith("/blocks/") for method, path, _ in writes)
    data = {path: body for _, path, body in writes}
    assert data["/blocks/headline-0"]["heading_2"]["rich_text"][0]["text"]["content"] == "21.3%"
    assert data["/blocks/headline-1"]["heading_2"]["rich_text"][0]["text"]["content"] == "3.3%"
    assert data["/blocks/count-2"]["paragraph"]["rich_text"][0]["text"]["content"] == "Awaiting verified app-event integration"
    assert "/blocks/label-0" not in data


def test_scorecard_fails_closed_when_card_missing(monkeypatch):
    monkeypatch.setattr(sync, "scorecard_rows", lambda: iter([]))
    monkeypatch.setattr(sync, "SCORECARD_PAGE_ID", "page")
    monkeypatch.setattr(sync, "block_children", lambda identifier: iter([]))
    monkeypatch.setattr(sync, "request", lambda *_: pytest.fail("No writes if cards are missing"))
    with pytest.raises(ValueError, match="Missing scorecard cards"):
        sync.sync_scorecard()


def observed_row(stage="Rejected", observed="Contacted", since=None, confirmed="Contacted",
                 reply=None, history=""):
    def txt(value):
        return {"rich_text": [{"plain_text": value}] if value else []}
    return {"id": "sample", "properties": {
        "Stage (AI Fills First)": {"select": {"name": stage}},
        "Observed Stage": txt(observed),
        "Observed Since": {"date": {"start": since} if since else None},
        "Confirmed Stage": txt(confirmed),
        "Stage Confirmed At": {"date": None},
        "Stage History": txt(history),
        "First Reply Confirmed At": {"date": {"start": reply} if reply else None},
        "Interested At": {"date": None},
        "Accepted At": {"date": None},
        "Rejected At": {"date": None},
        "Registered At": {"date": None},
        "First Meaningful Action At": {"date": None},
    }}


def test_debounces_stage_and_remembers_rejection_as_reply():
    now = datetime(2026, 10, 18, 17, tzinfo=timezone.utc)
    initial = sync.stage_changes(observed_row(), now)
    assert initial["Observed Stage"]["rich_text"][0]["text"]["content"] == "Rejected"
    pending = observed_row(observed="Rejected", since=(now - timedelta(minutes=4)).isoformat())
    assert sync.stage_changes(pending, now) == {}
    stable = observed_row(observed="Rejected", since=(now - timedelta(minutes=6)).isoformat())
    change = sync.stage_changes(stable, now)
    assert "First Reply Confirmed At" in change
    assert "Rejected At" in change
    assert "Registered At" not in change
    assert "baseline" not in change["Stage History"]["rich_text"][0]["text"]["content"]


def test_first_seen_stage_does_not_fabricate_historical_transition_time():
    now = datetime(2026, 10, 18, 17, tzinfo=timezone.utc)
    baseline = observed_row(stage="Activated", observed="Activated",
                            confirmed="", since=(now - timedelta(minutes=6)).isoformat())
    change = sync.stage_changes(baseline, now)
    assert "baseline -> Activated" in change["Stage History"]["rich_text"][0]["text"]["content"]
    assert "Interested At" not in change and "Accepted At" not in change
    assert "Registered At" not in change and "First Meaningful Action At" not in change


def test_previous_reply_survives_later_inactive_stage():
    now = datetime(2026, 10, 18, 17, tzinfo=timezone.utc)
    page = observed_row(stage="Inactive", observed="Inactive", confirmed="Replied",
                        reply="2026-10-14T10:00:00+00:00",
                        since=(now - timedelta(minutes=6)).isoformat())
    change = sync.stage_changes(page, now)
    assert "First Reply Confirmed At" not in change
    assert "Confirmed Stage" in change
    assert "Stage History" in change


def test_scorecard_does_not_publish_unconfirmed_stage(monkeypatch):
    monkeypatch.setattr(sync, "scorecard_rows", lambda: iter([
        observed_row(stage="Replied", observed="Replied",
                     since="2026-10-18T16:59:00+00:00", confirmed="")
    ]))
    monkeypatch.setattr(sync, "request", lambda *_: pytest.fail("should not write before stage confirmation"))
    assert sync.sync_scorecard() == (1, 0)


def test_recent_external_edit_blocks_confirmation():
    now = datetime(2026, 10, 18, 17, tzinfo=timezone.utc)
    page = observed_row(stage="Rejected", observed="Rejected", confirmed="Contacted",
                        since=(now - timedelta(minutes=8)).isoformat())
    page["last_edited_time"] = (now - timedelta(minutes=2)).isoformat()
    assert sync.stage_changes(page, now) == {}


def test_initial_baseline_does_not_invent_reply_or_acceptance():
    now = datetime(2026, 10, 18, 17, tzinfo=timezone.utc)
    page = observed_row(stage="Accepted", observed="Accepted", confirmed="",
                        since=(now - timedelta(minutes=7)).isoformat())
    changes = sync.stage_changes(page, now)
    assert "Confirmed Stage" in changes
    assert "First Reply Confirmed At" not in changes
    assert "Accepted At" not in changes


def test_stage_history_queries_entire_pipeline(monkeypatch):
    pages = [observed_row(stage="Inactive", observed="Inactive", confirmed="Inactive",
                          since="2026-10-18T16:00:00+00:00")]
    monkeypatch.setattr(sync, "all_pipeline_rows", lambda: iter(pages))
    monkeypatch.setattr(sync, "request", lambda *_: pytest.fail("No changes expected"))
    assert sync.sync_stage_history() == (1, 0)
