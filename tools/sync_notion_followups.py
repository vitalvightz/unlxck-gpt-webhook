"""Keep UNLXCK's editable Notion follow-up DM synced with its calculated copy.

Run every two minutes using a single server-side timer. Reuse the existing
server-side outreach qualification worker's Notion integration and credentials.
"""

import fcntl
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
WARM_STAGES = ("Replied", "Accepted", "Activated")
# New warm follow-up counters are independent of the original cold DM counter.
WARM_COUNTERS = (
    ("Replied", "Signup Nudges Sent", "Synced Signup Nudges Sent", "Signup Nudge 1 At"),
    ("Accepted", "Onboarding Nudges Sent", "Synced Onboarding Nudges Sent", "Onboarding Nudge 1 At"),
)

# Cold follow-ups retain their original Contacted schedule.
# A blank due date for an exception/terminal stage is intentional; Timing explains why.
MISSING_SEND_DATE = "NEEDS DATE: verify the first follow-up's actual Instagram send date."
MISSING_CONTACT_DATE = "NEEDS DATE: record the Instagram initial contact date."
BAD_COUNT = "NEEDS REVIEW: follow-up count conflicts with recorded send history."
LONDON = ZoneInfo("Europe/London")


def date_value(properties, name):
    return (properties.get(name, {}).get("date") or {}).get("start")


def date_patch(value):
    return {"date": {"start": value} if value else None}


def message_patch(value):
    return rich(value)


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

    if any(date_value(properties, field) for field in ("First Reply Confirmed At", "Accepted At", "Rejected At", "Registered At")):
        return None, "Engagement recorded — no cold follow-up", ""
    contacted = date_value(properties, "Date Contacted")
    if not contacted:
        return None, "Needs contact date", MISSING_CONTACT_DATE
    if count not in (0, 1, 2):
        return None, "Invalid follow-up count", BAD_COUNT
    if count == 2:
        if not first or not second:
            return None, "Needs Review: send history incomplete", ""
        # Historical send records cannot be undone, but early second sends
        # should remain visible for investigation rather than silently pass.
        first_stamp = parse_stamp(first)
        after_first = (datetime.combine(first_stamp.date() + timedelta(days=6),
                       datetime_time.min, LONDON) if "T" not in first
                       else (first_stamp.astimezone(timezone.utc) + timedelta(days=5)).astimezone(LONDON))
        day_eight = datetime.combine(
            parse_stamp(contacted).date() + timedelta(days=8), datetime_time.min, LONDON)
        if parse_stamp(second) < max(day_eight, after_first):
            return None, "Needs Review: send timing", ""
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

    if now.astimezone(timezone.utc) < due.astimezone(timezone.utc):
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
            retryable = read_only and exc.code in (429, 529, 500, 502, 503, 504)
            if not retryable or attempt == 3:
                raise
            delay = float(exc.headers.get("Retry-After") or min(2 ** attempt, 10))
            time.sleep(delay + random.uniform(0, 0.25))


def pages():
    # Baseline every prospect before stage entry and clear stale copy on exit.
    yield from all_pipeline_rows()


