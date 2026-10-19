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


def row(*, stage="Replied", sent="0", synced=None, copied="old DM", formula="next DM",
        contacted="2026-10-13", last_sent=None, first=None, second=None, safe_due=None,
        timing=""):
    def event(value):
        return {"date": {"start": value} if value else None}

    return {
        "id": "sample",
        "properties": {
            "Stage (AI Fills First)": {"select": {"name": stage}},
            "Follow-Ups Sent": {"select": {"name": sent} if sent else None},
            "Synced Follow-Ups Sent": {"number": synced},
            "Follow-Up DM": {"formula": {"type": "string", "string": formula}},
            "Copy Follow-Up": {"rich_text": [{"plain_text": copied}]},
            "Date Contacted": event(contacted),
            "Last Follow-Up Sent": event(last_sent),
            "Follow-Up 1 Sent At": event(first),
            "Follow-Up 2 Sent At": event(second),
            "Safe Next Due": event(safe_due),
            "Follow-Up Timing": {"rich_text": [{"plain_text": timing}] if timing else []},
        },
    }


def get_copy(changed):
    return changed["Copy Follow-Up"]["rich_text"][0]["text"]["content"]


def test_old_baseline_requires_manual_first_send_date():
    changed = sync.get_changes(row(stage="Contacted", sent="1"), date(2026, 10, 19))
    assert changed["Synced Follow-Ups Sent"] == {"number": 1}
    assert get_copy(changed) == sync.MISSING_SEND_DATE
    assert changed["Follow-Up Timing"]["rich_text"][0]["text"]["content"] == "Needs first send date"
    assert "Follow-Up 1 Sent At" not in changed
    assert "Last Follow-Up Sent" not in changed
    assert sync.missing_send_date(row(stage="Contacted", sent="1")["properties"])


def test_first_dropdown_send_records_observation_not_legacy_guess():
    observed = datetime.fromisoformat("2026-10-19T20:01:45+01:00")
    changed = sync.get_changes(row(stage="Contacted", sent="1", synced=0), observed)
    stamp = "2026-10-19T20:01:45+01:00"
    assert changed["Follow-Up 1 Sent At"] == {"date": {"start": stamp}}
    assert changed["Last Follow-Up Sent"] == {"date": {"start": stamp}}
    assert changed["Safe Next Due"] == {"date": {"start": "2026-10-24T20:01:45+01:00"}}
    assert "WAIT" in get_copy(changed)


def test_verified_native_button_first_timestamp_survives_poll():
    changed = sync.get_changes(
        row(stage="Contacted", sent="1", synced=0,
            first="2026-10-19T19:59:00+01:00", last_sent="2026-10-19T19:59:00+01:00"),
        datetime.fromisoformat("2026-10-19T20:01:45+01:00"),
    )
    assert "Follow-Up 1 Sent At" not in changed
    assert "Last Follow-Up Sent" not in changed
    assert changed["Synced Follow-Ups Sent"] == {"number": 1}
    assert changed["Safe Next Due"]["date"]["start"] == "2026-10-24T19:59:00+01:00"


def test_legacy_first_date_backfills_without_inventing_new_date():
    changed = sync.get_changes(
        row(stage="Contacted", sent="1", synced=1, last_sent="2026-10-16"),
        date(2026, 10, 19),
    )
    assert changed["Follow-Up 1 Sent At"] == {"date": {"start": "2026-10-16"}}
    assert changed["Safe Next Due"] == {"date": {"start": "2026-10-22T00:00:00+01:00"}}
    assert "Last Follow-Up Sent" not in changed


def test_date_only_history_waits_through_full_fifth_day():
    page = row(stage="Contacted", sent="1", synced=1, first="2026-10-16")
    due, status, message = sync.due_and_copy(
        page["properties"], 1, "2026-10-16", None,
        datetime.fromisoformat("2026-10-21T17:00:00+01:00"), "second follow-up text")
    assert due == "2026-10-22T00:00:00+01:00"
    assert status == "Follow-up 2: waiting"
    assert message.startswith("WAIT")


