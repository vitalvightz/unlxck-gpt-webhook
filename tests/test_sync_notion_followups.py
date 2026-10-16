"""Minimal regression tests for the scheduled Notion sync."""

import importlib.util
from datetime import date
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
