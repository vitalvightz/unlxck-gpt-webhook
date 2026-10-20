"""Minimal regression tests for the scheduled Notion sync."""

import importlib.util
import copy
import json
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
            "Warm Next DM": {"formula": {"type": "string", "string": "WAIT: due 23 Oct 2026"}},
            "Copy Follow-Up": {"rich_text": [{"plain_text": copied}]},
            "Date Contacted": event(contacted),
            "Last Follow-Up Sent": event(last_sent),
            "Follow-Up 1 Sent At": event(first),
            "Follow-Up 2 Sent At": event(second),
            "Safe Next Due": event(safe_due),
            "Follow-Up Timing": {"rich_text": [{"plain_text": timing}] if timing else []},
            "Details Sent": {"checkbox": False},
            "Details Sent At": event(None),
            "Onboarding Sent": {"checkbox": False},
            "Onboarding Sent At": event(None),
            "Signup Nudges Sent": {"select": None},
            "Synced Signup Nudges Sent": {"number": 0},
            "Onboarding Nudges Sent": {"select": None},
            "Synced Onboarding Nudges Sent": {"number": 0},
            "Signup Nudge 1 At": event(None),
            "Onboarding Nudge 1 At": event(None),
            "Warm Last Nudge At": event(None),
            "Feedback Requested": {"checkbox": False},
            "Feedback Requested At": event(None),
            "Feedback Reminder Sent": {"checkbox": False},
            "Feedback Submitted": {"number": 0},
            "Onboarding Complete": {"checkbox": False},
            "Registered At": event(None),
            "Follow-Up Sync State": sync.rich(json.dumps({"version": 1, "flags": {"Details Sent": False, "Onboarding Sent": False, "Feedback Requested": False, "Feedback Reminder Sent": False}, "seconds": {}, "reviews": {}, "dates": {}}, sort_keys=True, separators=(",", ":"))),
        },
    }


def get_copy(changed):
    return "".join(x["text"]["content"] for x in changed["Copy Follow-Up"]["rich_text"])


NOW = datetime.fromisoformat("2026-10-20T20:00:00+01:00")
TEMPLATES = {**{key: f"Approved {key} DM" for key in sync.TEMPLATE_LABELS},
             **{f"{segment}{number}": f"Approved {segment} response {number} https://unlxck.com/signup"
                for segment in ("amateur", "professional") for number in range(1, 5)}}


def apply(page, changes):
    page["properties"].update(copy.deepcopy(changes))
    return page


def state_of(page):
    return json.loads(sync.plain(page["properties"], sync.SYNC_STATE))


def warm_row(stage="Replied", count="0", synced=0, root="2026-10-15T10:00:00+01:00", first=None):
    page = row(stage=stage, synced=0)
    prefix = "Signup" if stage == "Replied" else "Onboarding"
    flag = "Details Sent" if stage == "Replied" else "Onboarding Sent"
    p = page["properties"]
    p[flag]["checkbox"] = bool(root)
    p[flag + " At"] = sync.date_patch(root)
    p[prefix + " Nudges Sent"]["select"] = {"name": count}
    p["Synced " + prefix + " Nudges Sent"]["number"] = synced
    p[prefix + " Nudge 1 At"] = sync.date_patch(first)
    return page


def test_old_baseline_requires_manual_first_send_date():
    changed = sync.get_changes(row(stage="Contacted", sent="1"), date(2026, 10, 19))
    assert changed["Synced Follow-Ups Sent"] == {"number": 1}
    assert get_copy(changed) == ""
    assert "Needs Review" in sync.plain(changed, "Follow-Up Timing")
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
    assert get_copy(changed) == ""


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
               copied="",
               safe_due=prior_due, timing="Follow-up 2: waiting")
    assert sync.get_changes(page, datetime.fromisoformat("2026-10-20T18:00:00+01:00")) == {}


def test_equivalent_utc_and_local_date_representation_does_not_resync():
    assert sync.same_date_value("2026-10-24T18:00:00+01:00", "2026-10-24T17:00:00.000Z")
    page = row(stage="Contacted", sent="1", synced=1,
               first="2026-10-19T18:00:00+01:00",
               last_sent="2026-10-19T18:00:00+01:00",
               copied="",
               safe_due="2026-10-24T17:00:00.000Z",
               timing="Follow-up 2: waiting")
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


def test_early_second_send_is_visible_as_timing_review():
    page = row(stage="Contacted", sent="2", synced=2,
               first="2026-10-19T20:00:00+01:00",
               second="2026-10-22T19:00:00+01:00")
    changed = sync.get_changes(page, date(2026, 10, 25))
    assert changed["Follow-Up Timing"]["rich_text"][0]["text"]["content"] == "Needs Review: send timing"
    assert changed.get("Safe Next Due", {"date": None}) == {"date": None}
    assert changed["Copy Follow-Up"] == {"rich_text": []}