def get_changes(page, today, templates=None):
    """Synchronise state without guessing whether an editor or a button supplied a time."""
    page, receipt_changes = consume_send_receipt(page, today)
    p = page["properties"]
    count_name = (p["Follow-Ups Sent"].get("select") or {}).get("name") or "0"
    count = int(count_name) if count_name in ("0", "1", "2") else -1
    synced = p["Synced Follow-Ups Sent"].get("number")
    invalid_checkpoint = synced not in (None, 0, 1, 2)
    if invalid_checkpoint:
        synced = None
    calculated = p["Follow-Up DM"].get("formula") or {}
    if calculated.get("type") != "string" or calculated.get("string") is None:
        raise ValueError(f"Missing calculated follow-up for {page['id']}")
    now = now_london(today)
    observed = now.isoformat(timespec="seconds")
    first = date_value(p, "Follow-Up 1 Sent At")
    second = date_value(p, "Follow-Up 2 Sent At")
    legacy = date_value(p, "Last Follow-Up Sent")
    changes = dict(receipt_changes)

    # Backfill unambiguous existing evidence. Never use a last-send date as the
    # first-send date for a record already at 2: it may belong to follow-up 2.
    if count == 1 and not first and legacy and synced in (None, 0, 1):
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
    elif consecutive and count == 2 and first and not second:
        second = observed
        changes["Follow-Up 2 Sent At"] = date_patch(second)
        changes["Last Follow-Up Sent"] = date_patch(second)
    elif count == 2 and second and not legacy:
        # Preserve first-send history in its own property, and maintain the
        # existing compatibility field as the *last* event.
        changes["Last Follow-Up Sent"] = date_patch(second)

    if count in (0, 1, 2) and not invalid_checkpoint and (synced is None or int(synced) != count):
        if synced is None or count == int(synced) + 1:
            changes["Synced Follow-Ups Sent"] = {"number": count}

    due, status, message = due_and_copy(
        p, count, first, second, now, calculated["string"])
    warm_changes, state = warm_state(page, today)
    changes.update(warm_changes)
    stage = (p["Stage (AI Fills First)"].get("select") or {}).get("name")
    if stage in WARM_STAGES:
        due, status, message = warm_due_and_copy({**p, **warm_changes}, state, now, templates or {})
    elif stage != "Contacted":
        due, status, message = None, "No further follow-up", ""
    for field, value in (("Follow-Up 1 Sent At", first), ("Follow-Up 2 Sent At", second)):
        recorded = state["dates"].get(field)
        current = date_value(p, field)
        if recorded and not same_date_value(recorded, current):
            state["reviews"]["Contacted"] = f"{field}: verified timestamp changed"
        elif value:
            state["dates"][field] = value
    if stage == "Contacted":
        if invalid_checkpoint:
            state["reviews"][stage] = "Invalid counter checkpoint"
        if increased and not consecutive or synced is not None and count < synced:
            state["reviews"][stage] = "Counter reversed or skipped a send"
        if count == 1 and legacy and first and not same_date_value(legacy, first):
            state["reviews"][stage] = "Last send conflicts with first send"
        if count == 2 and legacy and second and not same_date_value(legacy, second) and not (consecutive and "Follow-Up 2 Sent At" in changes):
            state["reviews"][stage] = "Last send conflicts with final send"
        if stage in state["reviews"]:
            due, status, message = None, "Needs Review: " + state["reviews"][stage], ""
        elif not status.startswith("Needs Review") and status.startswith(("Needs", "Invalid")):
            status = "Needs Review: " + status
        # Only actual eligible DMs belong in the mobile copy field.
        if not status.endswith(": ready") or message.lstrip().upper().startswith(("WAIT", "NEEDS REVIEW", "NEEDS DATE")):
            message = ""
    encoded = json.dumps(state, sort_keys=True, separators=(",", ":"))
    if encoded != plain(p, SYNC_STATE):
        changes[SYNC_STATE] = rich(encoded)

    current_due = date_value(p, "Safe Next Due")
    if not same_date_value(current_due, due):
        changes["Safe Next Due"] = date_patch(due)
    current_status = plain(p, "Follow-Up Timing")
    if current_status != status:
        changes["Follow-Up Timing"] = message_patch(status)
    current_message = plain(p, "Copy Follow-Up")
    if current_message != message:
        changes["Copy Follow-Up"] = message_patch(message)
    return changes



# One hidden property retains baselines and evidence that the shared legacy
# Warm Last Nudge At cannot represent independently for two different stages.
SYNC_STATE = "Follow-Up Sync State"
RESPONSE_PAGE_ID = "3fbd6e718d27803cbd94fe94f19a002a"
WARM_FLAGS = (
    ("Replied", "Details Sent", "Details Sent At"),
    ("Accepted", "Onboarding Sent", "Onboarding Sent At"),
    ("Activated", "Feedback Requested", "Feedback Requested At"),
)
TEMPLATE_LABELS = {
    "signup1": "Replied: 3 days after sending link:",
    "signup2": "Replied: final, 4 days after the first actual nudge:",
    "onboarding1": "Accepted: 3 days after sending access/onboarding instructions:",
    "onboarding2": "Accepted: final, 4 days after the first actual nudge:",
    "feedback1": "Activated: feedback, after 4 days:",
    "feedback2": "Activated: final feedback reminder, 5 days after the first request:",
}


