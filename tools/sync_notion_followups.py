"""Keep UNLXCK's editable Notion follow-up DM synced with its calculated copy.

Run every two minutes using a single server-side timer. Set NOTION_TOKEN in
/opt/unlxck/.env.production; grant that integration access to the pipeline.
"""

import json
import os
import random
import sys
import time
from datetime import datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

DATA_SOURCE_ID = os.getenv("NOTION_OUTREACH_DATA_SOURCE_ID", "08d8b476129a42b0b980102b08ce4bd8")
BASE = "https://api.notion.com/v1"
ACTIVE_STAGES = ("Contacted", "Replied", "Accepted", "Activated")


def request(method, path, body=None):
    headers = {
        "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
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
    p = page["properties"]
    count = int((p["Follow-Ups Sent"].get("select") or {}).get("name") or 0)
    synced = p["Synced Follow-Ups Sent"].get("number")
    calculated = p["Follow-Up DM"].get("formula") or {}
    if calculated.get("type") != "string" or calculated.get("string") is None:
        raise ValueError(f"Missing calculated follow-up for {page['id']}")
    message = calculated["string"]
    current = "".join(x.get("plain_text", "") for x in p["Copy Follow-Up"].get("rich_text", []))
    changes = {}
    if current != message:
        changes["Copy Follow-Up"] = {"rich_text": [{"text": {"content": message}}] if message else []}
    if synced is None or int(synced) != count:
        changes["Synced Follow-Ups Sent"] = {"number": count}
        # Baseline pre-existing records without assuming a date we did not witness.
        if synced is not None and int(synced) < count:
            changes["Last Follow-Up Sent"] = {"date": {"start": today.isoformat()}}
    return changes


def sync(today=None):
    today = today or datetime.now(ZoneInfo("Europe/London")).date()
    total = changed = 0
    for page in pages():
        total += 1
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
    return total, changed


if __name__ == "__main__":
    if not os.getenv("NOTION_TOKEN"):
        sys.exit("Set NOTION_TOKEN in the server environment (never commit it).")
    total, changed = sync()
    print(f"Notion follow-ups: checked {total}, updated {changed}")
