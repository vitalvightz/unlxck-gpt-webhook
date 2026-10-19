"""Keep UNLXCK's editable Notion follow-up DM synced with its calculated copy.

Run every two minutes using a single server-side timer. Reuse the existing
server-side outreach qualification worker's Notion integration and credentials.
"""

import json
import os
import random
import sys
import time
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

DATA_SOURCE_ID = os.getenv("NOTION_OUTREACH_DATA_SOURCE_ID", "08d8b476129a42b0b980102b08ce4bd8")
BASE = "https://api.notion.com/v1"


def notion_token():
    # The existing outreach qualification worker may use a different env name.
    # Reuse its token; do not create another integration or log the value.
    return (os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_KEY")
            or os.getenv("NOTION_INTEGRATION_TOKEN"))


ACTIVE_STAGES = ("Contacted", "Replied", "Accepted", "Activated")

# Only the Contacted stage produces automatic follow-up sends.
# A blank due date for an exception/terminal stage is intentional; Timing explains why.
MISSING_SEND_DATE = "NEEDS DATE: verify the first follow-up's actual Instagram send date."
MISSING_CONTACT_DATE = "NEEDS DATE: record the Instagram initial contact date."
BAD_COUNT = "NEEDS REVIEW: follow-up count conflicts with recorded send history."
LONDON = ZoneInfo("Europe/London")


def date_value(properties, name):
    return (properties[name].get("date") or {}).get("start")


def date_patch(value):
    return {"date": {"start": value} if value else None}


def message_patch(value):
    return {"rich_text": [{"text": {"content": value}}] if value else []}


def parse_stamp(value):
    if not value:
        return None
    if "T" not in value:
        return datetime.combine(date.fromisoformat(value), datetime_time.min, LONDON)
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return stamp.replace(tzinfo=LONDON) if stamp.tzinfo is None else stamp.astimezone(LONDON)


def same_date_value(left, right):
    """Compare real timestamps, not Notion's differing timezone/precision renderings."""
    if not left or not right:
        return left == right
    if ("T" in left) != ("T" in right):
        return False
    return parse_stamp(left) == parse_stamp(right)