def response_templates():
    """Read approved copy from RESPONSE DM, using section labels, never DM wording.

    Fail closed if editors remove a section label. Message text may change freely.
    No local duplicate message bank or extra integration is needed.
    """
    chunks = []
    def collect(parent):
        for block in block_children(parent):
            chunks.append(block_text(block))
            if block.get("has_children"):
                collect(block["id"])
    collect(RESPONSE_PAGE_ID)
    return parse_response_templates("\n\n".join(chunks))


def parse_response_templates(text):
    import re

    result = {}
    # Initial replies use the page's existing numbered segment/intent sections.
    sections = re.split(r"(Amateur fighters — 4 replies|Professional fighters — 4 replies|How to choose a reply)", text)
    for index, section in enumerate(sections[:-1]):
        if section not in ("Amateur fighters — 4 replies", "Professional fighters — 4 replies"):
            continue
        segment = "professional" if section.startswith("Professional") else "amateur"
        replies = re.split(r"(?:^|\n)\s*[1-4]\. [^\n]+\n", sections[index + 1])
        if len(replies) != 5:
            raise ValueError(f"RESPONSE DM: expected four {segment} sections")
        for number, reply in enumerate(replies[1:], 1):
            result[f"{segment}{number}"] = reply.strip()
    labels = list(TEMPLATE_LABELS.items())
    for index, (key, label) in enumerate(labels):
        if text.count(label) != 1:
            raise ValueError(f"RESPONSE DM: missing/duplicate section {label}")
        tail = text.split(label, 1)[1]
        end = labels[index + 1][1] if index + 1 < len(labels) else "The cold"
        if end not in tail:
            raise ValueError(f"RESPONSE DM: missing section boundary {end}")
        result[key] = tail.split(end, 1)[0].strip()
    return result


def initial_response(p, templates):
    # Use explicit enquiry cues where present; otherwise the approved general
    # response already describes both product paths. The operator can also pick
    # any of the eight approved alternatives directly on RESPONSE DM.
    enquiry = " ".join(plain(p, name) for name in ("Objection", "Notes") if name in p).lower()
    professional = (p.get("Experience", {}).get("select") or {}).get("name") == "Professional"
    segment = "professional" if professional else "amateur"
    number = 1
    if any(cue in enquiry for cue in ("already have a coach", "already has a coach", "own programme")):
        number = 1 if professional else 3
    elif any(cue in enquiry for cue in ("conditioning", "fight camp", "s&c plan")):
        number = 4 if professional else 2
    elif "recovery" in enquiry:
        segment, number = "professional", 3
    elif any(cue in enquiry for cue in ("sparring", "timer")):
        segment, number = "professional", 2
    return templates.get(f"{segment}{number}", "")


def elapsed_due(value, days):
    stamp = parse_stamp(value)
    if "T" not in value:
        # Unknown historical time: wait through the entire final day.
        return datetime.combine(stamp.date() + timedelta(days=days + 1), datetime_time.min, LONDON)
    return (stamp.astimezone(timezone.utc) + timedelta(days=days)).astimezone(LONDON)



def read_sync_state(p):
    raw = plain(p, SYNC_STATE)
    state = json.loads(raw) if raw else {"version": 1, "flags": {}, "seconds": {}, "reviews": {}, "dates": {}}
    if not isinstance(state, dict) or state.get("version") != 1:
        raise ValueError("Unsupported follow-up sync state")
    if any(not isinstance(state.get(key), dict) for key in ("flags", "seconds", "reviews", "dates")):
        raise ValueError("Malformed follow-up sync state")
    return state