def test_elapsed_gap_is_120_hours_through_spring_dst_change():
    page = row(stage="Contacted", sent="1", synced=1,
               contacted="2027-03-20", first="2027-03-26T20:00:00+00:00")
    due, _, _ = sync.due_and_copy(
        page["properties"], 1, "2027-03-26T20:00:00+00:00", None,
        datetime.fromisoformat("2027-03-31T20:30:00+01:00"), "second DM")
    assert due == "2027-03-31T21:00:00+01:00"


def test_full_five_day_gap_recomputed_on_repeated_poll():
    instant = datetime.fromisoformat("2026-10-19T18:00:00+01:00")
    prior_due = "2026-10-24T18:00:00+01:00"
    page = row(stage="Contacted", sent="1", synced=1, first=instant.isoformat(),
               copied="WAIT: next follow-up is due 24 Oct 2026, 18:00 BST.",
               safe_due=prior_due, timing="Follow-up 2: waiting")
    assert sync.get_changes(page, datetime.fromisoformat("2026-10-20T18:00:00+01:00")) == {}


def test_first_due_date_and_early_copy_are_consistent():
    page = row(stage="Contacted", sent="0", synced=0)
    due, status, message = sync.due_and_copy(
        page["properties"], 0, None, None,
        datetime.fromisoformat("2026-10-15T12:00:00+01:00"), "follow-up 1 text")
    assert due == "2026-10-16T00:00:00+01:00"
    assert status == "Follow-up 1: waiting"
    assert "follow-up 1 text" not in message


def test_second_due_respects_day_eight_and_five_days():
    page = row(stage="Contacted", sent="1", synced=1, first="2026-10-14T09:00:00+01:00")
    due, status, message = sync.due_and_copy(
        page["properties"], 1, "2026-10-14T09:00:00+01:00", None,
        datetime.fromisoformat("2026-10-20T11:00:00+01:00"), "second DM")
    assert due == "2026-10-21T00:00:00+01:00"  # Day 8 wins over 5-day gap.
    assert status.endswith("waiting")
    assert message.startswith("WAIT")


def test_ready_followup_displays_message_at_eligibility():
    page = row(stage="Contacted", sent="1", synced=1, first="2026-10-19T20:00:00+01:00")
    due, status, message = sync.due_and_copy(
        page["properties"], 1, "2026-10-19T20:00:00+01:00", None,
        datetime.fromisoformat("2026-10-24T20:00:00+01:00"), "second DM")
    assert due == "2026-10-24T20:00:00+01:00"
    assert status == "Follow-up 2: ready"
    assert message == "second DM"


def test_second_dropdown_send_preserves_first_and_records_second():
    page = row(stage="Contacted", sent="2", synced=1, first="2026-10-17T10:00:00+01:00",
               last_sent="2026-10-17T10:00:00+01:00", formula="")
    changed = sync.get_changes(page, datetime.fromisoformat("2026-10-24T18:01:00+01:00"))
    assert "Follow-Up 1 Sent At" not in changed
    assert changed["Follow-Up 2 Sent At"] == {"date": {"start": "2026-10-24T18:01:00+01:00"}}
    assert changed["Last Follow-Up Sent"] == {"date": {"start": "2026-10-24T18:01:00+01:00"}}
    assert changed["Copy Follow-Up"] == {"rich_text": []}


def test_second_button_timestamp_is_not_overwritten():
    page = row(stage="Contacted", sent="2", synced=1,
               first="2026-10-17T10:00:00+01:00",
               second="2026-10-24T17:59:50+01:00", last_sent="2026-10-24T17:59:50+01:00")
    page["last_edited_time"] = "2026-10-24T16:59:50Z"
    changed = sync.get_changes(page, datetime.fromisoformat("2026-10-24T18:01:00+01:00"))
    assert "Follow-Up 2 Sent At" not in changed
    assert "Last Follow-Up Sent" not in changed


def test_counter_reversal_keeps_history_and_blocks_copy():
    page = row(stage="Contacted", sent="1", synced=2,
               first="2026-10-19", second="2026-10-24", last_sent="2026-10-24")
    changed = sync.get_changes(page, date(2026, 10, 25))
    assert "Follow-Up 1 Sent At" not in changed
    assert "Follow-Up 2 Sent At" not in changed
    assert "Last Follow-Up Sent" not in changed
    assert "count" in get_copy(changed).lower()
    assert changed["Safe Next Due"] == {"date": None}