def test_two_sent_without_first_date_marks_incomplete_history():
    page = row(stage="Contacted", sent="2", synced=2,
               second="2026-10-24T20:00:00+01:00")
    changed = sync.get_changes(page, date(2026, 10, 25))
    assert changed["Follow-Up Timing"]["rich_text"][0]["text"]["content"] == (
        "Needs Review: send history incomplete")


def test_counter_reversal_keeps_history_and_blocks_copy():
    page = row(stage="Contacted", sent="1", synced=2,
               first="2026-10-19", second="2026-10-24", last_sent="2026-10-24")
    changed = sync.get_changes(page, date(2026, 10, 25))
    assert "Follow-Up 1 Sent At" not in changed
    assert "Follow-Up 2 Sent At" not in changed
    assert "Last Follow-Up Sent" not in changed
    assert get_copy(changed) == ""
    assert "Needs Review" in sync.plain(changed, "Follow-Up Timing")
    assert changed.get("Safe Next Due", {"date": None}) == {"date": None}


def test_missed_multiple_counter_increments_hold_for_review():
    changed = sync.get_changes(row(stage="Contacted", sent="2", synced=0), date(2026, 10, 25))
    assert "Follow-Up 1 Sent At" not in changed
    assert "Follow-Up 2 Sent At" not in changed
    assert changed["Follow-Up Timing"]["rich_text"][0]["text"]["content"] .startswith("Needs Review")


def test_missing_contact_date_blocks_copy():
    changed = sync.get_changes(
        row(stage="Contacted", sent="0", synced=0, contacted=None), date(2026, 10, 19))
    assert get_copy(changed) == ""
    assert "Needs Review" in sync.plain(changed, "Follow-Up Timing")


def test_replied_stage_copies_only_due_warm_messages():
    page = row(stage="Replied")
    p = page["properties"]
    p["Details Sent"]["checkbox"] = True
    p["Details Sent At"] = sync.date_patch("2026-10-15T10:00:00+01:00")
    p["Warm Next DM"]["formula"]["string"] = "WAIT: stale formula"
    changes = sync.get_changes(page, date(2026, 10, 19), {"signup1": "Updated approved wording"})
    assert get_copy(changes) == "Updated approved wording"


def test_idempotent_no_change_when_fields_synced():
    page = row(stage="Contacted", synced=0)
    now = date(2026, 10, 19)
    apply(page, sync.get_changes(page, now))
    assert sync.get_changes(page, now) == {}


def test_paginates_all_outreach_rows(monkeypatch):
    calls = []

    def fake_request(method, path, body=None):
        calls.append(body)
        return {"results": [row()], "has_more": len(calls) == 1, "next_cursor": "more" if len(calls) == 1 else None}

    monkeypatch.setattr(sync, "request", fake_request)
    monkeypatch.setattr(sync, "plain", lambda p, name: "")
    assert len(list(sync.pages())) == 2
    assert "start_cursor" not in calls[0]
    assert calls[1]["start_cursor"] == "more"


def test_changed_stage_during_final_read_skips_write(monkeypatch):
    page = row()
    latest = row(stage="Rejected")
    calls = []
    def fake_request(method, path, body=None):
        calls.append(method)
        assert method == "GET"
        return page if len(calls) == 1 else latest
    monkeypatch.setattr(sync, "pages", lambda: iter([page]))
    monkeypatch.setattr(sync, "request", fake_request)
    assert sync.sync(date(2026, 10, 16), templates={}) == (1, 0)
    assert calls == ["GET", "GET"]


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


# Stage changes are timestamped by stage_changes; warm events only require
# one operator checkbox/dropdown after the Instagram action, never a date field.
def test_warm_initial_poll_baselines_counters_without_inventing_send_dates():
    page = row(stage="Replied")
    page["properties"][sync.SYNC_STATE] = sync.rich("")
    page["properties"]["Synced Signup Nudges Sent"]["number"] = None
    page["properties"]["Synced Onboarding Nudges Sent"]["number"] = None
    changes = sync.get_warm_changes(page, datetime(2026, 10, 20, 20, tzinfo=timezone.utc))
    assert changes.pop(sync.SYNC_STATE)
    assert changes == {
        "Synced Signup Nudges Sent": {"number": 0},
        "Synced Onboarding Nudges Sent": {"number": 0},
    }


def test_ticking_details_sent_stamps_once_in_replied():
    page = row(stage="Replied")
    page["properties"]["Details Sent"]["checkbox"] = True
    now = datetime(2026, 10, 20, 20, 3, tzinfo=timezone.utc)
    changes = sync.get_warm_changes(page, now)
    assert changes["Details Sent At"]["date"]["start"] == now.astimezone(sync.LONDON).isoformat(timespec="seconds")
    page["properties"]["Details Sent At"] = changes["Details Sent At"]
    again = sync.get_warm_changes(page, now + timedelta(days=1))
    assert "Details Sent At" not in again