def warm_state(page, today):
    """Observe actions, atomically checkpoint evidence, and retain review latches."""
    import copy

    p = page["properties"]
    raw = plain(p, SYNC_STATE)
    state = read_sync_state(p)
    state = copy.deepcopy(state)
    changes = {}
    now = now_london(today).isoformat(timespec="seconds")
    stage = (p["Stage (AI Fills First)"].get("select") or {}).get("name")
    reviews = state["reviews"]
    # Retain a conservative observation of activation, never claim an app event.
    if stage == "Activated" and not state.get("activation_observed"):
        confirmed = plain(p, "Confirmed Stage")
        known = date_value(p, "Stage Confirmed At") if "Stage Confirmed At" in p and confirmed == "Activated" else None
        state["activation_observed"] = known or now

    for owner, flag, field in WARM_FLAGS:
        checked = p[flag].get("checkbox") is True
        value = date_value(p, field)
        previous = state["flags"].get(flag)
        if checked and not value:
            if previous is False:
                changes[field] = date_patch(now)
                value = now
            else:
                reviews[owner] = f"{flag}: historic action has no verified timestamp"
        if not checked and (value or previous is True):
            reviews[owner] = f"{flag}: reversed action conflicts with send history"
        state["flags"][flag] = checked

    effective = {**p, **changes}
    for owner, count_field, synced_field, first_field in WARM_COUNTERS:
        name = (p[count_field].get("select") or {}).get("name") or "0"
        synced = p[synced_field].get("number")
        first = date_value(effective, first_field)
        root_field = "Details Sent At" if owner == "Replied" else "Onboarding Sent At"
        root = date_value(effective, root_field)
        if name not in ("0", "1", "2") or synced not in (None, 0, 1, 2):
            reviews[owner] = "Invalid nudge counter"
            continue
        count = int(name)
        if synced is not None and (count < synced or count > synced + 1):
            reviews[owner] = "Counter reversed or skipped a send"
            continue  # Keep the high-water checkpoint: invalidity survives retries.
        if synced is None or count != synced:
            changes[synced_field] = {"number": count}
        if count and not root:
            reviews[owner] = "Nudge without details/instructions send history"
        if count == 0 and (first or state["seconds"].get(owner)):
            reviews[owner] = "Counter conflicts with timestamp history"
        if count == 1 and state["seconds"].get(owner):
            reviews[owner] = "Counter conflicts with second send"
        if count == 1 and not first:
            if synced == 0 and root:
                first = now
                changes[first_field] = date_patch(first)
            else:
                reviews[owner] = "First nudge has no verified timestamp"
        if count == 2:
            if not first:
                reviews[owner] = "Final nudge has no first-send history"
            if synced == 1 and first and root and not state["seconds"].get(owner):
                state["seconds"][owner] = now
            if not state["seconds"].get(owner):
                # Warm Last Nudge At is shared across stages: never guess its owner.
                reviews[owner] = "Final nudge has no stage-specific timestamp"
        if first and root and parse_stamp(first).astimezone(timezone.utc) < elapsed_due(root, 3).astimezone(timezone.utc):
            reviews[owner] = "First nudge sent before eligibility"
        second = state["seconds"].get(owner)
        if second and first and parse_stamp(second).astimezone(timezone.utc) < elapsed_due(first, 4).astimezone(timezone.utc):
            reviews[owner] = "Final nudge sent before eligibility"
        if first and "T" in first and parse_stamp(first) > parse_stamp(now):
            reviews[owner] = "Future send timestamp"
        if (first_field in changes or (synced == 1 and count == 2 and second)):
            # Compatibility summary only. Durable per-stage evidence is above.
            changes["Warm Last Nudge At"] = date_patch(second if count == 2 else first)

    requested = date_value(effective, "Feedback Requested At")
    reminder = p["Feedback Reminder Sent"].get("checkbox") is True
    previous = state["flags"].get("Feedback Reminder Sent")
    if reminder and not state["seconds"].get("Activated"):
        if previous is False and requested:
            state["seconds"]["Activated"] = now
        else:
            reviews["Activated"] = "Feedback reminder has no verified send history"
    if not reminder and (previous is True or state["seconds"].get("Activated")):
        reviews["Activated"] = "Feedback reminder reversed"
    if reminder and not requested:
        reviews["Activated"] = "Feedback reminder without first request"
    if requested and state["seconds"].get("Activated") and parse_stamp(state["seconds"]["Activated"]).astimezone(timezone.utc) < elapsed_due(requested, 5).astimezone(timezone.utc):
        reviews["Activated"] = "Feedback reminder sent before eligibility"
    state["flags"]["Feedback Reminder Sent"] = reminder
    # Detect edits to previously verified dates, without ever overwriting them.
    for owner, _, field in WARM_FLAGS:
        value = date_value(effective, field)
        if field in state["dates"] and not same_date_value(state["dates"][field], value):
            reviews[owner] = f"{field}: verified timestamp changed"
        elif value:
            state["dates"][field] = value
        if value and parse_stamp(value).astimezone(timezone.utc) > parse_stamp(now).astimezone(timezone.utc):
            reviews[owner] = f"{field}: future send timestamp"
    for owner, _, _, field in WARM_COUNTERS:
        value = date_value({**effective, **changes}, field)
        if field in state["dates"] and not same_date_value(state["dates"][field], value):
            reviews[owner] = f"{field}: verified timestamp changed"
        elif value:
            state["dates"][field] = value
        if value and parse_stamp(value).astimezone(timezone.utc) > parse_stamp(now).astimezone(timezone.utc):
            reviews[owner] = f"{field}: future send timestamp"
    encoded = json.dumps(state, sort_keys=True, separators=(",", ":"))
    if encoded != raw:
        changes[SYNC_STATE] = rich(encoded)
    return changes, state