def now_london(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime.combine(value, datetime_time.min, LONDON)
    return value.replace(tzinfo=LONDON) if value.tzinfo is None else value.astimezone(LONDON)


def waiting_until(due):
    return f"WAIT: next follow-up is due {due.strftime('%d %b %Y, %H:%M %Z')}."


def due_and_copy(properties, count, first, second, now, formula):
    stage = (properties["Stage (AI Fills First)"].get("select") or {}).get("name")
    if stage != "Contacted":
        return None, "Not in follow-up queue", formula

    contacted = date_value(properties, "Date Contacted")
    if not contacted:
        return None, "Needs contact date", MISSING_CONTACT_DATE
    if count not in (0, 1, 2):
        return None, "Invalid follow-up count", BAD_COUNT
    if count == 2:
        if not first or not second:
            return None, "Complete (send history incomplete)", ""
        # Historical send records cannot be undone, but early second sends
        # should remain visible for investigation rather than silently pass.
        first_stamp = parse_stamp(first)
        after_first = (datetime.combine(first_stamp.date() + timedelta(days=6),
                       datetime_time.min, LONDON) if "T" not in first
                       else (first_stamp.astimezone(timezone.utc) + timedelta(days=5)).astimezone(LONDON))
        day_eight = datetime.combine(
            parse_stamp(contacted).date() + timedelta(days=8), datetime_time.min, LONDON)
        if parse_stamp(second) < max(day_eight, after_first):
            return None, "Complete (timing review)", ""
        return None, "Complete (2 sent)", ""  # Never issue follow-up 3.
    if (count == 0 and (first or second)) or (count == 1 and second):
        return None, "Needs count review", BAD_COUNT

    contacted_local = parse_stamp(contacted).date()
    if count == 0:
        due = datetime.combine(contacted_local + timedelta(days=3), datetime_time.min, LONDON)
        status = "Follow-up 1"
    else:
        if not first:
            return None, "Needs first send date", MISSING_SEND_DATE
        first_stamp = parse_stamp(first)
        # Date-only historical evidence has unknown time of day. Wait through day 5.
        after_first = (datetime.combine(first_stamp.date() + timedelta(days=6),
                       datetime_time.min, LONDON) if "T" not in first
                       else (first_stamp.astimezone(timezone.utc) + timedelta(days=5)).astimezone(LONDON))
        day_eight = datetime.combine(contacted_local + timedelta(days=8), datetime_time.min, LONDON)
        due = max(day_eight, after_first)
        status = "Follow-up 2"

    if now < due:
        return due.isoformat(timespec="seconds"), f"{status}: waiting", waiting_until(due)
    return due.isoformat(timespec="seconds"), f"{status}: ready", formula


def missing_send_date(properties):
    return (
        (properties["Stage (AI Fills First)"].get("select") or {}).get("name") == "Contacted"
        and (properties["Follow-Ups Sent"].get("select") or {}).get("name") == "1"
        and not (date_value(properties, "Follow-Up 1 Sent At")
                 or date_value(properties, "Last Follow-Up Sent"))
        and properties["Synced Follow-Ups Sent"].get("number") not in (0, 0.0)
    )


def request(method, path, body=None):
    headers = {
        "Authorization": f"Bearer {notion_token()}",
        "Notion-Version": "2025-09-03",
        "Content-Type": "application/json",
    }
    payload = json.dumps(body).encode() if body is not None else None
    for attempt in range(4):
        time.sleep(0.35)  # Stay below Notion's average three requests/second.
        try:
            with urlopen(Request(BASE + path, data=payload, headers=headers, method=method), timeout=20) as response:
                return json.load(response)
        except HTTPError as exc:
            read_only = method == "GET" or path.endswith("/query")
            retryable = exc.code in (429, 529) or (read_only and exc.code in (500, 502, 503, 504))
            if not retryable or attempt == 3:
                raise
            delay = float(exc.headers.get("Retry-After") or min(2 ** attempt, 10))
            time.sleep(delay + random.uniform(0, 0.25))


def pages():
    cursor = None
    while True:
        body = {"page_size": 100, "filter": {"or": [
            {"property": "Stage (AI Fills First)", "select": {"equals": stage}}
            for stage in ACTIVE_STAGES
        ]}}
        if cursor:
            body["start_cursor"] = cursor
        result = request("POST", f"/data_sources/{DATA_SOURCE_ID}/query", body)
        yield from result["results"]
        cursor = result.get("next_cursor")
        if not result.get("has_more"):
            break


def get_changes(page, today):
    """Synchronise state without guessing whether an editor or a button supplied a time."""
    p = page["properties"]
    count = int((p["Follow-Ups Sent"].get("select") or {}).get("name") or 0)
    synced = p["Synced Follow-Ups Sent"].get("number")
    calculated = p["Follow-Up DM"].get("formula") or {}
    if calculated.get("type") != "string" or calculated.get("string") is None:
        raise ValueError(f"Missing calculated follow-up for {page['id']}")
    now = now_london(today)
    observed = now.isoformat(timespec="seconds")
    first = date_value(p, "Follow-Up 1 Sent At")
    second = date_value(p, "Follow-Up 2 Sent At")
    legacy = date_value(p, "Last Follow-Up Sent")
    changes = {}

    # Backfill unambiguous existing evidence. Never use a last-send date as the
    # first-send date for a record already at 2: it may belong to follow-up 2.
    if count == 1 and not first and legacy:
        first = legacy
        changes["Follow-Up 1 Sent At"] = date_patch(first)
    elif count == 2 and not second and legacy and synced in (None, 2, 2.0):
        second = legacy
        changes["Follow-Up 2 Sent At"] = date_patch(second)

    increased = synced is not None and int(synced) < count
    consecutive = increased and count - int(synced) == 1
    if consecutive and count == 1 and not first:
        # Polling observation is a conservative upper bound on the send time,
        # not proof of an exact Instagram timestamp.
        first = observed
        changes["Follow-Up 1 Sent At"] = date_patch(first)
        if not legacy:
            changes["Last Follow-Up Sent"] = date_patch(first)
    elif consecutive and count == 2 and not second:
        second = observed
        changes["Follow-Up 2 Sent At"] = date_patch(second)
        changes["Last Follow-Up Sent"] = date_patch(second)
    elif count == 2 and second and not same_date_value(legacy, second):
        # Preserve first-send history in its own property, and maintain the
        # existing compatibility field as the *last* event.
        changes["Last Follow-Up Sent"] = date_patch(second)

    if synced is None or int(synced) != count:
        changes["Synced Follow-Ups Sent"] = {"number": count}

    due, status, message = due_and_copy(
        p, count, first, second, now, calculated["string"])
    # A poll missed one or more intermediate send events. Never infer their
    # dates, and never show potentially premature sendable copy.
    if increased and not consecutive:
        due, status, message = None, "Needs count review", BAD_COUNT
    if synced is not None and count < int(synced):
        due, status, message = None, "Needs count review", BAD_COUNT

    current_due = date_value(p, "Safe Next Due")
    if not same_date_value(current_due, due):
        changes["Safe Next Due"] = date_patch(due)
    current_status = "".join(x.get("plain_text", "") for x in p["Follow-Up Timing"].get("rich_text", []))
    if current_status != status:
        changes["Follow-Up Timing"] = message_patch(status)
    current_message = "".join(x.get("plain_text", "") for x in p["Copy Follow-Up"].get("rich_text", []))
    if current_message != message:
        changes["Copy Follow-Up"] = message_patch(message)
    return changes


def sync(today=None):
    today = today or datetime.now(ZoneInfo("Europe/London"))
    total = changed = missing_dates = 0
    for page in pages():
        total += 1
        missing_dates += missing_send_date(page["properties"])
        changes = get_changes(page, today)
        if not changes:
            continue
        # Avoid applying an out-of-date candidate if stage/count changed mid-poll.
        fresh = request("GET", f"/pages/{page['id']}")
        original = page["properties"]
        current = fresh["properties"]
        if (original["Stage (AI Fills First)"].get("select") != current["Stage (AI Fills First)"].get("select")
                or original["Follow-Ups Sent"].get("select") != current["Follow-Ups Sent"].get("select")):
            continue
        changes = get_changes(fresh, today)
        if changes:
            request("PATCH", f"/pages/{page['id']}", {"properties": changes})
            changed += 1
    if missing_dates:
        print(f"Notion follow-ups: {missing_dates} contacted rows need historical send-date verification")
    return total, changed




# Reuse the existing cron and integration for dashboard totals, too.
SCORECARD_PAGE_ID = "3fcd6e718d27815f8509e69f573bcf27"


def scorecard_rows():
    cursor = None
    while True:
        body = {"page_size": 100, "filter": {
            "property": "Date Contacted", "date": {"is_not_empty": True},
        }}
        if cursor:
            body["start_cursor"] = cursor
        result = request("POST", f"/data_sources/{DATA_SOURCE_ID}/query", body)
        for page in result["results"]:
            detail = "".join(part.get("plain_text", "") for part in
                             page["properties"]["Source Detail"].get("rich_text", []))
            if detail != "SYSTEM_COUNTER":
                yield page
        if not result.get("has_more"):
            break
        cursor = result["next_cursor"]


def all_pipeline_rows():
    cursor = None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        result = request("POST", f"/data_sources/{DATA_SOURCE_ID}/query", body)
        for page in result["results"]:
            detail = plain(page["properties"], "Source Detail")
            if detail != "SYSTEM_COUNTER":
                yield page
        if not result.get("has_more"):
            break
        cursor = result["next_cursor"]


def block_children(parent_id):
    cursor = None
    while True:
        path = f"/blocks/{parent_id}/children?page_size=100"
        if cursor:
            path += f"&start_cursor={cursor}"
        result = request("GET", path)
        yield from result["results"]
        if not result.get("has_more"):
            break
        cursor = result["next_cursor"]


def block_text(block):
    return "".join(item.get("plain_text", item.get("text", {}).get("content", ""))
                   for item in block[block["type"]].get("rich_text", []))


# Record only stable, observed post-contact stage changes; do not invent historical dates.
STAGE_STABILITY_SECONDS = 5 * 60


def plain(p, name):
    return "".join(v.get("plain_text", v.get("text", {}).get("content", ""))
                   for v in p[name].get("rich_text", []))


def rich(value):
    return {"rich_text": [{"text": {"content": value[i:i + 1900]}}
                          for i in range(0, len(value), 1900)]}


def stage_changes(page, now):
    p = page["properties"]
    stage = ((p["Stage (AI Fills First)"].get("select") or {}).get("name") or "")
    if not stage:
        return {}
    observed = plain(p, "Observed Stage")
    if stage != observed or not p["Observed Since"].get("date"):
        return {"Observed Stage": rich(stage),
                "Observed Since": {"date": {"start": now.isoformat(timespec="seconds")}}}
    confirmed = plain(p, "Confirmed Stage")
    first_seen = datetime.fromisoformat(
        p["Observed Since"]["date"]["start"].replace("Z", "+00:00"))
    # General page edits can delay confirmation; they cannot prove stage continuity.
    edited = page.get("last_edited_time")
    if edited:
        last_edit = datetime.fromisoformat(edited.replace("Z", "+00:00"))
        if last_edit > first_seen and (now - last_edit).total_seconds() < STAGE_STABILITY_SECONDS:
            return {}
    if (now - first_seen).total_seconds() < STAGE_STABILITY_SECONDS:
        return {}
    timestamp = now.isoformat(timespec="seconds")
    contacted = bool(p["Date Contacted"].get("date"))
    rejection_transition = stage == "Rejected" and bool(confirmed) and confirmed != "Rejected"
    # These dates are when the CRM stage was confirmed, not historical DM dates.
    milestones = (
        ("First Reply Confirmed At", contacted and (stage in ("Replied", "Accepted", "Activated")
                                                  or rejection_transition)),
        ("Accepted At", contacted and stage in ("Accepted", "Activated")),
        ("Rejected At", contacted and rejection_transition),
    )
    changes = {prop: {"date": {"start": timestamp}} for prop, reached in milestones
               if reached and not p[prop].get("date")}
    # Repair baselines confirmed by #2925 before milestones existed.
    if confirmed == stage:
        return changes
    previous = confirmed or "baseline"
    history = plain(p, "Stage History")
    entry = f"{first_seen.isoformat(timespec='seconds')} {previous} -> {stage} (confirmed {timestamp})"
    changes.update({
        "Confirmed Stage": rich(stage),
        "Stage Confirmed At": {"date": {"start": timestamp}},
        "Stage History": rich(history + ("\n" if history else "") + entry),
    })
    return changes


def sync_stage_history(now=None, max_updates=20):
    now = now or datetime.now(timezone.utc)
    checked = updated = 0
    for page in all_pipeline_rows():
        checked += 1
        changes = stage_changes(page, now)
        if not changes:
            continue
        # Re-read before writing to avoid confirming a stage changed mid-poll.
        fresh = request("GET", f"/pages/{page['id']}")
        if ((page["properties"]["Stage (AI Fills First)"].get("select") or {}).get("name")
                != (fresh["properties"]["Stage (AI Fills First)"].get("select") or {}).get("name")):
            continue
        changes = stage_changes(fresh, now)
        if not changes:
            continue
        request("PATCH", f"/pages/{page['id']}", {"properties": changes})
        updated += 1
        if updated >= max_updates:
            break
    return checked, updated


def sync_scorecard():
    rows = list(scorecard_rows())
    total = len(rows)
    counts = {"REPLY RATE": 0, "ACCEPT RATE": 0, "ACTIVATION RATE": 0}
    for page in rows:
        p = page["properties"]
        stage = ((p["Stage (AI Fills First)"].get("select") or {}).get("name") or "")
        if p["First Reply Confirmed At"].get("date") or stage in ("Replied", "Accepted", "Activated", "Rejected"):
            counts["REPLY RATE"] += 1
        if p["Accepted At"].get("date") or stage in ("Accepted", "Activated"):
            counts["ACCEPT RATE"] += 1
        if stage == "Activated":
            counts["ACTIVATION RATE"] += 1

    cards = {}
    def inspect(parent_id):
        for block in block_children(parent_id):
            if block["type"] in ("column_list", "column"):
                inspect(block["id"])
            elif block["type"] == "callout":
                parts = list(block_children(block["id"]))
                names = [block_text(part) for part in parts if part["type"] == "paragraph"]
                for name in counts:
                    if name not in names:
                        continue
                    if name in cards:
                        raise ValueError(f"Duplicate scorecard card: {name}")
                    headline = [part for part in parts if part["type"].startswith("heading_")]
                    detail = [part for part in parts if part["type"] == "paragraph"
                              and ((" of " in block_text(part) and block_text(part).endswith(" fighters"))
                                  or block_text(part) == "Awaiting verified app-event integration")]
                    if len(headline) != 1 or len(detail) != 1:
                        raise ValueError(f"Unexpected scorecard layout: {name}")
                    cards[name] = (headline[0], detail[0])

    inspect(SCORECARD_PAGE_ID)
    if set(cards) != set(counts):
        raise ValueError(f"Missing scorecard cards: {set(counts) - set(cards)}")

    updated = 0
    for name, (headline, detail) in cards.items():
        percent = f"{100 * counts[name] / total:.1f}%" if total else "0%"
        description = f"{counts[name]} of {total} fighters"
        for block, value in ((headline, percent), (detail, description)):
            if block_text(block) != value:
                request("PATCH", f"/blocks/{block['id']}",
                        {block["type"]: {"rich_text": [{"type": "text", "text": {"content": value}}]}})
                updated += 1
    return total, updated

if __name__ == "__main__":
    if not notion_token():
        sys.exit("Expose the existing qualification worker Notion token as NOTION_TOKEN or NOTION_API_KEY (never commit it).")
    total, changed = sync()
    print(f"Notion follow-ups: checked {total}, updated {changed}")
    checked, updated = sync_stage_history()
    print(f"Notion stages: examined {checked}, updated {updated}")
    contacted, updated = sync_scorecard()
    print(f"Notion conversion: contacted {contacted}, updated {updated} blocks")