def test_accepted_onboarding_is_distinct_from_replied_details():
    page = row(stage="Accepted")
    page["properties"]["Details Sent"]["checkbox"] = True
    page["properties"]["Onboarding Sent"]["checkbox"] = True
    changed = sync.get_warm_changes(page, datetime(2026, 10, 20, 20, tzinfo=timezone.utc))
    assert "Onboarding Sent At" in changed
    assert "Details Sent At" in changed  # Explicit action survives rapid stage progression.


def test_activated_means_used_app_and_feedback_checkbox_stamps():
    page = row(stage="Activated")
    page["properties"]["Feedback Requested"]["checkbox"] = True
    changed = sync.get_warm_changes(page, datetime(2026, 10, 20, 20, tzinfo=timezone.utc))
    assert "Feedback Requested At" in changed
    assert "Details Sent At" not in changed


def test_signup_nudge_progression_stamps_first_and_last_automatically():
    page = row(stage="Replied")
    p = page["properties"]
    p["Synced Signup Nudges Sent"]["number"] = 0
    p["Synced Onboarding Nudges Sent"]["number"] = 0
    p["Details Sent"]["checkbox"] = True
    p["Details Sent At"] = sync.date_patch("2026-10-16T10:00:00+01:00")
    p["Signup Nudges Sent"]["select"] = {"name": "1"}
    now = datetime(2026, 10, 20, 20, tzinfo=timezone.utc)
    first = sync.get_warm_changes(page, now)
    assert first["Synced Signup Nudges Sent"] == {"number": 1}
    assert first["Signup Nudge 1 At"] == first["Warm Last Nudge At"]
    p["Synced Signup Nudges Sent"]["number"] = 1
    p["Signup Nudge 1 At"] = first["Signup Nudge 1 At"]
    p["Warm Last Nudge At"] = first["Warm Last Nudge At"]
    p["Signup Nudges Sent"]["select"] = {"name": "2"}
    last = sync.get_warm_changes(page, now + timedelta(days=4))
    assert last["Synced Signup Nudges Sent"] == {"number": 2}
    assert "Signup Nudge 1 At" not in last
    assert last["Warm Last Nudge At"]["date"]["start"] != first["Warm Last Nudge At"]["date"]["start"]


def test_onboarding_nudges_are_independent_of_previous_signup_counter():
    page = row(stage="Accepted")
    p = page["properties"]
    p["Signup Nudges Sent"]["select"] = {"name": "2"}
    p["Synced Signup Nudges Sent"]["number"] = 2
    p["Onboarding Sent"]["checkbox"] = True
    p["Onboarding Sent At"] = sync.date_patch("2026-10-16T10:00:00+01:00")
    p["Onboarding Nudges Sent"]["select"] = {"name": "1"}
    p["Synced Onboarding Nudges Sent"]["number"] = 0
    changes = sync.get_warm_changes(page, datetime(2026, 10, 20, 20, tzinfo=timezone.utc))
    assert changes["Synced Onboarding Nudges Sent"] == {"number": 1}
    assert "Onboarding Nudge 1 At" in changes
    assert "Synced Signup Nudges Sent" not in changes


def test_historical_warm_count_or_skipped_increment_never_fabricates_dates():
    page = row(stage="Replied")
    p = page["properties"]
    p["Signup Nudges Sent"]["select"] = {"name": "1"}
    p["Synced Signup Nudges Sent"]["number"] = None
    baseline = sync.get_warm_changes(page, datetime(2026, 10, 20, 20, tzinfo=timezone.utc))
    assert baseline["Synced Signup Nudges Sent"] == {"number": 1}
    assert "Warm Last Nudge At" not in baseline
    assert "Signup Nudge 1 At" not in baseline
    p["Synced Signup Nudges Sent"]["number"] = 0
    p["Signup Nudges Sent"]["select"] = {"name": "2"}
    missed = sync.get_warm_changes(page, datetime(2026, 10, 20, 20, tzinfo=timezone.utc))
    assert "Synced Signup Nudges Sent" not in missed
    assert "Replied" in json.loads(sync.plain(missed, sync.SYNC_STATE))["reviews"]
    assert "Warm Last Nudge At" not in missed
    assert "Signup Nudge 1 At" not in missed


def test_poll_writes_warm_timestamp_without_touching_cold_followup(monkeypatch):
    page = row(stage="Replied", copied="next DM", timing="Not in follow-up queue")
    p = page["properties"]
    p["Synced Signup Nudges Sent"]["number"] = 0
    p["Synced Onboarding Nudges Sent"]["number"] = 0
    p["Details Sent"]["checkbox"] = True
    writes = []
    def fake_request(method, path, body=None):
        if method == "GET":
            return page
        writes.append(body["properties"])
        return {}
    monkeypatch.setattr(sync, "pages", lambda: iter([page]))
    monkeypatch.setattr(sync, "request", fake_request)
    assert sync.sync(datetime(2026, 10, 20, 20, tzinfo=timezone.utc), templates={}) == (1, 1)
    assert "Details Sent At" in writes[0]
    assert "Follow-Ups Sent" not in writes[0]
    assert "Follow-Up 1 Sent At" not in writes[0]