def warm_due_and_copy(p, state, now, templates):
    stage = (p["Stage (AI Fills First)"].get("select") or {}).get("name")
    if stage in state["reviews"]:
        return None, "Needs Review: " + state["reviews"][stage], ""
    if stage == "Replied" and any(date_value(p, field) for field in ("Registered At", "Accepted At", "First Meaningful Action At")):
        return None, "Signup complete", ""
    if stage == "Accepted" and (p["Onboarding Complete"].get("checkbox") or date_value(p, "First Meaningful Action At")):
        return None, "Onboarding complete", ""
    if stage == "Activated" and (p["Feedback Submitted"].get("number") or 0) > 0:
        return None, "Feedback complete", ""
    if stage in ("Replied", "Accepted"):
        signup = stage == "Replied"
        root = date_value(p, "Details Sent At" if signup else "Onboarding Sent At")
        count = int((p["Signup Nudges Sent" if signup else "Onboarding Nudges Sent"].get("select") or {}).get("name") or "0")
        if not root:
            if signup:
                message = initial_response(p, templates)
                if message.lstrip().upper().startswith(("WAIT", "NEEDS REVIEW")):
                    message = ""
                return None, "Reply received — send details: ready" if message else "Needs Review: RESPONSE DM unavailable", message
            return None, "Send onboarding instructions — use approved access response", ""
        if count == 2:
            return None, "Complete (2 nudges sent)", ""
        anchor = date_value(p, "Signup Nudge 1 At" if signup else "Onboarding Nudge 1 At") if count else root
        due = elapsed_due(anchor, 4 if count else 3)
        key = ("signup" if signup else "onboarding") + str(count + 1)
        label = ("Signup" if signup else "Onboarding") + (" final follow-up" if count else " first follow-up")
    else:
        requested = date_value(p, "Feedback Requested At")
        if p["Feedback Reminder Sent"].get("checkbox"):
            return None, "Complete (feedback reminder sent)", ""
        due = elapsed_due(requested, 5) if requested else elapsed_due(state["activation_observed"], 4)
        key = "feedback2" if requested else "feedback1"
        label = "Feedback reminder" if requested else "Feedback request"
    if now.astimezone(timezone.utc) < due.astimezone(timezone.utc):
        return due.isoformat(timespec="seconds"), label + ": waiting", ""
    message = templates.get(key, "")
    if not message or message.lstrip().upper().startswith(("WAIT", "NEEDS REVIEW")):
        return None, "Needs Review: approved message unavailable", ""
    return due.isoformat(timespec="seconds"), label + ": ready", message


