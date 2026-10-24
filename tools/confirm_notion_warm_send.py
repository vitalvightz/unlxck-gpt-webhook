"""Desktop integration: reserve a warm attempt, then confirm an actual Instagram send.

All 3B senders must share this persistent SQLite journal and run serially.
An uncertain attempt stays reserved for manual review; never delete it to resend.
Notion has no conditional PATCH: other writers must not edit counters during sends.
"""
import argparse
import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime

import sync_notion_followups as sync


def guard(message):
    return hashlib.sha256(message.encode()).hexdigest()


@contextmanager
def journal(path):
    with sqlite3.connect(path, timeout=20) as db:
        db.execute("CREATE TABLE IF NOT EXISTS sends (page TEXT, step INTEGER, copy_hash TEXT, "
                   "message_id TEXT UNIQUE, stamp TEXT, applied INTEGER DEFAULT 0, PRIMARY KEY(page, step))")
        db.execute("BEGIN IMMEDIATE")
        yield db


def live(page_id, step, copy_hash, now):
    page = sync.request("GET", f"/pages/{page_id}")
    p = page["properties"]
    stage = (p["Stage (AI Fills First)"].get("select") or {}).get("name")
    count, _, error = sync.warm_nudge_progress(p)
    due, _ = sync.warm_schedule(p, now)
    if (stage not in sync.WARM_MESSAGES or sync.warm_review(page) or error or count != step - 1
            or p["Synced Signup Nudges Sent"].get("number") != count or not due
            or sync.parse_stamp(due) > now or step not in (1, 2)
            or guard(sync.WARM_MESSAGES[stage][count]) != copy_hash):
        raise ValueError("HOLD: live stage/count/history/due/copy changed")
    return page


def prepare(path, page_id, step, copy_hash, now):
    with journal(path) as db:
        live(page_id, step, copy_hash, now)
        db.execute("INSERT INTO sends(page, step, copy_hash) VALUES (?, ?, ?)", (page_id, step, copy_hash))
    # A duplicate reservation fails; the desktop flow must skip the send.


def confirm(path, page_id, step, message_id, now):
    if not message_id.strip():
        raise ValueError("A confirmed Instagram message ID is required")
    # Persist confirmation before the network call so an ambiguous response can
    # be reconciled against the exact same event time on retry.
    with journal(path) as db:
        row = db.execute("SELECT copy_hash, message_id, stamp, applied FROM sends WHERE page=? AND step=?",
                         (page_id, step)).fetchone()
        if not row or row[1] not in (None, message_id):
            raise ValueError("HOLD: no matching attempt or conflicting send confirmation")
        if row[3]:
            return
        stamp = row[2] or now.isoformat(timespec="seconds")
        db.execute("UPDATE sends SET message_id=?, stamp=? WHERE page=? AND step=?",
                   (message_id, stamp, page_id, step))
    with journal(path) as db:
        page = sync.request("GET", f"/pages/{page_id}")
        p = page["properties"]
        count = (p["Signup Nudges Sent"].get("select") or {}).get("name") or "0"
        if count == str(step) and sync.same_date_value(sync.date_value(p, "Warm Last Nudge At"), stamp):
            pass  # Earlier PATCH succeeded but its response was lost.
        else:
            live(page_id, step, row[0], now)
            patch = {"Signup Nudges Sent": {"select": {"name": str(step)}},
                     "Synced Signup Nudges Sent": {"number": step},
                     "Warm Last Nudge At": sync.date_patch(stamp)}
            if step == 1:
                patch["Signup Nudge 1 At"] = sync.date_patch(stamp)
            sync.request("PATCH", f"/pages/{page_id}", {"properties": patch})
        db.execute("UPDATE sends SET applied=1 WHERE page=? AND step=?", (page_id, step))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "confirm"))
    parser.add_argument("page_id")
    parser.add_argument("step", type=int, choices=(1, 2))
    parser.add_argument("evidence", help="prepare: approved message SHA256; confirm: verified Instagram message ID")
    parser.add_argument("--journal", required=True)
    args = parser.parse_args()
    page_id = args.page_id.replace("-", "").lower()
    action = prepare if args.action == "prepare" else confirm
    action(args.journal, page_id, args.step, args.evidence, datetime.now(sync.LONDON))