@pytest.mark.parametrize("stage", ["Replied", "Accepted"])
def test_new_counter_send_and_retry_are_atomic_and_idempotent(stage):
    page = warm_row(stage, count="1")
    changes = sync.get_changes(page, NOW, TEMPLATES)
    prefix = "Signup" if stage == "Replied" else "Onboarding"
    assert changes[prefix + " Nudge 1 At"] == sync.date_patch(NOW.isoformat())
    assert changes["Safe Next Due"] == sync.date_patch("2026-10-24T20:00:00+01:00")
    assert get_copy(changes) == ""
    apply(page, changes)
    assert sync.get_changes(page, NOW + timedelta(minutes=2), TEMPLATES) == {}


@pytest.mark.parametrize("stage", ["Replied", "Accepted"])
@pytest.mark.parametrize("count,synced,first", [("2", 0, None), ("0", 1, None),
                                               ("1", 1, None), ("2", 2, None),
                                               ("0", 0, "2026-10-19T20:00:00+01:00")])
def test_invalid_warm_history_blocks_copy_and_remains_reviewed(stage, count, synced, first):
    page = warm_row(stage, count, synced, first=first)
    for _ in range(3):
        changes = sync.get_changes(page, NOW, TEMPLATES)
        apply(page, changes)
        assert sync.plain(page["properties"], "Follow-Up Timing").startswith("Needs Review")
        assert not sync.plain(page["properties"], "Copy Follow-Up")
        assert not sync.date_value(page["properties"], "Safe Next Due")
        if not first:
            assert not sync.date_value(page["properties"], "Signup Nudge 1 At" if stage == "Replied" else "Onboarding Nudge 1 At")


def test_historical_checkbox_on_first_poll_does_not_invent_timestamp():
    page = row()
    p = page["properties"]
    p[sync.SYNC_STATE] = sync.rich("")
    p["Details Sent"]["checkbox"] = True
    changes = sync.get_changes(page, NOW, TEMPLATES)
    assert "Details Sent At" not in changes
    assert "historic action" in sync.plain(changes, "Follow-Up Timing")
    assert get_copy(changes) == ""


@pytest.mark.parametrize("stage", ["Replied", "Accepted"])
def test_native_one_action_first_send_before_baseline_preserves_proven_time(stage):
    page = warm_row(stage, "1", None, first="2026-10-19T12:00:00+01:00")
    page["properties"][sync.SYNC_STATE] = sync.rich("")
    changes = sync.get_changes(page, NOW, TEMPLATES)
    field = "Signup Nudge 1 At" if stage == "Replied" else "Onboarding Nudge 1 At"
    assert field not in changes
    assert changes["Safe Next Due"] == sync.date_patch("2026-10-23T12:00:00+01:00")
    assert "Needs Review" not in sync.plain(changes, "Follow-Up Timing")


def test_first_poll_query_to_read_counter_race_is_recorded(monkeypatch):
    page = warm_row(synced=None)
    page["properties"][sync.SYNC_STATE] = sync.rich("")
    fresh = copy.deepcopy(page)
    fresh["properties"]["Signup Nudges Sent"]["select"] = {"name": "1"}
    writes = []
    def request(method, path, body=None):
        if method == "GET":
            return copy.deepcopy(fresh)
        writes.append(body["properties"])
    monkeypatch.setattr(sync, "pages", lambda: iter([page]))
    monkeypatch.setattr(sync, "request", request)
    assert sync.sync(NOW, TEMPLATES) == (1, 1)
    assert writes[0]["Signup Nudge 1 At"] == sync.date_patch(NOW.isoformat())
    assert writes[0]["Synced Signup Nudges Sent"] == {"number": 1}


def test_all_stage_baseline_survives_rapid_progression():
    page = row(stage="Ready to Send")
    p = page["properties"]
    p[sync.SYNC_STATE] = sync.rich("")
    p["Synced Signup Nudges Sent"]["number"] = None
    apply(page, sync.get_changes(page, NOW, TEMPLATES))
    assert p["Synced Signup Nudges Sent"]["number"] == 0
    p["Stage (AI Fills First)"]["select"] = {"name": "Accepted"}
    p["Details Sent"]["checkbox"] = True
    changes = sync.get_changes(page, NOW + timedelta(minutes=2), TEMPLATES)
    assert "Details Sent At" in changes
    assert "Onboarding Sent At" not in changes
    assert "Signup Nudge 1 At" not in changes