SEND_RECEIPT = "Follow-Up Send Receipt"


def consume_send_receipt(page, today):
    """Consume the native Record Send button's stage|action|time exactly once.

    This explicit receipt is the only first-poll path that can prove a newly
    recorded action before any worker baseline. Ordinary historic counters cannot.
    It is an inbox, not another counter. All existing action fields remain canonical.
    """
    import copy

    p = page["properties"]
    receipt = plain(p, SEND_RECEIPT)
    if not receipt:
        return page, {}
    state = read_sync_state(p)
    if state.get("receipt") == receipt:
        return page, {}
    state = copy.deepcopy(state)
    changes = {}
    current_stage = (p["Stage (AI Fills First)"].get("select") or {}).get("name")
    owner = current_stage
    try:
        owner, action, stamp = receipt.split("|", 2)
        observed = parse_stamp(stamp)
        if "T" not in stamp or observed.astimezone(timezone.utc) > now_london(today).astimezone(timezone.utc):
            raise ValueError("Invalid receipt time")
        if owner not in ACTIVE_STAGES or owner in state["reviews"]:
            raise ValueError("Receipt stage has unresolved history")
        count_field = {"Contacted": "Follow-Ups Sent", "Replied": "Signup Nudges Sent", "Accepted": "Onboarding Nudges Sent"}.get(owner)
        flag, date_field = {s: (f, d) for s, f, d in WARM_FLAGS}.get(owner, (None, None))
        if action == "initial" and owner in ("Replied", "Accepted"):
            if p[flag].get("checkbox") or date_value(p, date_field):
                raise ValueError("Initial response already recorded")
            if (p[count_field].get("select") or {}).get("name") not in (None, "0"):
                raise ValueError("Initial action conflicts with nudge history")
            changes[flag] = {"checkbox": True}
            changes[date_field] = date_patch(stamp)
        elif action in ("1", "2") and count_field:
            count = int((p[count_field].get("select") or {}).get("name") or "0")
            if count != int(action) - 1:
                raise ValueError("Duplicate or skipped send action")
            if owner == "Contacted":
                _, status, _ = due_and_copy(p, count, date_value(p, "Follow-Up 1 Sent At"), date_value(p, "Follow-Up 2 Sent At"), observed, "")
                if not status.endswith(": ready"):
                    raise ValueError("Cold action is not eligible")
                field = "Follow-Up " + action + " Sent At"
                changes["Last Follow-Up Sent"] = date_patch(stamp)
            else:
                first_field = "Signup Nudge 1 At" if owner == "Replied" else "Onboarding Nudge 1 At"
                anchor = date_value(p, first_field if count else date_field)
                if not anchor or observed.astimezone(timezone.utc) < elapsed_due(anchor, 4 if count else 3).astimezone(timezone.utc):
                    raise ValueError("Warm action is not eligible")
                field = first_field if action == "1" else None
                if action == "2":
                    state["seconds"][owner] = stamp
                changes["Warm Last Nudge At"] = date_patch(stamp)
            if field:
                if date_value(p, field):
                    raise ValueError("Send timestamp already exists")
                changes[field] = date_patch(stamp)
            changes[count_field] = {"select": {"name": action}}
            changes["Synced " + count_field] = {"number": int(action)}
        elif owner == "Activated" and action in ("request", "reminder"):
            requested = date_value(p, "Feedback Requested At")
            anchor = requested if action == "reminder" else state.get("activation_observed")
            if not anchor or observed.astimezone(timezone.utc) < elapsed_due(anchor, 5 if action == "reminder" else 4).astimezone(timezone.utc):
                raise ValueError("Feedback action is not eligible")
            field = "Feedback Reminder Sent" if action == "reminder" else "Feedback Requested"
            if p[field].get("checkbox"):
                raise ValueError("Feedback action already recorded")
            changes[field] = {"checkbox": True}
            if action == "request":
                changes["Feedback Requested At"] = date_patch(stamp)
            else:
                state["seconds"][owner] = stamp
        else:
            raise ValueError("Unknown send action")
    except (ValueError, TypeError) as exc:
        changes = {}
        state["reviews"][owner if owner in ACTIVE_STAGES else current_stage] = str(exc)
    state["receipt"] = receipt
    changes[SYNC_STATE] = rich(json.dumps(state, sort_keys=True, separators=(",", ":")))
    return {**page, "properties": {**p, **changes}}, changes