def test_missed_multiple_counter_increments_hold_for_review():
    changed = sync.get_changes(row(stage="Contacted", sent="2", synced=0), date(2026, 10, 25))
    assert "Follow-Up 1 Sent At" not in changed
    assert "Follow-Up 2 Sent At" not in changed
    assert changed["Follow-Up Timing"]["rich_text"][0]["text"]["content"] == "Needs count review"


def test_missing_contact_date_blocks_copy():
    changed = sync.get_changes(
        row(stage="Contacted", sent="0", synced=0, contacted=None), date(2026, 10, 19))
    assert get_copy(changed) == sync.MISSING_CONTACT_DATE


def test_replied_stage_preserves_reply_template():
    changed = sync.get_changes(row(stage="Replied", sent="1", synced=1), date(2026, 10, 19))
    assert get_copy(changed) == "next DM"


def test_idempotent_no_change_when_fields_synced():
    page = row(stage="Replied", sent="1", synced=1, copied="next DM", timing="Not in follow-up queue")
    assert sync.get_changes(page, date(2026, 10, 19)) == {}



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
        # Initial baselines have no milestone dates; Inactive keeps previous milestones.
        past = {"date": {"start": "2026-10-17"}} if stage == "Inactive" else {"date": None}
        return {"properties": {
            "Stage (AI Fills First)": {"select": {"name": stage}},
            "First Reply Confirmed At": past,
            "Accepted At": past,
            "Registered At": {"date": None},
            "First Meaningful Action At": {"date": None},
        }}
    monkeypatch.setenv("UNLXCK_APP_EVENTS_VERIFIED", "0")  # Must not gate CRM activation.
    monkeypatch.setattr(sync, "scorecard_rows", lambda: iter(
        [item("Contacted")] * 47 + [item("Rejected")] + [item("Replied")] * 11
        + [item("Accepted")] * 2 + [item("Activated")] * 2 + [item("Inactive")]
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
            block("count-" + str(i), "paragraph",
                  "Awaiting verified app-event integration" if i == 2 else "0 of 0 fighters"),
        ]

    monkeypatch.setattr(sync, "SCORECARD_PAGE_ID", "page")
    monkeypatch.setattr(sync, "block_children", lambda identifier: iter(tree[identifier]))
    writes = []
    monkeypatch.setattr(sync, "request", lambda method, path, body=None: writes.append((method, path, body)))
    assert sync.sync_scorecard() == (64, 6)
    assert len(writes) == 6
    assert all(method == "PATCH" and path.startswith("/blocks/") for method, path, _ in writes)
    data = {path: body for _, path, body in writes}
    assert data["/blocks/headline-0"]["heading_2"]["rich_text"][0]["text"]["content"] == "26.6%"
    assert data["/blocks/headline-1"]["heading_2"]["rich_text"][0]["text"]["content"] == "7.8%"
    assert data["/blocks/headline-2"]["heading_2"]["rich_text"][0]["text"]["content"] == "3.1%"
    assert data["/blocks/count-0"]["paragraph"]["rich_text"][0]["text"]["content"] == "17 of 64 fighters"
    assert data["/blocks/count-1"]["paragraph"]["rich_text"][0]["text"]["content"] == "5 of 64 fighters"
    assert data["/blocks/count-2"]["paragraph"]["rich_text"][0]["text"]["content"] == "2 of 64 fighters"
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
        "Date Contacted": {"date": {"start": "2026-10-17"}},
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
    assert change["First Reply Confirmed At"]["date"]["start"] == now.isoformat(timespec="seconds")
    assert change["Accepted At"]["date"]["start"] == now.isoformat(timespec="seconds")
    assert "Interested At" not in change
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


def test_scorecard_with_pending_stage_still_validates_cards(monkeypatch):
    monkeypatch.setattr(sync, "scorecard_rows", lambda: iter([
        observed_row(stage="Replied", observed="Replied",
                     since="2026-10-18T16:59:00+00:00", confirmed="")
    ]))
    monkeypatch.setattr(sync, "SCORECARD_PAGE_ID", "page")
    monkeypatch.setattr(sync, "block_children", lambda *_: iter([]))
    with pytest.raises(ValueError, match="Missing scorecard cards"):
        sync.sync_scorecard()


def test_recent_external_edit_blocks_confirmation():
    now = datetime(2026, 10, 18, 17, tzinfo=timezone.utc)
    page = observed_row(stage="Rejected", observed="Rejected", confirmed="Contacted",
                        since=(now - timedelta(minutes=8)).isoformat())
    page["last_edited_time"] = (now - timedelta(minutes=2)).isoformat()
    assert sync.stage_changes(page, now) == {}


def test_initial_baseline_records_observation_time_milestones():
    now = datetime(2026, 10, 18, 17, tzinfo=timezone.utc)
    page = observed_row(stage="Accepted", observed="Accepted", confirmed="",
                        since=(now - timedelta(minutes=7)).isoformat())
    changes = sync.stage_changes(page, now)
    assert "Confirmed Stage" in changes
    assert changes["First Reply Confirmed At"]["date"]["start"] == now.isoformat(timespec="seconds")
    assert changes["Accepted At"]["date"]["start"] == now.isoformat(timespec="seconds")


@pytest.mark.parametrize("stage,accepted", [("Replied", False), ("Accepted", True),
                                           ("Activated", True)])
def test_baseline_captures_existing_crm_evidence_not_original_dm_time(stage, accepted):
    now = datetime(2026, 10, 18, 17, tzinfo=timezone.utc)
    page = observed_row(stage=stage, observed=stage, confirmed="",
                        since=(now - timedelta(minutes=7)).isoformat())
    changes = sync.stage_changes(page, now)
    assert changes["First Reply Confirmed At"]["date"]["start"] == now.isoformat(timespec="seconds")
    assert ("Accepted At" in changes) == accepted
    assert "baseline ->" in changes["Stage History"]["rich_text"][0]["text"]["content"]
    assert "Registered At" not in changes
    assert "First Meaningful Action At" not in changes


def test_repairs_previously_confirmed_baseline_without_overwriting_history():
    now = datetime(2026, 10, 18, 17, tzinfo=timezone.utc)
    page = observed_row(stage="Activated", observed="Activated", confirmed="Activated",
                        since=(now - timedelta(minutes=7)).isoformat())
    changes = sync.stage_changes(page, now)
    assert set(changes) == {"First Reply Confirmed At", "Accepted At"}
    page["properties"]["First Reply Confirmed At"] = changes["First Reply Confirmed At"]
    page["properties"]["Accepted At"] = changes["Accepted At"]
    assert sync.stage_changes(page, now) == {}


def test_initial_rejection_is_not_automatically_treated_as_reply():
    now = datetime(2026, 10, 18, 17, tzinfo=timezone.utc)
    page = observed_row(stage="Rejected", observed="Rejected", confirmed="",
                        since=(now - timedelta(minutes=7)).isoformat())
    changes = sync.stage_changes(page, now)
    assert "Confirmed Stage" in changes
    assert "First Reply Confirmed At" not in changes
    assert "Rejected At" not in changes


def test_stage_history_queries_entire_pipeline(monkeypatch):
    pages = [observed_row(stage="Inactive", observed="Inactive", confirmed="Inactive",
                          since="2026-10-18T16:00:00+00:00")]
    monkeypatch.setattr(sync, "all_pipeline_rows", lambda: iter(pages))
    monkeypatch.setattr(sync, "request", lambda *_: pytest.fail("No changes expected"))
    assert sync.sync_stage_history() == (1, 0)


def test_accepted_transition_is_reply_but_not_automatically_interested():
    now = datetime(2026, 10, 18, 17, tzinfo=timezone.utc)
    page = observed_row(stage="Accepted", observed="Accepted", confirmed="Replied",
                        since=(now - timedelta(minutes=7)).isoformat())
    page["properties"]["Date Contacted"] = {"date": {"start": "2026-10-17"}}
    changes = sync.stage_changes(page, now)
    assert "First Reply Confirmed At" in changes
    assert "Accepted At" in changes
    assert "Interested At" not in changes


def test_uncontacted_rejection_does_not_count_as_reply():
    now = datetime(2026, 10, 18, 17, tzinfo=timezone.utc)
    page = observed_row(stage="Rejected", observed="Rejected", confirmed="Contacted",
                        since=(now - timedelta(minutes=7)).isoformat())
    page["properties"]["Date Contacted"] = {"date": None}
    changes = sync.stage_changes(page, now)
    assert "Confirmed Stage" in changes
    assert "First Reply Confirmed At" not in changes