def test_record_nudge_even_if_stage_advanced_before_poll():
    page = warm_row(count="1")
    page["properties"]["Stage (AI Fills First)"]["select"] = {"name": "Accepted"}
    changes = sync.get_changes(page, NOW, TEMPLATES)
    assert changes["Signup Nudge 1 At"] == sync.date_patch(NOW.isoformat())
    assert "Onboarding Nudge 1 At" not in changes
    assert "Signup" not in sync.plain(changes, "Follow-Up Timing")


@pytest.mark.parametrize("root,days,expected", [
    ("2026-10-23T20:00:00+01:00", 3, "2026-10-26T19:00:00+00:00"),
    ("2027-03-26T20:00:00+00:00", 3, "2027-03-29T21:00:00+01:00"),
    ("2026-10-23T20:00:00+01:00", 4, "2026-10-27T19:00:00+00:00"),
    ("2027-03-26T20:00:00+00:00", 5, "2027-03-31T21:00:00+01:00"),
    ("2026-10-23", 3, "2026-10-27T00:00:00+00:00"),
])
def test_warm_elapsed_gaps_and_date_only_history_across_dst(root, days, expected):
    assert sync.elapsed_due(root, days).isoformat() == expected


@pytest.mark.parametrize("stage", ["Replied", "Accepted"])
def test_warm_final_is_four_days_after_actual_first_nudge(stage):
    page = warm_row(stage, "1", 1, first="2026-10-19T12:00:00+01:00")
    changes = sync.get_changes(page, NOW, TEMPLATES)
    assert changes["Safe Next Due"] == sync.date_patch("2026-10-23T12:00:00+01:00")
    apply(page, changes)
    changes = sync.get_changes(page, NOW + timedelta(days=10), TEMPLATES)
    assert get_copy(changes) == TEMPLATES["signup2" if stage == "Replied" else "onboarding2"]


def test_feedback_request_waits_four_days_then_reminder_five_days_and_stops():
    page = row(stage="Activated", synced=0)
    apply(page, sync.get_changes(page, NOW, TEMPLATES))
    assert sync.date_value(page["properties"], "Safe Next Due") == "2026-10-24T20:00:00+01:00"
    changes = sync.get_changes(page, NOW + timedelta(days=4), TEMPLATES)
    assert get_copy(changes) == TEMPLATES["feedback1"]
    apply(page, changes)
    page["properties"]["Feedback Requested"]["checkbox"] = True
    apply(page, sync.get_changes(page, NOW + timedelta(days=4), TEMPLATES))
    assert sync.date_value(page["properties"], "Safe Next Due") == "2026-10-29T19:00:00+00:00"
    changes = sync.get_changes(page, NOW + timedelta(days=10), TEMPLATES)
    assert get_copy(changes) == TEMPLATES["feedback2"]
    apply(page, changes)
    page["properties"]["Feedback Reminder Sent"]["checkbox"] = True
    apply(page, sync.get_changes(page, NOW + timedelta(days=10), TEMPLATES))
    assert sync.plain(page["properties"], "Follow-Up Timing").startswith("Complete")
    assert sync.get_changes(page, NOW + timedelta(days=20), TEMPLATES) == {}


@pytest.mark.parametrize("stage,field,kind,value", [
    ("Replied", "Registered At", "date", {"start": "2026-10-19"}),
    ("Accepted", "Onboarding Complete", "checkbox", True),
    ("Activated", "Feedback Submitted", "number", 1),
    ("Rejected", None, None, None), ("Inactive", None, None, None),
    ("Review Hold", None, None, None),
])
def test_relevant_progression_or_rejection_stops_followups(stage, field, kind, value):
    page = warm_row(stage if stage in ("Replied", "Accepted") else "Replied")
    p = page["properties"]
    p["Stage (AI Fills First)"]["select"] = {"name": stage}
    if field:
        p[field] = {kind: value}
    changes = sync.get_changes(page, NOW + timedelta(days=30), TEMPLATES)
    assert get_copy(changes) == ""
    assert "ready" not in sync.plain(changes, "Follow-Up Timing")


def test_initial_reply_uses_approved_segment_and_enquiry_without_starting_schedule():
    page = row(synced=0)
    page["properties"]["Notes"] = sync.rich("I already have a coach")
    changes = sync.get_changes(page, NOW, TEMPLATES)
    assert get_copy(changes) == TEMPLATES["amateur3"]
    assert "Details Sent At" not in changes
    assert "Safe Next Due" not in changes
    page["properties"]["Experience"] = {"select": {"name": "Professional"}}
    assert get_copy(sync.get_changes(page, NOW, TEMPLATES)) == TEMPLATES["professional1"]


def test_initial_reply_is_not_resent_when_details_already_sent():
    page = warm_row(root="2026-10-20T12:00:00+01:00")
    changes = sync.get_changes(page, NOW, TEMPLATES)
    assert get_copy(changes) == ""
    assert "waiting" in sync.plain(changes, "Follow-Up Timing")