def get_warm_changes(page, today):
    return warm_state(page, today)[0]

def sync(today=None, templates=None):
    fixed_time = today
    today = today or datetime.now(LONDON)
    if templates is None:
        try:
            templates = response_templates()
        except (ValueError, OSError) as exc:
            print(f"Notion RESPONSE DM unavailable ({type(exc).__name__}); blocking warm copy", file=sys.stderr)
            templates = {}
    total = changed = 0
    for page in pages():
        total += 1
        # Stable baselined rows need no extra API reads. Every unbaselined row
        # has a pending checkpoint, so first-poll races still get a fresh read.
        try:
            candidate = get_changes(page, today, templates)
        except (ValueError, TypeError, KeyError):
            candidate = True
        if not candidate:
            continue
        fresh = request("GET", f"/pages/{page['id']}")
        observed_at = fixed_time or datetime.now(LONDON)
        original, current = page["properties"], fresh["properties"]
        # In-memory first-poll evidence is valid only for actual observed 0->1
        # and false->true transitions, never for a pre-existing nonzero value.
        seed_changes = {}
        if not plain(current, SYNC_STATE) and not plain(original, SYNC_STATE):
            seeded = warm_state(page, observed_at)[1]
            fresh = {**fresh, "properties": {**current, SYNC_STATE: rich(json.dumps(seeded))}}
            for count_field, synced_field in [("Follow-Ups Sent", "Synced Follow-Ups Sent")] + [(c, s) for _, c, s, _ in WARM_COUNTERS]:
                if current[synced_field].get("number") is None:
                    name = (original[count_field].get("select") or {}).get("name") or "0"
                    if name not in ("0", "1", "2"):
                        continue
                    baseline = {"number": int(name)}
                    fresh["properties"][synced_field] = baseline
                    seed_changes[synced_field] = baseline
        try:
            changes = {**seed_changes, **get_changes(fresh, observed_at, templates)}
        except (ValueError, TypeError, KeyError):
            # Corrupt per-row state must clear copy, not leave a stale DM live
            # or prevent other fighters/history/KPIs from being synchronized.
            changes = {"Safe Next Due": date_patch(None), "Copy Follow-Up": rich(""),
                       "Follow-Up Timing": rich("Needs Review: invalid or incomplete sync state")}

        # Compare against the real server state, including the temporary seed.
        if SYNC_STATE not in changes and not plain(current, SYNC_STATE):
            changes[SYNC_STATE] = fresh["properties"][SYNC_STATE]
        if not changes:
            continue
        # Revalidate all properties, formulas and revision immediately before
        # PATCH. Notion has no conditional PATCH; see documented residual window.
        latest = request("GET", f"/pages/{page['id']}")
        if latest.get("last_edited_time") != fresh.get("last_edited_time") or latest["properties"] != current:
            continue
        request("PATCH", f"/pages/{page['id']}", {"properties": changes})
        changed += 1
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
                   for v in p.get(name, {}).get("rich_text", []))


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
        latest = request("GET", f"/pages/{page['id']}")
        if latest.get("last_edited_time") != fresh.get("last_edited_time") or latest["properties"] != fresh["properties"]:
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


