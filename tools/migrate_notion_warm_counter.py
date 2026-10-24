"""Preview/apply the #3027 formula migration with the existing Notion token.

Run in the worker after deployment. Does not edit rows, counters, or timestamps.
"""
import argparse
import json
from pathlib import Path

import sync_notion_followups as sync

FIELDS = ("Warm Next Due", "Warm Next DM", "Next DM to Copy", "Next Outreach Due", "Outreach Next Step")
WARM = 'or(prop("Stage (AI Fills First)") == "Replied", prop("Stage (AI Fills First)") == "Accepted")'


def formula_changes(properties):
    changes = {}
    for name in FIELDS:
        original = properties[name]["formula"]["expression"]
        # Preserve all non-warm branches, especially cold and Activated.
        prefix = f'if({WARM}, '
        if original.startswith(prefix):
            continue
        shared = original.replace('prop("Onboarding Nudges Sent")', 'prop("Signup Nudges Sent")')
        shared = shared.replace('prop("Onboarding Nudge 1 At")', 'prop("Signup Nudge 1 At")')
        if name in ("Warm Next Due", "Next Outreach Due"):
            warm = 'prop("Safe Next Due")'
        elif name in ("Warm Next DM", "Next DM to Copy"):
            # Copy Follow-Up is selected independently by the updated worker.
            warm = 'prop("Copy Follow-Up")'
        else:
            warm = f'if(empty(prop("Safe Next Due")), prop("Follow-Up Timing"), {shared})'
        changes[name] = {"formula": {"expression": f'{prefix}{warm}, {original})'}}
    return changes


def migrate(apply=False, backup=None):
    path = f"/data_sources/{sync.DATA_SOURCE_ID}"
    schema = sync.request("GET", path)
    changes = formula_changes(schema["properties"])
    print("Formula migration fields: " + ", ".join(changes))
    if not apply or not changes:
        return
    if not backup:
        raise ValueError("--backup is required when applying")
    # Exclusive creation prevents overwriting the original rollback snapshot.
    with Path(backup).open("x") as target:
        json.dump({name: schema["properties"][name] for name in FIELDS}, target, indent=2)
    fresh = sync.request("GET", path)
    if any(fresh["properties"][name]["formula"] != schema["properties"][name]["formula"] for name in FIELDS):
        raise RuntimeError("Formulas changed during review; retry with a new backup")
    sync.request("PATCH", path, {"properties": changes})
    verified = sync.request("GET", path)
    if any(verified["properties"][name]["formula"] != patch["formula"] for name, patch in changes.items()):
        raise RuntimeError("Formula read-back differs; keep 3B sends disabled")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup")
    args = parser.parse_args()
    migrate(args.apply, args.backup)