@pytest.mark.parametrize("message", ["Any newly approved greeting", "Hello 👋\n\nNew text", "WAIT: operator instruction", ""])
def test_copy_eligibility_does_not_depend_on_greeting(message):
    page = warm_row()
    changes = sync.get_changes(page, NOW, {**TEMPLATES, "signup1": message})
    assert get_copy(changes) == (message if message and not message.startswith("WAIT") else "")


def test_warm_history_is_separate_from_inconsistent_cold_history():
    page = warm_row()
    page["properties"]["Follow-Ups Sent"]["select"] = {"name": "0"}
    page["properties"]["Synced Follow-Ups Sent"]["number"] = 2
    assert get_copy(sync.get_changes(page, NOW, TEMPLATES)) == TEMPLATES["signup1"]


def test_timestamp_edit_conflict_blocks_without_overwriting_verified_time():
    page = warm_row()
    apply(page, sync.get_changes(page, NOW, TEMPLATES))
    field = "Details Sent At"
    original = state_of(page)["dates"][field]
    page["properties"][field] = sync.date_patch("2026-10-12T10:00:00+01:00")
    changes = sync.get_changes(page, NOW, TEMPLATES)
    assert field not in changes
    assert "verified timestamp changed" in sync.plain(changes, "Follow-Up Timing")
    assert state_of(apply(page, changes))["dates"][field] == original


@pytest.mark.parametrize("field,new_value", [
    ("Details Sent At", sync.date_patch("2026-10-16")),
    (sync.SYNC_STATE, sync.rich('{"version":99}')),
    ("Signup Nudges Sent", {"select": {"name": "1"}}),
    ("Feedback Submitted", {"number": 1}),
])
def test_concurrent_notion_edits_on_final_read_never_get_overwritten(monkeypatch, field, new_value):
    page = warm_row()
    latest = copy.deepcopy(page)
    latest["properties"][field] = new_value
    responses = iter([page, latest])
    def request(method, path, body=None):
        assert method == "GET", "stale PATCH must not happen"
        return copy.deepcopy(next(responses))
    monkeypatch.setattr(sync, "pages", lambda: iter([page]))
    monkeypatch.setattr(sync, "request", request)
    assert sync.sync(NOW, TEMPLATES) == (1, 0)


def test_overlapping_cli_execution_skips_all_three_passes(monkeypatch, tmp_path):
    lock_path = tmp_path / "sync.lock"
    monkeypatch.setenv("NOTION_TOKEN", "test")
    monkeypatch.setenv("NOTION_FOLLOWUP_LOCK", str(lock_path))
    monkeypatch.setattr(sync, "sync", lambda: pytest.fail("overlapping run"))
    with lock_path.open("a") as lock:
        sync.fcntl.flock(lock, sync.fcntl.LOCK_EX | sync.fcntl.LOCK_NB)
        sync.run()


def test_template_parser_uses_labels_and_preserves_multiline_approved_copy():
    text = "Amateur fighters — 4 replies\n"
    text += "\n".join(f"{i}. Heading {i}\n\nApproved amateur {i}\nhttps://unlxck.com/signup\n" for i in range(1, 5))
    text += "Professional fighters — 4 replies\n"
    text += "\n".join(f"{i}. Heading {i}\n\nApproved professional {i}\nhttps://unlxck.com/signup\n" for i in range(1, 5))
    text += "How to choose a reply\nInstructions\n"
    for key, label in sync.TEMPLATE_LABELS.items():
        text += label + "\n\nEdited greeting for " + key + "\n\n"
    text += "The cold counter remains separate."
    parsed = sync.parse_response_templates(text)
    assert parsed["signup1"] == "Edited greeting for signup1"
    assert "https://unlxck.com/signup" in parsed["amateur1"]
    assert "Instructions" not in parsed["professional4"]
    with pytest.raises(ValueError, match="section"):
        sync.parse_response_templates(text.replace(sync.TEMPLATE_LABELS["signup1"], "Deleted label"))


@pytest.mark.parametrize("stage,action", [("Replied", "initial"), ("Accepted", "initial"),
                                         ("Replied", "1"), ("Accepted", "1")])
def test_record_send_receipt_works_before_any_baseline(stage, action):
    page = warm_row(stage, synced=None, root=None if action == "initial" else "2026-10-15T10:00:00+01:00")
    p = page["properties"]
    p[sync.SYNC_STATE] = sync.rich("")
    receipt = f"{stage}|{action}|2026-10-20T19:59:00+01:00"
    p[sync.SEND_RECEIPT] = sync.rich(receipt)
    changes = sync.get_changes(page, NOW, TEMPLATES)
    field = ("Details Sent At" if stage == "Replied" else "Onboarding Sent At") if action == "initial" else ("Signup Nudge 1 At" if stage == "Replied" else "Onboarding Nudge 1 At")
    assert changes[field] == sync.date_patch("2026-10-20T19:59:00+01:00")
    apply(page, changes)
    assert state_of(page)["receipt"] == receipt
    assert sync.get_changes(page, NOW + timedelta(minutes=2), TEMPLATES) == {}