def schema_plan(schema):
    """Add only durable safety state/receipt; reuse the existing warm view fields."""
    props = schema["properties"]
    required = {
        "Copy Follow-Up": "rich_text", "Follow-Up Timing": "rich_text", "Safe Next Due": "date",
        "Warm Next Due": "formula", "Warm Next DM": "formula", "Outreach Next Step": "formula",
        "Stage (AI Fills First)": "select", "Feedback Reminder Sent": "checkbox",
        "Feedback Submitted": "number", "Onboarding Complete": "checkbox", "Registered At": "date",
        "Follow-Ups Sent": "select", "Synced Follow-Ups Sent": "number",
        "Follow-Up DM": "formula", "Follow-Up 1 Sent At": "date", "Follow-Up 2 Sent At": "date",
        "Last Follow-Up Sent": "date", "Date Contacted": "date", "Warm Last Nudge At": "date",
    }
    for _, counter, synced, first in WARM_COUNTERS:
        required.update({counter: "select", synced: "number", first: "date"})
    for _, flag, field in WARM_FLAGS:
        required.update({flag: "checkbox", field: "date"})
    for name, kind in required.items():
        if props.get(name, {}).get("type") != kind:
            raise ValueError(f"Incompatible Notion property: {name} (expected {kind})")
    updates = {}
    for name in (SYNC_STATE, SEND_RECEIPT):
        if name not in props:
            updates[name] = {"rich_text": {}}
        elif props[name].get("type") != "rich_text":
            raise ValueError(f"Incompatible Notion property: {name}")
    for name, expression in (("Warm Next Due", 'prop("Safe Next Due")'),
                             ("Warm Next DM", 'prop("Copy Follow-Up")')):
        if props[name]["formula"].get("expression") != expression:
            updates[name] = {"formula": {"expression": expression}}
    # Preserve the entire existing non-warm expression, including cold behavior.
    expression = props["Outreach Next Step"]["formula"]["expression"]
    marker = 'prop("Follow-Up Timing")'
    stage = 'prop("Stage (AI Fills First)")'
    wrapper = f'if(or({stage} == "Replied", {stage} == "Accepted", {stage} == "Activated"), {marker}, ('
    if not expression.startswith(wrapper):
        expression = f'if(or({stage} == "Replied", {stage} == "Accepted", {stage} == "Activated"), {marker}, ({expression}))'
        updates["Outreach Next Step"] = {"formula": {"expression": expression}}
    return {"properties": updates}


def prepare_schema(apply=False):
    schema = request("GET", f"/data_sources/{DATA_SOURCE_ID}")
    plan = schema_plan(schema)
    # This preview contains schema/formulas only, never tokens or fighter rows.
    print(json.dumps(plan, indent=2))
    if apply and plan["properties"]:
        request("PATCH", f"/data_sources/{DATA_SOURCE_ID}", plan)
    return plan


def check_schema():
    plan = schema_plan(request("GET", f"/data_sources/{DATA_SOURCE_ID}"))
    if plan["properties"]:
        raise ValueError("Notion schema needs migration: run --schema-plan and review before --prepare-schema")


def run(argv=()):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--schema-plan", action="store_true", help="Preview one-time Notion compatibility migration (read only)")
    modes.add_argument("--prepare-schema", action="store_true", help="Apply the reviewed one-time compatibility migration")
    modes.add_argument("--check-schema", action="store_true", help="Validate schema/formula compatibility without editing rows")
    args = parser.parse_args(argv)
    if not notion_token():
        sys.exit("Expose the existing qualification worker Notion token as NOTION_TOKEN or NOTION_API_KEY (never commit it).")
    # This script runs in the existing worker container on one Hetzner host.
    # A process-scoped advisory lock includes follow-ups, history and KPIs.
    # Never unlink it: overlapping open file descriptors must share one inode.
    with open(os.getenv("NOTION_FOLLOWUP_LOCK", "/tmp/unlxck-notion-followups.lock"), "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Notion sync: another execution holds the lock; skipping")
            return
        if args.schema_plan or args.prepare_schema:
            prepare_schema(apply=args.prepare_schema)
            return
        check_schema()
        if args.check_schema:
            response_templates()
            print("Notion schema and approved response sections are compatible")
            return
        total, changed = sync()
        print(f"Notion follow-ups: checked {total}, updated {changed}")
        checked, updated = sync_stage_history()
        print(f"Notion stages: examined {checked}, updated {updated}")
        contacted, updated = sync_scorecard()
        print(f"Notion conversion: contacted {contacted}, updated {updated} blocks")


if __name__ == "__main__":
    run(sys.argv[1:])