def test_receipt_repeated_after_send_does_not_overwrite_timestamp():
    page = warm_row(count="1", synced=1, first="2026-10-19T10:00:00+01:00")
    page["properties"][sync.SEND_RECEIPT] = sync.rich("Replied|1|2026-10-20T19:59:00+01:00")
    changes = sync.get_changes(page, NOW, TEMPLATES)
    assert "Signup Nudge 1 At" not in changes
    assert "Duplicate" in sync.plain(changes, "Follow-Up Timing")
    assert get_copy(changes) == ""


@pytest.mark.parametrize("receipt", ["broken", "Replied|2|2026-10-20T19:59:00+01:00",
                                     "Replied|1|2026-10-21T19:59:00+01:00",
                                     "Replied|1|2026-10-15T11:00:00+01:00"])
def test_invalid_receipt_never_fabricates_send_history(receipt):
    page = warm_row()
    page["properties"][sync.SEND_RECEIPT] = sync.rich(receipt)
    changes = sync.get_changes(page, NOW, TEMPLATES)
    assert "Signup Nudge 1 At" not in changes
    assert "Needs Review" in sync.plain(changes, "Follow-Up Timing")
    assert get_copy(changes) == ""


def test_receipt_preserves_action_owner_across_stage_change():
    page = warm_row()
    p = page["properties"]
    p["Stage (AI Fills First)"]["select"] = {"name": "Accepted"}
    p[sync.SEND_RECEIPT] = sync.rich("Replied|1|2026-10-20T19:59:00+01:00")
    changes = sync.get_changes(page, NOW, TEMPLATES)
    assert "Signup Nudge 1 At" in changes
    assert "Onboarding Nudge 1 At" not in changes
    assert "Signup" not in sync.plain(changes, "Follow-Up Timing")


@pytest.mark.parametrize("stage,action,count", [("Replied", "2", "1"), ("Accepted", "2", "1"),
                                               ("Contacted", "1", "0"), ("Contacted", "2", "1")])
def test_receipt_records_final_and_cold_actions_once(stage, action, count):
    if stage == "Contacted":
        page = row(stage=stage, sent=count, synced=int(count), contacted="2026-10-10", first="2026-10-14T10:00:00+01:00" if count == "1" else None)
    else:
        page = warm_row(stage, count, int(count), first="2026-10-15T10:00:00+01:00", root="2026-10-10T10:00:00+01:00")
    page["properties"][sync.SEND_RECEIPT] = sync.rich(f"{stage}|{action}|2026-10-20T19:59:00+01:00")
    changes = sync.get_changes(page, NOW, TEMPLATES)
    assert "Needs Review" not in sync.plain(changes, "Follow-Up Timing")
    apply(page, changes)
    assert sync.get_changes(page, NOW, TEMPLATES) == {}
    if stage != "Contacted":
        assert state_of(page)["seconds"][stage] == "2026-10-20T19:59:00+01:00"


@pytest.mark.parametrize("code", [429, 529])
def test_patch_rate_limit_does_not_retry_stale_page_mutation(monkeypatch, code):
    attempts = []
    def fail(req, timeout):
        attempts.append(req)
        raise HTTPError(req.full_url, code, "Retry later", {"Retry-After": "1"}, None)
    monkeypatch.setattr(sync, "urlopen", fail)
    monkeypatch.setattr(sync.time, "sleep", lambda _: None)
    with pytest.raises(HTTPError):
        sync.request("PATCH", "/pages/sample", {"properties": {}})
    assert len(attempts) == 1


def test_approved_live_response_page_snapshot_is_parseable():
    # Audited 2026-10-20. Runtime still reads the live page, never this fixture.
    source = (MODULE.parents[1] / "tests/fixtures/notion_response_dm.txt").read_text()
    templates = sync.parse_response_templates(source)
    assert len(templates) == 14
    assert templates["signup1"] == "Hey mate, just checking you got the beta link. Any issues signing up? Happy to help."
    assert templates["feedback2"].endswith("No pressure.")
    assert templates["professional1"].endswith("https://unlxck.com/signup")
    assert "How to choose" not in templates["professional4"]


def schema_fixture():
    # REST types verified against the live connector schema, not formula source.
    p = row()["properties"]
    props = {}
    for name, prop in p.items():
        kind = next(iter(prop))
        props[name] = {"type": kind, kind: {"expression": "original_expression"} if kind == "formula" else {}}
    props["Warm Next Due"] = {"type": "formula", "formula": {"expression": "old_warm_due"}}
    props["Outreach Next Step"] = {"type": "formula", "formula": {"expression": 'if(prop("Stage (AI Fills First)") == "Contacted", "cold action", "warm action")'}}
    return {"properties": props}


def test_schema_plan_is_additive_and_preserves_cold_formula_branch():
    schema = schema_fixture()
    schema["properties"].pop(sync.SYNC_STATE)
    plan = sync.schema_plan(schema)["properties"]
    assert plan[sync.SYNC_STATE] == {"rich_text": {}}
    assert plan[sync.SEND_RECEIPT] == {"rich_text": {}}
    assert plan["Warm Next Due"]["formula"]["expression"] == 'prop("Safe Next Due")'
    assert plan["Warm Next DM"]["formula"]["expression"] == 'prop("Copy Follow-Up")'
    assert schema["properties"]["Outreach Next Step"]["formula"]["expression"] in plan["Outreach Next Step"]["formula"]["expression"]
    assert "Follow-Up DM" not in plan
    assert "Stage History" not in plan
    assert "Reply Rate (%)" not in plan
    for name, value in plan.items():
        schema["properties"][name] = {"type": next(iter(value)), **value}
    assert sync.schema_plan(schema) == {"properties": {}}


def test_schema_plan_fails_before_write_on_incompatible_property(monkeypatch):
    schema = schema_fixture()
    schema["properties"]["Safe Next Due"]["type"] = "formula"
    def request(method, path, body=None):
        assert method == "GET"
        return schema
    monkeypatch.setattr(sync, "request", request)
    with pytest.raises(ValueError, match="Safe Next Due"):
        sync.prepare_schema(apply=True)


def test_schema_preview_never_mutates_notion(monkeypatch):
    methods = []
    def request(method, path, body=None):
        methods.append(method)
        return schema_fixture()
    monkeypatch.setattr(sync, "request", request)
    assert sync.prepare_schema()["properties"]
    assert methods == ["GET"]


def test_missing_template_source_clears_warm_copy_without_blocking_history(monkeypatch):
    page = warm_row()
    writes = []
    def unavailable():
        raise ValueError("section removed")
    def request(method, path, body=None):
        if method == "GET":
            return copy.deepcopy(page)
        writes.append(body["properties"])
    monkeypatch.setattr(sync, "response_templates", unavailable)
    monkeypatch.setattr(sync, "pages", lambda: iter([page]))
    monkeypatch.setattr(sync, "request", request)
    assert sync.sync(NOW) == (1, 1)
    assert writes[0]["Copy Follow-Up"] == sync.rich("")
    assert "Needs Review" in sync.plain(writes[0], "Follow-Up Timing")


def test_unchanged_baselined_records_do_not_use_per_row_api_budget(monkeypatch):
    page = warm_row()
    apply(page, sync.get_changes(page, NOW, TEMPLATES))
    monkeypatch.setattr(sync, "pages", lambda: iter([page] * 220))
    monkeypatch.setattr(sync, "request", lambda *_: pytest.fail("unchanged rows need no extra GET/PATCH"))
    assert sync.sync(NOW, TEMPLATES) == (220, 0)


def test_corrupt_state_clears_copy_and_does_not_overwrite_dates(monkeypatch):
    page = warm_row()
    page["properties"][sync.SYNC_STATE] = sync.rich("corrupt JSON")
    writes = []
    def request(method, path, body=None):
        if method == "GET":
            return copy.deepcopy(page)
        writes.append(body["properties"])
    monkeypatch.setattr(sync, "pages", lambda: iter([page]))
    monkeypatch.setattr(sync, "request", request)
    assert sync.sync(NOW, TEMPLATES) == (1, 1)
    assert writes[0] == {"Safe Next Due": sync.date_patch(None), "Copy Follow-Up": sync.rich(""),
                         "Follow-Up Timing": sync.rich("Needs Review: invalid or incomplete sync state")}


@pytest.mark.parametrize("field", ["First Reply Confirmed At", "Rejected At", "Accepted At", "Registered At"])
def test_confirmed_engagement_prevents_cold_restart_after_stage_reversal(field):
    page = row(stage="Contacted", synced=0)
    page["properties"][field] = sync.date_patch("2026-10-19")
    changes = sync.get_changes(page, NOW, TEMPLATES)
    assert get_copy(changes) == ""
    assert "no cold follow-up" in sync.plain(changes, "Follow-Up Timing")


def test_feedback_activation_uses_existing_confirmed_crm_observation():
    page = row(stage="Activated")
    page["properties"]["Confirmed Stage"] = sync.rich("Activated")
    page["properties"]["Stage Confirmed At"] = sync.date_patch("2026-10-15T10:00:00+01:00")
    changes = sync.get_changes(page, NOW, TEMPLATES)
    assert changes["Safe Next Due"] == sync.date_patch("2026-10-19T10:00:00+01:00")
    assert get_copy(changes) == TEMPLATES["feedback1"]
    assert "Stage Confirmed At" not in changes
    assert "First Meaningful Action At" not in changes
